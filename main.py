import base64
import os
import json
from fastapi import FastAPI, HTTPException, Request,Depends



from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse,StreamingResponse
from fastapi.templating import Jinja2Templates

from dotenv import load_dotenv
from supabase import create_client, Client
from pydantic import BaseModel
import asyncio
import redis.asyncio as aredis
import uvicorn


from ai_engine.graph import GraphBuilder
from ai_engine.chat import generate_response
from helper.commit import get_commit_sha,check_commit_id
from ai_engine.agent import graph
from helper.redis_helper import redis_publish
from ai_engine.qdrant import delete_chunk
from ai_engine.graph_db import Neo4jHandler



# Load environment variables
load_dotenv()
# redis_aconn = aredis.from_url(os.getenv("REDIS_URL"))
redis_aconn = aredis.from_url(os.getenv("REDIS_URL"))
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
base_url = os.getenv("BASE_URL", "http://localhost:7860")

if not supabase_url or not supabase_key:





    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")


app = FastAPI()
supabase: Client = create_client(supabase_url, supabase_key)


























templates = Jinja2Templates(directory="templates")

# app.mount("/static", StaticFiles(directory="static"), name="static")



class RepoRequest(BaseModel):
    url:str

class ChatRequest(BaseModel):
    session_id:int
    text:str


#---------------Auth (Cookie checking)-------------------------------------------

async def get_current_user(request:Request):
    """
    Checks if the user hs a valid session token.
    If yes,returns the User object
    If no,returns None
    :param request:
    :return:
    """

    token = request.cookies.get("access_token","")



    if not token:
        return None
    try:
        user_response = supabase.auth.get_user(token)

        return user_response.user
    except Exception:
        return None

async def require_user(user = Depends(get_current_user)):
    """
    Stops the request if not valid user
    :param user:
    :return:
    """
    if not user:
        raise HTTPException(status_code= 401,detail="Not authenticated")
    return user

# -------------------------------------------------------- ROUTES -----------------------------


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, user = Depends(get_current_user)):
    """
    Renders the Landing Page and passes config data.
    """
    if user:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("index.html", {
        "request": request
    })

@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request, user = Depends(get_current_user)):
    """
    Renders the Dashboard and passes config data.
    """
    if not user:
        return RedirectResponse(url ="/")
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user":user
    })



@app.get("/login/github")
def login_github():
    """
        Generates the GitHub OAuth URL and redirects the user.
    """

    data = supabase.auth.sign_in_with_oauth({
        "provider": "github",
        "options": {
            "redirect_to": f"{base_url}/auth/callback",
            "scopes": "repo user"
        }
    })
    return RedirectResponse(data.url)

@app.get("/auth/callback")
def auth_callback(code:str):

    try:

        res = supabase.auth.exchange_code_for_session({"auth_code":code})


        provider_token = res.session.provider_token

        if provider_token:
            supabase.table("profiles").update({
                "github_token": provider_token
            }).eq("id",res.user.id).execute()



        redirect = RedirectResponse(url ="/dashboard")
        redirect.set_cookie(
            key="access_token",
            value= res.session.access_token,
            httponly=True,
            samesite="lax",
            path="/",
            secure=True
        )
        return redirect
    except Exception as e:
        return HTMLResponse(f"Auth failed :{str(e)}",status_code=400)



@app.get("/logout")
def logout():
    response.delete_cookie("access_token")
    return response


@app.get("/api/sessions")
async def get_sessions(user = Depends(require_user)):
    """Fetch all the conversation from database"""

    response = (supabase.table("chat_sessions").select("*").eq("user_id",user.id).order("created_at",desc=True).execute())





    return {"sessions": response.data}



@app.get("/api/sessions/{session_id}")
async def get_session_history(session_id:int ,user = Depends(require_user)):
    """Fetch the content of chat by session_id"""
    try:
        profile_resp = supabase.table("profiles").select("github_token").eq("id", user.id).single().execute()


        github_token = profile_resp.data.get('github_token')
        commit_info = check_commit_id(session_id = session_id,client = supabase,github_token=github_token)





        graph_data = None
        print(f'commit info received: {commit_info}')

        if not commit_info["is_latest"]:
            ##-------------------------------------------------------BLocking--------------------------------
            job_id = f"{user.id}:{session_id}"

            job_details = {
                "job_id": job_id,
                "url": commit_info["repo_url"],
                "commit_id": commit_info["latest_commit"],
                "is_updated": True
            }

            graph_data = await redis_publish(job_details)
            supabase.table("repositories").update({"latest_commit_id": commit_info["latest_commit"]})






        # -------------------------------load conversation_history -------------------------------
        if not graph_data:

            data = await redis_aconn.get(f"repo_details:{commit_info['repo_url']}")

            if data:
                data = json.loads(data)
                graph_data = {
                    "nodes": data.get("files_list"),
                    "links": data.get("links")
                }
        db_row = supabase.table("chat_messages").select("*").eq("session_id", session_id).execute()




        if not db_row.data:
            return {"messages": [],"graph": graph_data}
        db_row = db_row.data[0]
        encoded_state = db_row.get("state")
        checkpoint_type = db_row.get("checkpoint_type")


        if not encoded_state:
            return {"messages":[],"graph": graph_data}

        state_bytes = base64.b64decode(encoded_state)
        state = graph.checkpointer.serde.loads_typed((checkpoint_type,state_bytes))

        raw_msgs = state.get('channel_values').get("messages",[])

        formatted_msgs = []
        for m in raw_msgs:
            formatted_msgs.append({
                "sender":"ai" if m.type == "ai" else "user",
                "content": m.content
            })

        return {"messages": formatted_msgs,"graph": graph_data}
    except Exception as e:
        print(f"Error fetching session history: {e}")
        raise
@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: int, user=Depends(require_user)):
    try:
        # 1. Fetch the session to get the repo_id
        session_res = supabase.table("chat_sessions").select('repository_id').eq("id", session_id).execute()

        if not session_res.data:
            raise HTTPException(status_code=404, detail="Session not found")

        repo_id = session_res.data[0].get("repository_id")

        # 2. Fetch the repository data
        repo_res = supabase.table("repositories").select("*").eq("id", repo_id).single().execute()


        if not repo_res.data:
            # If repo is already gone, just delete the session
            supabase.table("chat_sessions").delete().eq("id", session_id).execute()

            return {"status": "success", "cleaned_up": False}

        repo_db_row = repo_res.data
        n_session = repo_db_row.get("n_sessions", 0)


        if n_session <= 1:
            # CONDITION: Last session -> Full Cleanup
            repo_full_name = repo_db_row.get("full_name")  # e.g., "https://github.com/user/repo"
            cleaned_url = repo_full_name.strip("/")
            parts = cleaned_url.split("/")

            # Corrected Unpacking: owner is second to last, repo is last
            owner = parts[-2]
            repo = parts[-1].removesuffix(".git")

            # A. Clean Redis (Must be awaited)
            await redis_aconn.delete(f"repo_details:{repo_full_name}")

            # B. Clean Qdrant
            commit_id = repo_db_row.get("latest_commit_id")
            delete_chunk(repo, commit_id)

            # C. Clean Neo4j
            neo4j_handler = Neo4jHandler()
            # Ensure your delete_commit method handles the owner/repo correctly
            neo4j_handler.delete_commit(repo_name=repo, owner_name=owner)
            neo4j_handler.close()

            # D. Delete Repository Record
            supabase.table("repositories").delete().eq("id", repo_id).execute()



        else:
            # CONDITION: Reduce session count
            supabase.table("repositories").update({"n_sessions": n_session - 1}).eq("id", repo_id).execute()


        # 3. Delete the session itself
        supabase.table("chat_sessions").delete().eq("id", session_id).execute()


        print(f"Session {session_id} deleted successfully")
        return {
            "status": "success",
            "cleaned_up": n_session <= 1
        }

    except Exception as e:
        print(f"Error deleting session: {e}")


@app.post("/api/analyze")
async def analyze_repo(request: RepoRequest,user = Depends(require_user)):
    """
    1.Receive repo link
    2. Creates an entry into repo & session table
    3. Initialize the "Processing"(Cloning/Indexing)
    :param request:
    :param user:
    :return:
    """
    profile_resp = supabase.table("profiles").select("github_token").eq("id",user.id).single().execute()
    github_token = profile_resp.data.get('github_token')
    commit_sha = get_commit_sha(repo_url = request.url,github_token=github_token)




    repo_save = {

        "n_name" : request.url.split("/")[-1].replace(".git",""),
        "n_full_name": request.url,
        "n_latest_commit_id": commit_sha
    }
    repo = supabase.rpc("upsert_repo_increment",repo_save).execute()



    repo_id = repo.data["id"]

    session_save = {
        "user_id":user.id,
        "repository_id": repo_id,
        "title": request.url.split("/")[-1].replace(".git","")
    }
    session_res = supabase.table("chat_sessions").insert(session_save).execute()


    session_id = session_res.data[0]["id"]


    if repo.data["new_or_updated"]:

        ##-------------------------------------------------------BLocking--------------------------------
        job_id = f"{user.id}:{session_id}"
        job_details = {
            "job_id": job_id,
            "github_token": github_token,
            "user_id": user.id,
            "commit_id": commit_sha,
            "is_updated" : False
        }
        graph_data = await redis_publish(job_details)
        print(f"graph_data : {graph_data}")
    else:
        graph_builder = GraphBuilder()
        graph_data = await graph_builder.build_repo_graph_frontend(request.url,github_token)



    return {"session_id":session_id,
            "message": "Repo analyzed successfully",
            "graph": graph_data}


@app.post("/api/chat")
async def chat(request: ChatRequest,user = Depends(require_user)):
    """Saves conversation into database"""

    async def event_generator():
        try:

            async for content in generate_response(request.session_id, request.text):
                data = json.dumps({"content": content})
                yield f"data: {data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")



if __name__ == "__main__":

    uvicorn.run(app)