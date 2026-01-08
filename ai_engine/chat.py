
#TODO: Import graph build in agent.py file and generate chat response

async def generate_response(session_id:int,text:str):
    response_text = f"Successfully received text:{text} with session_id:{session_id}"
    return response_text