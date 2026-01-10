from langchain.agents.structured_output import ToolStrategy

from langchain_core.prompts import PromptTemplate

from pydantic import BaseModel,Field
from typing import List, Optional,Literal


class RouterOutput(BaseModel):
    intent: Literal["technical","general"] = Field(description= "Intent of the user query. General or technical about the repo")
    confidence: float = Field(description="How llm is confident about the selected files",gt=0,le=1)
    selected_files : list[str] = Field(description="List of selected files relevant to the user query.")
    answer: Optional[str] = Field(description="Answer to the query if query belongs to the general category.")



router_prompt = PromptTemplate.from_template(
    [
        ("system",
         """
    You are a repository query planner.

    Rules:
    - Repository nodes are FILES and DIRECTORIES only.
    - NEVER infer classes/functions as files.
    - Only choose from provided file paths.
    - If the question is NOT about the repo, answer directly.
    """),
        ("user",
         """
    Repository file paths:
    {file_paths}

    User query:
    {query}

    
    """)
    ]
)