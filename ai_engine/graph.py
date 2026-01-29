import ast
import json
import ast
import uuid
import os
import httpx
import requests
import asyncio
from qdrant_client import QdrantClient,models
from ai_engine.qdrant import create_collection,get_chunk_code,embed_text
qdrant_client = QdrantClient(url=os.getenv("QDRANT_ENDPOINT"),api_key=os.getenv("QDRANT_API_KEY"))
import redis
redis_conn = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)



class CodeAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.imports = []
        self.functions = []
        self.calls = []
        self.class_def = []

    def visit_Import(self,node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ''
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}")
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.class_def.append(node.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        function_name = self._get_func_name(node.func)
        if function_name:
            self.calls.append(function_name)
        self.generic_visit(node)

    def _get_func_name(self,node):
        if isinstance(node,ast.Name):
            return node.id
        elif isinstance(node,ast.Attribute):
            return node.attr
        return  None

class GraphBuilder:
    def __init__(self):
        self.nodes = []
        self.links = []
        self.path_to_id = {}
        self.id_counter = 0
        self.tree_data = None
        self.owner= None
        self.repo= None
        self.default_branch = None


    async def get_tree(self,repo_url:str,github_token:str):
        """
        Gets GitHub repo tree using repo url
        :param repo_url:
        :param github_token:
        :return:
        """
        clean_url = repo_url.rstrip("/")
        parts = clean_url.split("/")
        if len(parts) < 2: return None
        self.owner, self.repo = parts[-2], parts[-1].removesuffix(".git")


        header = {
            "Accept": "application/vnd.github+json",
        }
        if github_token:
            header["Authorization"] = f"Bearer {github_token}"


        branch_url = f"https://api.github.com/repos/{self.owner}/{self.repo}"
        response = requests.get(branch_url,headers=header).json()
        if "default_branch" not in response:
            raise  ValueError("Cannot access repo.Check link and Rate limits")
        self.default_branch = response["default_branch"]


        github_tree_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/{self.default_branch}?recursive=1"
        async with httpx.AsyncClient() as Client:
            try:
                resp = await Client.get(github_tree_url, headers=header)
                print(resp)
                resp.raise_for_status()
                if resp.status_code != 200:
                    return None
                tree_data = resp.json()
            except Exception as e:
                print(f"Encountered error :{e}")


        self.tree_data = sorted(tree_data.get("tree"), key=lambda x: x["path"])



    async def build_repo_graph_frontend(self,repo_url:str,github_token:str):
        """
        Fetches file from GitHub repo and constructs a graph for frontend
        :param repo_url:
        :param github_token:
        :return:
        """

        try:

            await self.get_tree(repo_url,github_token)

            root_id= self.id_counter
            self.nodes.append({
                "id":root_id,
                "name": self.repo,
                "group": "root",
                "radius": 25
            })
            self.id_counter +=1


            for item in self.tree_data:
                path = item["path"]
                is_folder = item["type"] == "tree"
                node_id = self.id_counter
                self.nodes.append({
                    "id": node_id,
                    "name": path.split("/")[-1],
                    "path" : path,
                    "group": "folder" if is_folder else "file",
                    "radius": 12 if is_folder else 6
                })
                self.path_to_id[path] = self.id_counter
                if "/" in path:
                    parent_path = path.rsplit("/",1)[0]
                    parent_id = self.path_to_id.get(parent_path)
                else:
                    parent_id = root_id
                self.links.append({"source": parent_id,"target": node_id})
                self.id_counter+=1





            return {"nodes":self.nodes,"links":self.links}

        except Exception as e:
            print(f"Graph Generation Failed:{e}")
            return None

    async def preprocessing_graph(self, repo_url: str, github_token: str,commit_id:str):
        """
        1. Filter files and stores .py and .md files
        2. Breaks .py file into Imports,Functions definitions,Class definitions,Function calls
        3. Encodes code file (.js,.py,.html,.css) chunks code(Recursive splitter) and stores points into qdrant.
        :param repo_url:
        :param github_token:
        :param commit_id:
        :return:
        """
        structure = {}
        await self.get_tree(repo_url,github_token)
        #------------------------------------get nodes for files and folder in repo ----------------------------------------------------
        try:

            await self.get_tree(repo_url,github_token)

            root_id= self.id_counter
            self.nodes.append({
                "id":root_id,
                "path": "",
                "name": self.repo,
                "group": "root",
                "radius": 25
            })
            self.id_counter +=1
            n_files = 0

            for item in self.tree_data:
                path = item["path"]
                is_folder = item["type"] == "tree"
                node_id = self.id_counter
                if not is_folder:
                    n_files +=1
                self.nodes.append({
                    "id": node_id,
                    "name": path.split("/")[-1],
                    "path" : path,
                    "group": "folder" if is_folder else "file",
                    "radius": 12 if is_folder else 6
                })
                self.path_to_id[path] = self.id_counter
                if "/" in path:
                    parent_path = path.rsplit("/",1)[0]
                    parent_id = self.path_to_id.get(parent_path)
                else:
                    parent_id = root_id
                self.links.append({"source": parent_id,"target": node_id})
                self.id_counter+=1
            if n_files > 100:
                return False
        except Exception as e:
            print(f"Graph Generation Failed:{e}")
            return None



        ##---------------------------------preprocess data-------------------------
        create_collection()
        chunker = get_chunk_code()
        points = []
        n_files = 0
        for item in self.tree_data:
            path = item["path"]

            if item["type"] == "blob":
                raw_url = f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.default_branch}/{path}"
                response = requests.get(raw_url)
                code_content = response.text
                if response.text == "":
                    continue
                if n_files > 100:
                    break

                try:
                    # --------Encodes, chunks code in file and creates point for every chunk-------------------------------------------------
                    if path.endswith((".js",".md",".html",".css",".py")):
                        chunks = chunker.split_text(code_content)
                        embed_texts = embed_text(chunks)
                        for idx, (chunk, embedding) in enumerate(zip(chunks, embed_texts)):
                            payload = {
                                "repo_name": self.repo,
                                "commit_id": commit_id,
                                "path": path,
                                "text": chunk,
                                "language": path.split(".")[-1],
                                "chunk_index": idx
                            }
                            points.append(models.PointStruct(
                                id = str(uuid.uuid4()),
                                vector = embedding,
                                payload = payload
                            ))
                        n_files += 1 

                    #------------------If it is python file parse the code and get function_calls,class_def ,function_def and import------------------------------
                    if path.endswith(".py"):
                        try:

                            tree = ast.parse(code_content)
                            analyzer = CodeAnalyzer()
                            analyzer.visit(tree)

                            structure[path] = {
                                "imports":analyzer.imports,
                                "functions": analyzer.functions,
                                "class_def":analyzer.class_def,
                                "calls":analyzer.calls
                            }
                        except Exception as e:
                            print(f"Encountered error while breaking python files :{e}")


                except Exception as e:
                    print(f"Error at preprocessing graph : {e}")


        if points:
            qdrant_client.upsert(
                collection_name="repo_knowledge",
                points = points
            )
        redis_conn.set(f"repo_details:{repo_url}",json.dumps({"files_list": self.nodes,"owner":self.owner,"commit_id":commit_id,"repo_name":self.repo,"links": self.links}),nx = True)
        return {"structure": structure,"nodes":self.nodes,"owner":self.owner,"Repo_name":self.repo,"links": self.links}






