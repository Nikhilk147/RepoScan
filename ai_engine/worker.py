import os
import redis
from dotenv import load_dotenv
import json
import time
from graph_db import Neo4jHandler
from graph import GraphBuilder
import asyncio
from helper.commit import get_commit_sha
import multiprocessing
from supabase import Client,create_client
import traceback
#TODO: Increase the functionality by retrieving repo files ..scanning them...get the file content...can building method from graph.db
#TODO: first check if the repo exists in graph_db
#TODO: if repo exists but if it represents old commit..initiate the build graph functionality

MAIN_QUEUE = "repo_tasks"
QUEUE_PROCESSING = "repo_tasks:processing"
UNIQUE_SET = "repo_task:unique_set"
TIMEOUT_SEC  = 300
MAX_CONCURRENT_JOBS = 5
supabase: Client = create_client(os.getenv("SUPABASE_URL"),os.getenv("SUPABASE_KEY"))
load_dotenv()
redis_conn = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

# ------------------------------------------------------Build database graph------------------------------------------------------------

async def build_graph(repo_detail,commit_id):
    owner = repo_detail["owner"]
    repo = repo_detail["Repo_name"]
    print(repo_detail)

    file_list = [node["path"] for node in repo_detail["nodes"] if node["path"].endswith(".py")]
    neo4j_handler = Neo4jHandler()
    try:
        neo4j_handler.add_owner(owner_name=owner)
        neo4j_handler.add_repo(owner_name=owner,repo_name=repo)
        neo4j_handler.add_commit(repo_name=repo,owner_name=owner,commit_id=commit_id)
        print(file_list)
        for f in file_list:
            neo4j_handler.add_file(repo_name=repo,file_path=f,owner_name= owner,commit_id = commit_id)
        neo4j_handler.create_relations(repo_name =repo,owner_name = owner, nodes=repo_detail["nodes"], preprocessed_repo = repo_detail,commit_id=commit_id)



        neo4j_handler.close()
    except Exception as e:
        full_traceback = traceback.format_exc()
        print(full_traceback)
        print(f"Error occurred while building graph in neo4j:{e}")


# ------------------------------------------------------------------------Queueing jobs ----------------------------------------------



async def _async_processing_task_(job_details):

    graph_builder = GraphBuilder()
    print(f"Job details in processing task: {job_details}")
    repo_url = job_details["url"]
    github_token = job_details["github_token"]
    session_id = job_details["session_id"]
    try:
        commit_id = get_commit_sha(repo_url=repo_url, github_token=github_token)
        repo_details = await graph_builder.preprocessing_graph(repo_url=repo_url, github_token=github_token,commit_id=commit_id)

        await build_graph(repo_detail = repo_details,commit_id = commit_id)
        graph_data = {"nodes":repo_details["nodes"],"links":repo_details["links"]}
        job_detail = {
            "status": "completed",
            "graph_data": graph_data
                     }
        redis_conn.publish(f"job_status:{job_details["job_id"]}",json.dumps(job_detail))
    except Exception as e:
        job_detail = {
            "status": "failed"
        }
        redis_conn.publish(f"job_status:{job_details["job_id"]}", json.dumps(job_detail))
        full_traceback = traceback.format_exc()
        print(full_traceback)
        print(f"Encounter error in job completion :{e}")

def processing_task_wrapper(job_details):
    asyncio.run(_async_processing_task_(job_details))


def cleanup_resources(redis_conn, job_details, reason="Finished"):
    """

    :param redis_conn:
    :param job_details:

    :param reason:
    :return:
    """
    job_id = job_details["job_id"]
    print(f"removing job from the queue:{job_id}")

    pipe = redis_conn.pipeline()
    pipe.lrem(QUEUE_PROCESSING,0,json.dumps(job_details))
    pipe.srem(UNIQUE_SET,job_id)

    pipe.execute()

    if reason == "Killed" or reason == "Crashed":
        print("Deleting resources occupied by a killed job")
        session_id = job_details["session_id"]
        user_id = job_details["user_id"]
        repo_id = supabase.table("chat_sessions").select("repository_id").eq("id",session_id).eq("user_id",user_id).single().execute().data["repository_id"]
        repo = supabase.table("repositories").select("n_sessions").eq("id",repo_id).single().execute().data["n_sessions"]
        if repo == 1:
            supabase.table("repositories").delete().eq("id",repo_id).eq("user_id",user_id).execute()
            supabase.table("chat_sessions").delete().eq("id",session_id).execute()
            repo_url = job_details["url"]
            clean_url = repo_url.rstrip("/")

            parts = clean_url.split("/")
            if len(parts) < 2: return None
            owner, repo = parts[-2], parts[-1].removesuffix(".git")
            neo4j_handler = Neo4jHandler()
            neo4j_handler.delete_commit(repo_name=repo,owner_name=owner)
            print("Completed deleting resources from neo4j and supabase")



async def start_worker():
    """
    Job scheduling function. Listens for job calls and execute them one by one
    :return:
    """


    running_processes ={}


    while True:
        current_time = time.time()

        for job_id in list(running_processes.keys()):
            info = running_processes[job_id]
            data = info['data']
            p = info["process"]

            if not p.is_alive():
                if p.exitcode == 0:
                    cleanup_resources(redis_conn,data,reason="Finished")
                else:
                    cleanup_resources(redis_conn,data,reason="Crashed")

                del running_processes[job_id]
                continue
            runtime = current_time - info["start_time"]
            if runtime >= TIMEOUT_SEC:
                print(f"TIMEOUT reached {runtime:.2f}, Killing {job_id}")
                p.terminate()
                p.join()
                cleanup_resources(redis_conn,data,reason="Killed")
                del running_processes[job_id]
        if len(running_processes) < MAX_CONCURRENT_JOBS:
            try:
                data =redis_conn.blmove(MAIN_QUEUE,QUEUE_PROCESSING,timeout=1,src="RIGHT",dest = "LEFT")

                if data:
                    data = json.loads(data)
                    job_id= data["job_id"]

                    p = multiprocessing.Process(target=processing_task_wrapper,args=(data,))
                    p.start()
                    running_processes[job_id] = {
                        "process":p,
                        "start_time":time.time(),
                        "data":data
                    }
                    print(f"started: {job_id} (Active:{len(running_processes)}")
            except Exception as e:
                traceback.print_exc()
                print(f"Encountered error while starting to process job in worker.py as {e}")



if __name__ == "__main__":
    asyncio.run(start_worker())