import base64
import os
import json
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from supabase import create_client, Client
from pydantic import BaseModel
import redis.asyncio as aredis
import uvicorn

# --- Custom Modules ---
from ai_engine.graph import GraphBuilder
from ai_engine.chat import generate_response
from helper.commit import get_commit_sha, check_commit_id
from ai_engine.agent import graph
from helper.redis_helper import redis_publish
from ai_engine.qdrant import delete_chunk
from ai_engine.graph_db import Neo4jHandler

# 1. Load Environment
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
REDIS_URL = os.getenv("REDIS_URL")
BASE_URL = os.getenv("BASE_URL", "http://localhost:7860")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
redis_aconn = None  


@asynccontextmanager
async def lifespan(app: FastAPI):
    
    global redis_aconn
    redis_aconn = aredis.from_url(REDIS_URL, decode_responses=True)
    print("Redis connected.")
    yield
    # Shutdown
    if redis_aconn:
        await redis_aconn.close()
        print("Redis connection closed.")

app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


templates = Jinja2Templates(directory="templates")

# app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Models ---
class RepoRequest(BaseModel):
    url: str

class ChatRequest(BaseModel):
    session_id: int
    text: str


# --- Auth Dependencies ---

async def get_current_user(request: Request):
    token = request.cookies.get("access_token", "")
    if not token:
        return None
    try:
        
        user_response = await asyncio.to_thread(supabase.auth.get_user, token)
        return user_response.user
    except Exception:
        return None

async def require_user(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------------- Routes ----------------

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/")
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user
    })

@app.get("/login/github")
async def login_github():
    
    data = await asyncio.to_thread(
        supabase.auth.sign_in_with_oauth,
        {
            "provider": "github",
            "options": {
                "redirect_to": f"{BASE_URL}/auth/callback",
                "scopes": "repo user"
            }
        }
    )
    return RedirectResponse(data.url)

@app.get("/auth/callback")
async def auth_callback(code: str):
    try:
        
        res = await asyncio.to_thread(
            supabase.auth.exchange_code_for_session, {"auth_code": code}
        )
        provider_token = res.session.provider_token
        
        if provider_token:
            await asyncio.to_thread(
                lambda: supabase.table("profiles").update({
                    "github_token": provider_token
                }).eq("id", res.user.id).execute()
            )

        redirect = RedirectResponse(url="/dashboard")
        redirect.set_cookie(
            key="access_token",
            value=res.session.access_token,
            httponly=True,
            samesite="lax",
            path="/",
            secure=True 
        )
        return redirect
    except Exception as e:
        return HTMLResponse(f"Auth failed: {str(e)}", status_code=400)

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response

@app.get("/api/sessions")
async def get_sessions(user=Depends(require_user)):
   
    response = await asyncio.to_thread(
        lambda: supabase.table("chat_sessions")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return {"sessions": response.data}

@app.get("/api/sessions/{session_id}")
async def get_session_history(session_id: int, user=Depends(require_user)):
    try:
        profile_resp = await asyncio.to_thread(
            lambda: supabase.table("profiles").select("github_token").eq("id", user.id).single().execute()
        )
        github_token = profile_resp.data.get('github_token')
        
        
        commit_info = await asyncio.to_thread(
            check_commit_id, session_id, supabase, github_token
        )
        
        graph_data = None
        print(f'commit info received: {commit_info}')
        
        if not commit_info["is_latest"]:
            job_id = f"{user.id}:{session_id}"
            job_details = {
                "job_id": job_id,
                "url": commit_info["repo_url"],
                "session_id": session_id,
                "github_token": github_token,
                "user_id": user.id,
                "commit_id": commit_info["latest_commit"],
                "is_updated": True
            }
           
            graph_data = await redis_publish(job_details)
            
            await asyncio.to_thread(
                lambda: supabase.table("repositories").update({
                    "latest_commit_id": commit_info["latest_commit"]
                }).execute()
            )

        if not graph_data:
            data = await redis_aconn.get(f"repo_details:{commit_info['repo_url']}")
            if data:
                data = json.loads(data)
                graph_data = {
                    "nodes": data.get("files_list"),
                    "links": data.get("links")
                }
        
        db_row = await asyncio.to_thread(
            lambda: supabase.table("chat_messages").select("*").eq("session_id", session_id).execute()
        )
        
        if not db_row.data:
            return {"messages": [], "graph": graph_data}
            
        data = db_row.data[0]
        encoded_state = data.get("state")
        checkpoint_type = data.get("checkpoint_type")

        if not encoded_state:
            return {"messages": [], "graph": graph_data}
            
        state_bytes = base64.b64decode(encoded_state)
        # Graph loading might be CPU intensive, ok to leave here or wrap if very slow
        state = graph.checkpointer.serde.loads_typed((checkpoint_type, state_bytes))
        raw_msgs = state.get('channel_values', {}).get("messages", [])

        formatted_msgs = []
        for m in raw_msgs:
            formatted_msgs.append({
                "sender": "ai" if m.type == "ai" else "user",
                "content": m.content
            })

        return {"messages": formatted_msgs, "graph": graph_data}
    except Exception as e:
        print(f"Error fetching session history: {e}")
        raise

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: int, user=Depends(require_user)):
    try:
        session_res = await asyncio.to_thread(
            lambda: supabase.table("chat_sessions").select('repository_id').eq("id", session_id).execute()
        )
        if not session_res.data:
            raise HTTPException(status_code=404, detail="Session not found")

        repo_id = session_res.data[0].get("repository_id")

        repo_res = await asyncio.to_thread(
            lambda: supabase.table("repositories").select("*").eq("id", repo_id).single().execute()
        )
        
        if not repo_res.data:
            await asyncio.to_thread(
                lambda: supabase.table("chat_sessions").delete().eq("id", session_id).execute()
            )
            return {"status": "success", "cleaned_up": False}

        repo_db_row = repo_res.data
        n_session = repo_db_row.get("n_sessions", 0)

        cleaned_up = False
        if n_session <= 1:
            cleaned_up = True
            repo_full_name = repo_db_row.get("full_name")
            cleaned_url = repo_full_name.strip("/")
            parts = cleaned_url.split("/")
            owner = parts[-2]
            repo = parts[-1].removesuffix(".git")

            await redis_aconn.delete(f"repo_details:{repo_full_name}")
            
            commit_id = repo_db_row.get("latest_commit_id")
            
            await asyncio.to_thread(delete_chunk, repo, commit_id)

            def clean_neo4j():
                neo4j_handler = Neo4jHandler()
                neo4j_handler.delete_commit(repo_name=repo, owner_name=owner)
                neo4j_handler.close()
            
            await asyncio.to_thread(clean_neo4j)

            await asyncio.to_thread(
                lambda: supabase.table("repositories").delete().eq("id", repo_id).execute()
            )
        else:
            await asyncio.to_thread(
                lambda: supabase.table("repositories").update({"n_sessions": n_session - 1}).eq("id", repo_id).execute()
            )

        await asyncio.to_thread(
            lambda: supabase.table("chat_sessions").delete().eq("id", session_id).execute()
        )

        return {"status": "success", "cleaned_up": cleaned_up}

    except Exception as e:
        print(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
async def analyze_repo(request: RepoRequest, user=Depends(require_user)):
    profile_resp = await asyncio.to_thread(
        lambda: supabase.table("profiles").select("github_token").eq("id", user.id).single().execute()
    )
    github_token = profile_resp.data.get('github_token')
    
    commit_sha = await asyncio.to_thread(
        get_commit_sha, request.url, github_token
    )
    
    repo_save = {
        "n_name": request.url.split("/")[-1].replace(".git", ""),
        "n_full_name": request.url,
        "n_latest_commit_id": commit_sha
    }
    
    repo = await asyncio.to_thread(
        lambda: supabase.rpc("upsert_repo_increment", repo_save).execute()
    )
    repo_id = repo.data["id"]
    
    session_save = {
        "user_id": user.id,
        "repository_id": repo_id,
        "title": request.url.split("/")[-1].replace(".git", "")
    }
    session_res = await asyncio.to_thread(
        lambda: supabase.table("chat_sessions").insert(session_save).execute()
    )
    session_id = session_res.data[0]["id"]
    
    graph_data = None
    if repo.data["new_or_updated"]:
        job_id = f"{user.id}:{session_id}"
        job_details = {
            "job_id": job_id,
            "url": request.url,
            "session_id": session_id,
            "github_token": github_token,
            "user_id": user.id,
            "commit_id": commit_sha,
            "is_updated": False
        }
        graph_data = await redis_publish(job_details)
    else:
        graph_builder = GraphBuilder()
        
        graph_data = await graph_builder.build_repo_graph_frontend(request.url, github_token)

    return {
        "session_id": session_id,
        "message": "Repo analyzed successfully",
        "graph": graph_data
    }

@app.post("/api/chat")
async def chat(request: ChatRequest, user=Depends(require_user)):
    async def event_generator():
        try:
            async for content in generate_response(request.session_id, request.text):
                data = json.dumps({"content": content})
                yield f"data: {data}\n\n"
        except Exception as e:
            error_data = json.dumps({"error": str(e)})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    
    uvicorn.run(app, host="0.0.0.0", port=7860)