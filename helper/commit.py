from supabase import create_client,Client
import requests
import os

from dotenv import load_dotenv
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(supabase_url, supabase_key)
def get_commit_sha(repo_url,github_token):
    """
    Returns commit sha for repo_url for default branch
    :param repo_url:
    :param github_token:
    :return:
    """
    clean_url = repo_url.rstrip("/")
    parts = clean_url.split("/")
    if len(parts) < 2: return None
    owner, repo = parts[-2], parts[-1].removesuffix(".git")

    branch_url = f"https://api.github.com/repos/{owner}/{repo}"
    header = {
        "Accept": "application/vnd.github+json",
    }
    if github_token:
        header["Authorization"] = f"Bearer {github_token}"

    default_branch = requests.get(branch_url,headers=header).json()["default_branch"]

    commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{default_branch}"

    commit_sha = requests.get(commit_url,headers=header).json()["sha"]

    return commit_sha


def check_commit_id(session_id,client, github_token ):
    repo_id = client.table("chat_sessions").select("repository_id").eq("id",session_id).single().execute()
    repo = client.table("repositories").select("full_name","latest_commit_id").eq("id",repo_id.data["repository_id"]).single().execute()
    repo_url = repo.data["full_name"]
    db_sha = repo.data["latest_commit_id"]

    github_sha = get_commit_sha(repo_url, github_token=github_token)

    if db_sha == github_sha:
        response_json = {
            "is_latest": True,
            "repo_url": repo_url,
        }
        return response_json
    else:
        response_json = {
            "is_latest": False,
            "repo_url" : repo_url,
            "latest_commit": github_sha

        }
        return response_json




