import os
from typing import TypedDict,List,Union
from langgraph.graph import StateGraph,END,START
from langchain_core.messages import AIMessage,HumanMessage,SystemMessage
from langchain_huggingface import HuggingFaceEndpoint
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate

#TODO: Build a RAG pipeline. It should take retrieve the structure(calls,imports and definitions) from neo4j.
#TODO: Perform similarly search using Qdrant. Provide Neo4j output of similarity and query of user
#TODO: Use persistence method on langgraph and integrate with supabase..If needed change the schema in supabase

router_llm = HuggingFaceEndpoint(
    repo_id="google/flan-t5-large",
    task="text2text-generation",
    max_new_tokens=10,
    temperature=0.01,
    huggingfacehub_api_token=os.getenv("HUGGINGFACEHUB_API_TOKEN")
)

llm_technical = ChatGroq(
    temperature = 0,
    model = "llama3-70b-8192",
    api_key = os.getenv("GROQ_API_KEY")
)

class AgentState(TypedDict):
    messages: List[Union[HumanMessage,AIMessage,SystemMessage]]
    intent:str

def router_node(state:AgentState):
    """Analyze the user query and decide if request is basic knowledge
    question/greetings or based on git/coding"""
    last_message = state["messages"][-1].content

    router_prompt = PromptTemplate.from_template(
        """Classify the following query as either "technical explanation of topic or general" or "deep technical question/coding question
        answer in just "general" or "technical/code"
        Question : {input}
        Classification
        
        """
    )
    chain = router_prompt | router_llm
    response = chain.invoke({"input":last_message})
    intent = response.strip().lower().replace(".","")
    if "technical" in intent or "code" in intent:
        intent = "technical"
    else:
        intent = "general"
    print("--------------------------Intend Analyzed-----------------------------------")

def technical_node(state:AgentState):
    """Large model serves the technical/coding requirement (Groq)"""
    print("----Expert Node---------")
    pass



