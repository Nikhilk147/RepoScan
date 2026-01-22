import os
from typing import TypedDict

from langchain_groq import ChatGroq
from resources.router import RouterOutput,router_prompt
from typing import List, Optional,LiteralString,Annotated,Literal,Dict
from langchain_core.output_parsers import PydanticOutputParser
from ai_engine.graph_db import Neo4jHandler
from ai_engine.qdrant import search_chunk
from resources.large_llm_prompt import large_lm_prompt
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
from langgraph.graph import StateGraph, add_messages,START,END
from langsmith import traceable
from helper.checkpointer import SupabaseSaver
from resources.summarizer import summary_prompt


neo4j_handler = Neo4jHandler()


parser = PydanticOutputParser(pydantic_object = RouterOutput)


llm_technical = ChatGroq(
    temperature = 0,
    model="llama-3.1-8b-instant",

    api_key = os.getenv("GROQ_API_KEY")
)
summarizer_llm = ChatGroq(
    temperature = 0,

    model="llama-3.1-8b-instant",

    api_key = os.getenv("GROQ_API_KEY")
)
router_llm = ChatGroq(
    temperature = 0,

    model="llama-3.1-8b-instant",

    api_key = os.getenv("GROQ_API_KEY")
).with_structured_output(RouterOutput)


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

    #External Info
    commit_id:str
    repo_name:str
    files_path:List[str]

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


    for h in hits.points:
        payload = h.payload
        keyword_score = keyword_similarity(query = query,text = payload["text"])
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
        reranked.append((final_score,payload["text"]))
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
    """
    Summarizes the conversation history if it exceeds 10(length = 20) consersations
    :param state:
    :return:
    """
    if len(state["messages"]) <= 20:
        return state
    messages = state["messages"]
    summary = state["summary"]

    last_messages = messages[:-20]
    remaining = messages[-20:]

    s_prompt = summary_prompt.invoke({"summary":summary,"last_messages":last_messages})

    summary = summarizer_llm.invoke(s_prompt).content

    return {
        **state,
        "messages": remaining,
        "summary": summary
    }

def router_node(state:RepoState):
    """
    Small llm:
    -classify the intent
    - if general directly produce the answer
    - selects files if technical

    :param state:
    :return:
    """
    prompt = router_prompt.invoke(
        {
            "file_paths": state["files_path"],
            "query": state["user_query"]
        }
    )
    parsed = router_llm.invoke(prompt)

    return {
        "intent": parsed.intent,
        "selected_files": parsed.files,
        "planner_confidence": parsed.confidence,
        "final_answer": parsed.answer if parsed.intent == "general" else None
    }


def neo4j_node(state:RepoState):
    """
    Extracts dependencies from neo4j and adds in selected files.
    :param state:
    :return:
    """
    selected_files = [file for file in state["files_path"] if file.endswith(".py")]

    files = neo4j_handler.search_files(repo_name= state["repo_name"],commit_id= state["commit_id"],files = selected_files)



    return {
        "selected_files" : files
    }

def qdrant_node(state:RepoState):
    """
    Performs similarity search in GitHub repo. Retrieves and reranks the chunks
    :param state:
    :return:
    """

    hits = search_chunk(repo_name=state["repo_name"],
                        commit_id=state["commit_id"],
                        files = state["selected_files"],
                        user_query=state["user_query"])

    reranked_chunk = rerank_chunks(hits = hits,
                                   query =state["user_query"],
                                   selected_files=state["selected_files"],
                                   confidence_score = state["planner_confidence"])

    chunks = "\n\n".join(reranked_chunk)


    return {
        "chunks": chunks
    }

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

    return {
        "final_answer": response,
        "messages": [HumanMessage(content=state["user_query"]), AIMessage(content=response)]
    }
def answer_node(state:RepoState):
    """
    Returns the answer if the query was general
    :param state: 
    :return: 
    """

    return {
        "final_answer":state["final_answer"],
        "messages": [
            HumanMessage(content=state["user_query"]),
            AIMessage(content=state["final_answer"])
        ]
    }
def router_func(state:RepoState):
    """
    Router node based on intent of the query
    :param state:
    :return:
    """

    if state["intent"] == "general":
        return "general_answer"
    else:
        return "technical"
## ------------------------------------Build graph----------------------------------------------

##-----------------Nodes----------------
builder = StateGraph(RepoState)

builder.add_node("summarize",summarize_node)
builder.add_node("router",router_node)
builder.add_node("neo4j",neo4j_node)
builder.add_node("qdrant",qdrant_node)
builder.add_node("technical",technical_node)
builder.add_node("general_answer",answer_node)


#------------------Edges ----------------
builder.add_edge(START,"router")
builder.add_conditional_edges(
    "router",
    router_func,
    {
        "general_answer": "general_answer",
        "technical": "neo4j"
    }
)
builder.add_edge("neo4j","qdrant")
builder.add_edge("qdrant","technical")
builder.add_edge("technical",END)
builder.add_edge("general_answer",END)

graph = builder.compile(checkpointer = SupabaseSaver())
