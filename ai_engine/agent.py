import os
from typing import TypedDict
from langchain_core.messages import BaseMessage
from langchain_huggingface import HuggingFaceEndpoint
from langchain_groq import ChatGroq

from resources.router import RouterOutput,router_prompt
from typing import List, Optional,LiteralString,Annotated,Literal,Dict
from langchain_core.output_parsers import PydanticOutputParser
from graph_db import Neo4jHandler
from qdrant import search_chunk
from resources.large_llm_prompt import large_lm_prompt
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, add_messages
from langsmith import traceable
#TODO: Build a RAG pipeline. It should take retrieve the structure(calls,imports and definitions) from neo4j.
#TODO: Perform similarly search using Qdrant. Provide Neo4j output of similarity and query of user
#TODO: Use persistence method on langgraph and integrate with supabase..If needed change the schema in supabase

neo4j_handler = Neo4jHandler()


parser = PydanticOutputParser(pydantic_object = RouterOutput)
router_llm = HuggingFaceEndpoint(
    repo_id="google/flan-t5-large",
    task="text2text-generation",
    max_new_tokens=64,
    temperature=0.01,
    huggingfacehub_api_token=os.getenv("HUGGINGFACEHUB_API_TOKEN")
).with_structured_output(parser)

llm_technical = ChatGroq(
    temperature = 0,
    model = "llama-3.1-8b-instant",
    api_key = os.getenv("GROQ_API_KEY")
)


summarizer_llm = HuggingFaceEndpoint(
    repo_id="google/flan-t5-large",
    task="text2text-generation",
    temperature = 0,
    huggingfacehub_api_token=os.getenv(("HUGGINGFACE_API_TOKEN"))
)


class RepoState(TypedDict):
    messages:Annotated[List,add_messages]
    intent:Literal["general","technical"]
    selected_files :List[str]
    # files_score : Dict[str,float]
    chunks:str
    planner_confidence:float
    summary :str
    user_query :str
    final_answer :Optional[str]

def keyword_similarity(query:str,text:str) -> float:
    query = set(query.lower().split())
    text = set(text.lower().split())
    if not query:
        return 0.0
    return len((query & text)) / len(query)

def rerank_chunks(hits, query,selected_files,confidence_score,top_k = 8):
    """
    Logic of reranking for chunks.
    score = 0.45 * vector_score +
            0.25 * confidence_score +
            0.20 * file_score +
            0.10 * keyword_score
    :param hits:
    :param query:
    :param selected_files:
    :param confidence_score:
    :param top_k:
    :return:
    """
    reranked = []

    for h in hits:
        payload = h.payload
        keyword_score = keyword_similarity(query = query,text = payload.text)
        vector_score = h.score
        confidence_score = confidence_score
        if payload["path"] in selected_files:
            file_score = 1.0
        else:
            file_score = 0.4

        final_score = (
            0.45 * vector_score +
            0.25 * confidence_score +
            0.20 * file_score +
            0.10 * keyword_score
        )
        reranked.append((final_score,payload.text))
    reranked.sort(key= lambda x : x[0], reverse = True )
    return [text for _,text in reranked[:top_k]]


@traceable(name="context_sync")
def build_context(state:RepoState):
    if state.get("summary"):
        return [
            SystemMessage(content=f"You are a senior software engineer.\nCConversation summary: {state["summary"]}")
        ] + state["messages"]
    return state["messages"]


#----------------------------Nodes -------------------------------------------------------------

def summarize_node(state:RepoState):
    if len(state["messages"]) <= 20:
        return state
    messages = state["messages"]
    summary = state["summary"]

    last_messages = messages[:-20]
    remaining = messages[-20:]

    summary_prompt = f"""
    You are summarizing a technical conversation.

    Rules:
    - Preserve technical details.
    - Preserve unresolved questions.
    - Preserve user intent.
    - Do not add new information.
    
    
        Existing summary:{summary}
        
        New conversation: 
        {last_messages}
        
        Return a concise summary. 
    """

    summary = summarizer_llm.invoke(summary_prompt).content

    return {
        **state,
        "messages": remaining,
        "summary": summary
    }

def planner_node(state:RepoState,files_paths:List[str]):
    """
    Small llm:
    -classify the intent
    - if general directly produce the answer
    - selects files if technical

    :param state:
    :param files_paths:
    :return:
    """
    prompt = router_prompt.invoke(
        {
            "file_paths": files_paths,
            "query": state["user_query"]
        }
    )
    parsed = router_llm.invoke(prompt)
    result = RouterOutput.parse_raw(parsed)

    state["intent"] = result.intent
    state["selected_files"] = result.files
    state["planner_confidence"] = result.confidence

    if result["intent"] == "general":
        state["final_answer"] = result.answer

def neo4j_node(state:RepoState,repo_name:str,commit_id:str):
    """
    Extracts dependencies from neo4j and adds in selected files.
    :param state:
    :param repo_name:
    :param commit_id:
    :return:
    """
    selected_files = state["selected_files"]

    files = neo4j_handler.search_files(repo_name= repo_name,commit_id= commit_id,files = selected_files)


    state["selected_files"] = files
    return state

def qdrant_node(state:RepoState,repo_name,commit_id):
    """
    Performs similarity search in GitHub repo. Retrieves and reranks the chunks
    :param state:
    :param repo_name:
    :param commit_id:
    :return:
    """

    hits = search_chunk(repo_name=repo_name,
                        commit_id=commit_id,
                        files = state["selected_files"],
                        user_query=state["user_query"])

    reranked_chunk = rerank_chunks(hits = hits,
                                   query =state["user_query"],
                                   selected_files=state["selected_files"],
                                   confidence_score = state["planner_confidence"])

    chunks = "\n\n".join(reranked_chunk)
    state["chunks"] = chunks

    return state

def technical_node(state:RepoState):
    """
    Answers the technical query of user
    :param state:
    :return:
    """
    messages = build_context(state)
    prompt = large_lm_prompt.invoke({
        "query" : state["user_query"],
        "paths": state["selected_files"],
        "context": state["chunks"],
        "old_chat_context": messages
    })

    response = llm_technical.invoke(prompt).content
    state["final_answer"] = response
    return {
        "messages": state["messages"] + [response]
    }
def answer_node(state:RepoState):
    """
    Returns the answer if the query was general
    :param state: 
    :return: 
    """
    pass

## ------------------------------------Build graph----------------------------------------------

# builder = StateGraph(RepoState)
#
# builder.add_node("summarize",summarize_node)
# builder





