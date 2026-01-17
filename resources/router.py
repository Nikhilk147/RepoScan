from langchain.agents.structured_output import ToolStrategy
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel,Field
from typing import List, Optional,Literal


class RouterOutput(BaseModel):
    intent: Literal["technical","general"] = Field(description= "Intent of the user query. General or technical about the repo")
    confidence: float = Field(description="How llm is confident about the selected files",gt=0,le=1)
    files : list[str] = Field(description="List of selected files relevant to the user query.")
    answer: Optional[str] = Field(description="Answer to the query if query belongs to the general category.")


# for future optimizations
# class SelectedFile(BaseModel):
#     path: str
#     confidence: float  = Field(description="How llm is confident about the selected files",gt=0,le=1)
#
# class RouterOutput(BaseModel):
#     intent: Literal["general", "technical"]
#     confidence: float = Field(description="How llm is confident about the selected files",gt=0,le=1)
#     files: list[SelectedFile] = []
#     answer: Optional[str] = None

router_prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
         """
    You are a repository query planner.

    You operate on a code repository.
    
    Rules:
    - Repository nodes are FILES and DIRECTORIES only.
    - NEVER infer classes, functions, or variables as files.
    - ONLY select from the provided file paths.
    - DO NOT hallucinate file paths.
    - If the query is not about the repository, classify it as "general".
    - If technical, select the minimum number of relevant files.
    - Provide a confidence score between 0.0 and 1.0.
    """),
        ("user",
         """
    Repository file paths:
    {file_paths}
    
    User query:
    {query}
    
    Decide:
    1. Is the intent "general" or "technical"?
    2. If technical, which files are relevant?
    3. Provide a confidence score per file.
    4. If general, provide a direct answer.
    5. Intent should be technical if query is about repository and need repository details to answer.
    Return ONLY valid JSON matching the schema.

    
    """)
    ]
)