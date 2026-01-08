#TODO: define a structure of the graph
#TODO: Check if can undergo a similarity search
#TODO: define functions for building a graph from a new query
#TODO: check if there is a functionality to delete a graph after a specific time(TTL)
#TODO: Make sure it store commit id for every repo in the database
import os

from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class Neo4jHandler:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth = (os.getenv("NEO4J_USERNAME"),os.getenv("NEO4j_PASSWORD")),

        )


    def close(self):
        self.driver.close()

    def add_owner(self,owner_name):
        """
        Adds a repo owner of repo and links them to the Highest Node
        :param owner_name:
        :return:
        """
        query = """
        MATCH (root:Root)
        MERGE (o:RepoOwner {username: $name})
        MERGE (root) - [:OWNS] -> (o)
        """
        with self.driver.session() as session:
            session.run(query,name = owner_name)


    def add_repo(self,owner_name,repo_name):
        """
        Adds a repo node and links it to its owner node
        :param owner_name:
        :param repo_name:
        :return:
        """
        query = """
        MATCH (owner:RepoOwner {username: $owner})
        MERGE (r:Repository {name: $name, full_name: $owner + '/' + $name})
        MERGE (owner) - [:HAS_REPO] -> (r)
        """
        with self.driver.session() as session:
            session.run(query,owner = owner_name,name = repo_name)



    def add_commit(self,repo_name,owner_name,commit_id):
        """
        Adds a commit node representing the latest commit to the default branch
        :param repo_name:
        :param owner_name:
        :param commit_id:
        :return:
        """
        query = """
        MATCH (owner:RepoOwner {username: $owner}) - [:HAS_REPO] -> (repo:Repository {name:$name})
        MERGE (com:Commit {commit_id: $commit_id})
        ON CREATE SET com.created_at = datetime.realtime()
        MERGE (repo) - [:HAS_COMMIT] -> (com)
        """
        with self.driver.session() as session:
            session.run(query,owner = owner_name,name = repo_name,commit_id= commit_id)


    def add_file(self,repo_name,file_path,owner_name,commit_id):
        """
        Analyze the path, if path consists of hierarchy of files.Create an individual node for every level.
        :param repo_name:
        :param owner_name:
        :param file_path:

        :return:
        """

        parts = file_path.strip("/").split("/")
        file_name = parts[-1]
        directories = parts[:-1]
        with self.driver.session() as session:

            result = session.run("MATCH (r:Repository {name : $name,full_name : $owner + '/'+ $name}) - [:HAS_COMMIT] -> (comm:Commit) RETURN elementId(comm) as id", name = repo_name,owner = owner_name)
            record = result.single()
            if not record:
                print(f"Error : commit for {repo_name} doesn't exist. Create it first.")
                return
            parent_id = record["id"]
            print(f"directories for path : {file_path} ---{directories}----file_name:{file_name}")
            current_path = ""
            for folder in directories:
                current_path = f"{current_path}/{folder}" if current_path else folder
                query = """
                MATCH (parent) WHERE elementId(parent) = $pid
                MERGE (d:DIRECTORY {path: $path})
                ON CREATE SET d.name = $name
                MERGE (parent) - [:CONTAINS_DIR] -> (d)
                RETURN elementId(d) as id 
                """
                result = session.run(query,pid = parent_id,path =current_path,name = folder)
                parent_id = result.single()["id"]
            query_file = """
            MATCH (parent) WHERE elementId(parent) = $pid
            MERGE (f:File {path : $path,commit_id:$commit_id})
            ON CREATE SET f.name = $name
            MERGE (parent) - [:CONTAINS_FILE] -> (f)
            """
            session.run(query_file,pid = parent_id,path = file_path,name = file_name,commit_id=commit_id)


    def create_relations(self,repo_name,owner_name,nodes,preprocessed_repo,commit_id):
        """
        Builds relationships between .py files if a file imports from another file
        :param repo_name:
        :param owner_name:
        :param nodes:
        :param preprocessed_repo:
        :param commit_id:
        :return:
        """
        relations = {}
        node_list = [node["path"] for node in nodes ]
        for file, data in preprocessed_repo['structure'].items():
            imports = data.get("imports")
            import_result = []
            for ele in imports:
                imp = ele.lstrip(".").split(".") if "." in ele else ele
                if imp == ele:
                    path = file.rsplit("/", 1)[0] + f"/{imp}.py"

                    if path in node_list:
                        import_result.append(path)
                else:

                    for item in range(len(imp), 0, -1):
                        if "/" in file:
                            temp_path = file.rsplit("/", 1)[0] + "/" + "/".join(imp[:item]) + ".py"
                        else:
                            temp_path = "" + "/".join(imp[:item]) + ".py"

                        if temp_path in node_list:
                            import_result.append(temp_path)
                            break
            if len(import_result) > 0:
                relations[file] = import_result
            else:
                continue
        print(f"Relations:{relations}")
        with self.driver.session() as session:
            owner_to_commit_query = """
            MATCH (o:RepoOwner {username: $owner}) - [:HAS_REPO] -> (r:Repository {name:$name}),
                    (r:Repository {name:$name}) - [:HAS_COMMIT] -> (com:Commit)
            RETURN elementId(com) as id 
            """

            result = session.run(owner_to_commit_query, owner = owner_name,name =repo_name)
            commit_node = result.single()["id"]
            create_relation_query = """
                                    MATCH (main) WHERE elementId(main) = $mid
                                    MATCH (main) - [*] -> (s_file:File {path: $s_path,commit_id:$commit_id})
                                    MATCH (main) - [*] -> (d_file:File {path: $d_path,commit_id:$commit_id})
                                    MERGE (s_file) - [:IMPORTS] -> (d_file)
                            """
            for file,imports in relations.items():
                s_path = file
                for imp in imports:
                    d_path = imp
                    session.run(create_relation_query,mid=commit_node,s_path = s_path,d_path=d_path,commit_id=commit_id)



    def delete_commit(self,repo_name,owner_name):
        query_to_delete_commit = """
            MATCH (o:RepoOwner {username: $owner}) - [:HAS_REPO] -> (r:Repository {name:$name}) - [:HAS_COMMIT] -> (com:Commit)
            MATCH (com) - [*0..]-> (n)
            DETACH DELETE n
        """
        with self.driver.session()  as session:
            session.run(query_to_delete_commit,owner= owner_name,repo = repo_name)









