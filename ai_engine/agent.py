import os
from typing import TypedDict
from langchain_core.messages import BaseMessage
from langchain_huggingface import HuggingFaceEndpoint
from langchain_groq import ChatGroq

from resources.router import RouterOutput,router_prompt
from typing import List, Optional,LiteralString,Annotated
from langchain_core.output_parsers import PydanticOutputParser
from graph_db import Neo4jHandler
from qdrant import search_chunk
from resources.large_llm_prompt import large_lm_prompt
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, add_messages

#TODO: Build a RAG pipeline. It should take retrieve the structure(calls,imports and definitions) from neo4j.
#TODO: Perform similarly search using Qdrant. Provide Neo4j output of similarity and query of user
#TODO: Use persistence method on langgraph and integrate with supabase..If needed change the schema in supabase

neo4j_handler = Neo4jHandler()


parser = PydanticOutputParser(pydantic_object = RouterOutput)
router_llm = HuggingFaceEndpoint(
    repo_id="google/flan-t5-large",
    task="text2text-generation",
    max_new_tokens=10,
    temperature=0.01,
    huggingfacehub_api_token=os.getenv("HUGGINGFACEHUB_API_TOKEN")
).with_structured_output(parser)

llm_technical = ChatGroq(
    temperature = 0,
    model = "llama3-70b-8192",
    api_key = os.getenv("GROQ_API_KEY")
)



class RepoState(TypedDict):
    user_query:str
    selected_files: List[str]
    planner_confidence : float
    chunks : LiteralString
    final_answer : Optional[str]
    messages: Annotated[list,SystemMessage("You are a senior software engineer."), add_messages]
    summary: Optional[str]
    intent:str



def small_llm_node(state:RepoState,file_paths):
    """Analyze the user query and decide if request is basic knowledge
    question/greetings or based on git/coding"""
    last_message = state["messages"][-1].content
    chain = router_prompt | router_llm | parser
    response = chain.invoke({
        "query":last_message,
        "file_paths":file_paths,
    })
    result = response.content
    intent = result.intent
    if intent == "technical":
        state["intent"] = "technical"
    else:
        state["intent"] = "general"
        state["final_answer"] = result.answer
    print("-------------------------- Intent Analyzed -----------------------------------")

def neo4j_node(state:RepoState,repo_details,commit_id):
    """Finds files that being imported by selected file by small lmm"""
    files = state["selected_files"]
    dependencies = neo4j_handler.search_files(repo_name= repo_details["name"],commit_id= commit_id,files = files)
    files = set(files + dependencies)
    state["selected_files"] = list(files)

def qdrant_node(state:RepoState,repo_name,commit_id):
    """Vector search in qdrant for relevant chunks"""
    hits = search_chunk(repo_name=repo_name,commit_id=commit_id,files = state["selected_files"],user_query = state["messages"][-1])
    content = "\n\n".join([h.payload["text"] for h in hits])
    state["chunks"] = content



def technical_node(state:RepoState):
    """Large model serves the technical/coding requirement (Groq)"""
    print("----Expert Node---------")
    state["messages"][-1] = large_lm_prompt.invoke(
        {
            "query": state["user_query"],
            'paths': state["selected_files"],
            'context': state["chunks"]
        })
    llm_technical.invoke(state["messages"])



