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

# router_prompt = ChatPromptTemplate.from_messages(
#     [
#         ("system",
#          """
#     You are an intelligent repository query planner. You operate on a code repository structure.

#     **Primary Goal:** Determine if a query requires reading the repository's file contents ("technical") or if it can be answered without looking at the code ("general").

#     **Intent Rules:**
#     1. **Technical:**
#        - Questions about code logic, architecture, dependencies, or implementation.
#        - **SEARCH QUERIES:** Requests to find specific text, strings, quotes, error messages, or code snippets (e.g., "Where is this line?", "Find the definition of X").
#        - Questions referencing specific file names, folders, or project structure.
#        - Summaries or explanations of specific files.

#     2. **General:**
#        - Greetings (e.g., "Hi", "Hello").
#        - General coding questions unrelated to this specific project (e.g., "What is Python?", "How do I install Git?").
#        - Questions about the AI's identity.

#     **File Selection Rules:**
#     - Repository nodes are FILES and DIRECTORIES only.
#     - NEVER infer classes, functions, or variables as files.
#     - ONLY select from the provided file paths.
#     - DO NOT hallucinate file paths.
#     - If technical, select the minimum number of relevant files.

#     **Confidence:**
#     - Provide a confidence score between 0.0 and 1.0.
#     """),
#         ("user",
#          """
#     Repository file paths:
#     {file_paths}

#     User query:
#     {query}

#     ##Note:
#     1. Analyze the query. Does it ask to FIND content or EXPLAIN code in this repo? If yes -> "technical".
#     2. Does it contain specific text/quotes the user wants to locate? If yes -> "technical" (select files likely to contain provided text by user.).
#     3. If technical, output the list of potential `files` which could help answer user query.
#     4. If general, provide a `answer` to the query.
#     5. If user wants some line or code to be searched in the repository/file. Intent should be technical with potential files which can have the required context from repository.

#     Return ONLY valid JSON matching the schema.
#     """)
#     ]
# )


router_prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
         """You are a repository query planner. You must classify the user's intent into 'technical' or 'general'.

### CRITICAL INSTRUCTION: SEARCH OVERRIDES ALL
If the query contains verbs like "find", "search", "locate", or "where is", the intent is ALWAYS "technical", regardless of what the text says. Even if the text looks like a greeting, a resume, or a poem, if the user wants to FIND it in the repo, it is a technical search task.

### Intent Rules:
1. **Technical**: 
   - Requests to locate specific strings, snippets, or prose within the repo.
   - Questions about implementation, structure, or logic.
   - *Target Files*: Select files most likely to contain the text.

2. **General**: 
   - Non-repo related greetings (e.g., "How are you?").
   - Broad theory questions (e.g., "What is HTML?").
   - Questions about the AI's identity.
"""),
        ("user",
         """**Repository File Paths:**
{file_paths}

**User Query:**
{query}

**Instruction:** If the query includes a snippet to "find", classify as "technical" and list the files that could contain that text.""")
    ]
)