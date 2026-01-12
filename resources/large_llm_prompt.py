from langchain_core.prompts import ChatPromptTemplate




large_lm_prompt = ChatPromptTemplate.from_messages(
    [
    ("system",
        """
        You are a senior software engineer.
        
        You answer questions using:
        - Provided repository context
        - File paths for grounding
        
        Rules:
        - Cite file paths explicitly when relevant.
        - Do not hallucinate APIs or behavior.
        - If unsure, say so clearly.
        - Prefer concise, technical explanations.
        """),

    ("user",
     """
        Summary of Conversation and last few conversations:
        {old_chat_context}
        
        User query:
        {query}
    
        Relevant files:
        {paths}
    
        Code context:
        {context}
        
        Provide a clear and accurate answer.
    """)]
)