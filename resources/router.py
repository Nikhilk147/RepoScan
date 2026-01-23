from langchain.agents.structured_output import ToolStrategy
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel,Field
from typing import List, Optional,Literal


class RouterOutput(BaseModel):
    intent: Literal["technical","general"] = Field(description= "Intent of the user query. General or technical about the repo")
    confidence: float = Field(description="How llm is confident about the selected files",ge=0,le=1)
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
    You are an intelligent repository query planner. You operate on a code repository structure.

    **Primary Goal:** Determine if a query requires reading the repository's file contents ("technical") or if it can be answered without looking at the code ("general").

    **Intent Rules:**
    1. **Technical:**
       - Questions about code logic, architecture, dependencies, or implementation.
       - **SEARCH QUERIES:** Requests to find specific text, strings, quotes, error messages, or code snippets (e.g., "Where is this line?", "Find the definition of X").
       - Questions referencing specific file names, folders, or project structure.
       - Summaries or explanations of specific files.

    2. **General:**
       - Greetings (e.g., "Hi", "Hello").
       - General coding questions unrelated to this specific project (e.g., "What is Python?", "How do I install Git?").
       - Questions about the AI's identity.

    **File Selection Rules:**
    - Repository nodes are FILES and DIRECTORIES only.
    - NEVER infer classes, functions, or variables as files.
    - ONLY select from the provided file paths.
    - DO NOT hallucinate file paths.
    - If technical, select the minimum number of relevant files.

    **Confidence:**
    - Provide a confidence score between 0.0 and 1.0.
    """),
        ("user",
         """
    Repository file paths:
    {file_paths}

    User query:
    {query}

    **Task:**
    1. Analyze the query. Does it ask to FIND content or EXPLAIN code in this repo? If yes -> "technical".
    2. Does it contain specific text/quotes the user wants to locate? If yes -> "technical" (select files likely to contain text, like .md, .txt, .html, or source code).
    3. If technical, output the list of relevant `files`.
    4. If general, provide a `answer`.

    Return ONLY valid JSON matching the schema.
    """)
    ]
)