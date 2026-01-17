
from langchain_core.prompts import ChatPromptTemplate
summary_prompt = ChatPromptTemplate.from_messages([
    ('system',
    f"""
    You are summarizing a technical conversation.

    Rules:
    - Preserve technical details.
    - Preserve unresolved questions.
    - Preserve user intent.
    - Do not add new information.
    """),
    ('user',"""
        Existing summary:{summary}

        New conversation: 
        {last_messages}

        Return a concise summary. 
    """)])
