import base64
import os
import json
from fastapi import FastAPI, HTTPException, Request,Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse,StreamingResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from starlette.routing import request_response
from supabase import create_client, Client
from pydantic import BaseModel
import asyncio
import redis.asyncio as aredis
import uvicorn
from ai_engine.graph import GraphBuilder
from ai_engine.chat import generate_response
from helper.commit import get_commit_sha,check_commit_id
from ai_engine.agent import graph

# Load environment variables
load_dotenv()

#TODO: Integrate with chat_response
#TODO: MAke sure that messages are in the form Message Format
#TODO : Integrate with Langgraph persistence format
#TODO: include a commit id check if it doesn't match, initiate the graph building.Replace the existing graph


supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")


app = FastAPI()
supabase: Client = create_client(supabase_url, supabase_key)
redis_aconn = aredis.from_url(os.getenv("REDIS_URL"))


templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

MAIN_QUEUE = "repo_tasks"
UNIQUE_SET = "repo_task:unique_set"
MAX_QUEUE_SIZE = 100

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
# ----------------------------------------------redis---------------------------------------------

async def push_to_redis(job_data):
    current_size = await redis_aconn.llen(MAIN_QUEUE)
    if current_size >= MAX_QUEUE_SIZE:
        print(f"REJECTED: Queue is full: {current_size}")
        return False
    job_id = job_data["job_id"]
    if await redis_aconn.sadd(UNIQUE_SET,job_id) ==0:
        print(f"IGNORED: Job {job_id} already queued")
        return False

    payload = json.dumps(job_data)
    await redis_aconn.lpush(MAIN_QUEUE,payload)
    print("Queued successfully...")
    return True



# --- ROUTES ---

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
            "redirect_to": "http://localhost:8000/auth/callback",
            "scopes": "repo user"
        }
    })
    return RedirectResponse(data.url)

@app.get("/auth/callback")
def auth_callback(code:str):
    is_production = os.getenv("ENVIRONMENT") == "production"
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
            secure=False
        )
        return redirect
    except Exception as e:
        return HTMLResponse(f"Auth failed :{str(e)}",status_code=400)

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response

#----------------------------Auth flow ------------------------------------

@app.get("/api/sessions")
async def get_sessions(user = Depends(require_user)):
    """Fetch all the conversation from database"""

    response = (supabase.table("chat_sessions").select("*").eq("user_id",user.id).order("created_at",desc=True).execute())
    return {"sessions": response.data}



@app.get("/api/sessions/{session_id}")
async def get_session_history(session_id:int ,user = Depends(require_user)):
    """Fetch the content of chat by session_id"""

    profile_resp = supabase.table("profiles").select("github_token").eq("id", user.id).single().execute()
    github_token = profile_resp.data.get('github_token')
    commit_info = check_commit_id(session_id = session_id,client = supabase,github_token=github_token)

    if not commit_info["is_latest"]:
        ##-------------------------------------------------------BLocking--------------------------------
        job_id = f"{user.id}:{session_id}"

        job_details = {
            "job_id": job_id,
            "url": commit_info["repo_url"],
            "session_id": session_id,
            "github_token": github_token,
            "user_id": user.id,
        }

        pubsub = redis_aconn.pubsub()
        channel_name = f"job_status:{job_id}"
        await pubsub.subscribe(channel_name)
        try:
            await push_to_redis(job_details)
            print(f"Waiting for the job to complete:{job_id}")
            async with asyncio.timeout(1000):
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = json.loads(message["data"])
                        if data["status"] == "completed":
                            graph_data = data["graph_data"]
                            break
                        if data["status"] == "failed":
                            raise HTTPException(status_code=500, detail=f"Job failed to execute :{job_id}")
            supabase.table("repositories").update({"latest_commit_id":commit_info["latest_commit"]})
        except asyncio.TimeoutError:
            print("Job timeout reached")
            raise HTTPException(status_code=504, detail=f"Analyze timeout(worker took too long)")
        finally:
            await pubsub.unsubscribe(channel_name)
            await redis_aconn.aclose()

    db_row = supabase.table("chat_messages").select("*").eq("session_id",session_id).execute()
    print(f"Output of db_row :{db_row}")
    if not db_row.data:
        return {"messages": []}
    db_row = db_row.data[0]
    encoded_state = db_row.get("state")
    checkpoint_type = db_row.get("checkpoint_type")
    print(f"encoded_state: {encoded_state}")
    if not encoded_state:
        return {"messages":[]}
    state_bytes = base64.b64decode(encoded_state)
    state = graph.checkpointer.serde.loads_typed((checkpoint_type,state_bytes))
    print(f"state: {state}")
    raw_msgs = state.get('channel_values').get("messages",[])
    print(f"raw messages received from supabase in main.py{raw_msgs}")
    formatted_msgs = []
    for m in raw_msgs:
        formatted_msgs.append({
            "sender":"ai" if m.type == "ai" else "user",
            "content": m.content
        })
    return {"messages": formatted_msgs}


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
            "url": request.url,
            "session_id": session_id,
            "github_token": github_token,
            "user_id": user.id,
        }

        pubsub = redis_aconn.pubsub()
        channel_name = f"job_status:{job_id}"
        await pubsub.subscribe(channel_name)
        try:
            await push_to_redis(job_details)
            print(f"Waiting for the job to complete:{job_id}")
            async with asyncio.timeout(1000):
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = json.loads(message["data"])
                        if data["status"] == "completed":
                            graph_data = data["graph_data"]
                            break
                        if data["status"] == "failed":
                            raise HTTPException(status_code = 500, detail = f"Job failed to execute :{job_id}")
        except asyncio.TimeoutError:
            print("Job timeout reached")
            raise HTTPException(status_code = 504,detail=f"Analyze timeout(worker took too long)")
        finally:
            await pubsub.unsubscribe(channel_name)
            await redis_aconn.aclose()
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
            # Iterate through the generator from chat.py
            async for content in generate_response(request.session_id, request.text):
                # We wrap the string in JSON so the frontend can parse it safely
                data = json.dumps({"content": content})
                yield f"data: {data}\n\n"
        except Exception as e:
            error_data = json.dumps({"error": str(e)})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")



if __name__ == "__main__":


    # Use host="0.0.0.0" to make it accessible if testing from other devices
    uvicorn.run(app, port=8000)