from ai_engine.graph_db import Neo4jHandler

h = Neo4jHandler()


repo_name = "Explora"
commit_id =  "e69e6d2e3f727c968db4b4a80b45f81705f72fcc"
files = ["main.py","detection.py"]

h.search_files(repo_name=repo_name,commit_id=commit_id,files=files)

