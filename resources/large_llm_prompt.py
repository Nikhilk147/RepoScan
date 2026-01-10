from langchain_core.prompts import PromptTemplate




large_lm_prompt = PromptTemplate.from_message(
    [
    ("user", """
    User query:
    {query}

    Relevant files:
    {paths}

    Code context:
    {context}
    """)]
)