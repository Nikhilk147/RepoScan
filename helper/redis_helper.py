import os
import redis.asyncio as aredis
from dotenv import load_dotenv
import asyncio
import json
from fastapi import HTTPException
load_dotenv()
redis_aconn = aredis.from_url(os.getenv("REDIS_URL"))

MAIN_QUEUE = "repo_tasks"
UNIQUE_SET = "repo_task:unique_set"
MAX_QUEUE_SIZE = 100


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


async def redis_publish(job_details):
    """
    Publish job into pub-sub channel
    :param job_details:
    :return:
    """
    job_id = job_details["job_id"]
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

    except asyncio.TimeoutError:
        print("Job timeout reached")
        raise HTTPException(status_code=504, detail=f"Analyze timeout(worker took too long)")
    finally:
        await pubsub.unsubscribe(channel_name)

    return graph_data