import base64
import os
import redis
import json
from dotenv import load_dotenv
load_dotenv()
redis_conn = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
#TODO: Import graph build in agent.py file and generate chat response
from supabase import create_client,Client
from ai_engine.agent import graph
supabase:Client = create_client(os.getenv("SUPABASE_URL"),os.getenv("SUPABASE_KEY"))


async def generate_response(session_id:int,text:str):
    history = supabase.table("chat_messages").select("*").eq("session_id",session_id).execute()
    print(history)
    if  len(history.data) == 0:
        repo_id = supabase.table("chat_sessions").select("repository_id").eq("id", session_id).single().execute()
        repo_url = supabase.table("repositories").select("full_name").eq("id",repo_id.data["repository_id"]).execute()
        repo_details = redis_conn.get(f"repo_details:{repo_url.data[0]["full_name"]}")
        repo_details = json.loads(repo_details)
        state = {
            "commit_id": repo_details["commit_id"],
            "repo_name":repo_details["repo_name"],
            "files_path": [node["path"] for node in repo_details["files_list"]],
            "user_query": text
        }
    else:
        db_row = history.data[0]
        encoded_state = db_row.get("state")
        checkpoint_type = db_row.get("checkpoint_type")
        state_bytes = base64.b64decode(encoded_state)
        state = graph.checkpointer.serde.loads_typed((checkpoint_type, state_bytes))
        state["user_query"] = text


    config = {
        "configurable": {"thread_id": session_id}
    }
    state["final_answer"] = None
    async for event in graph.astream(state,config = config,stream_mode = "values"):
        answer = event.get("final_answer")
        if answer and answer.strip():
            yield answer