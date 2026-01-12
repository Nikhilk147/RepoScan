from ai_engine.graph_db import Neo4jHandler
from langchain_groq import ChatGroq
h = Neo4jHandler()
import os

# repo_name = "Explora"
# commit_id =  "e69e6d2e3f727c968db4b4a80b45f81705f72fcc"
# files = ["main.py","detection.py"]
#
# h.search_files(repo_name=repo_name,commit_id=commit_id,files=files)

llm_technical = ChatGroq(
    temperature = 0,
    model = "llama-3.1-8b-instant",
    api_key = os.getenv("GROQ_API_KEY")
)


output = llm_technical.invoke("hello ")
print(output.type)