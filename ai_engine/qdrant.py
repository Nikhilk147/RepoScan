from qdrant_client import QdrantClient
from qdrant_client import models
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import os



load_dotenv()
from langchain_text_splitters import RecursiveCharacterTextSplitter

embedding_model = SentenceTransformer(
    'sentence-transformers/all-MiniLM-L6-v2'
)

# qdrant_client = QdrantClient(url = os.getenv("QDRANT_ENDPOINT") ,api_key = os.getenv("QDRANT_API_KEY") )
qdrant_client = QdrantClient(":memory:")


def get_chunk_code():
    return RecursiveCharacterTextSplitter(
        chunk_size = 800,
        chunked_overlap = 150,
        seperaors = [
            "\nclass",
            "\ndef",
            "\nasync",
            "\nif",
            "\nfor",
            "\nwhile",
            "\n",
            " "
        ]
    )



def create_collection():
    if not qdrant_client.collection_exists("repo_knowledge"):
        qdrant_client.create_collection(
            collection_name = "repo_knowledge",
            vectors_config = models.VectorsConfig(
                size = 384,
                distance = models.Distance.COSINE
            ),
            hnsw_config = models.HnswConfig(
                m= 16,
                ef_construct=200,
                full_scan_threshold = 10000,
                on_disk  = True
            ),
            optimizers_config= models.OptimizersConfig(
                indexing_threshold=20000
            )
        )

def embed_text(content:list[str]):
    return embedding_model.encode(
        content,
        show_progress_bar = False,
        normalize_embeddings=True
    ).tolist()

chunker = get_chunk_code()


def ingest_repo(commit_id,code_content,repo_name,path):
    chunks = chunker.split_text(code_content)
    embed_texts = embed_text(chunks)
    for idx, (chunk, embedding) in enumerate(zip(chunks, embed_texts)):
        payload = {
            "repo_name": repo_name,
            "commit_id": commit_id,
            "path": path,
            "text": chunk,
            "language": path.split(".")[-1],
            "chunk_index": idx
        }
def search_chunk(repo_name,commit_id,files,user_query,top_k = 20):
    chunks = []
    q_filter = models.Filter(
        must = [
            models.FieldCondition(
                key= "commit_id",
                match = models.MatchValue(value = commit_id)
            ),
            models.FieldCondition(
                key = "repo_name",
                match = models.MatchValue(value = repo_name)
            ),
            models.FieldCondition(
                key = "path",
                match = models.MatchAny(any = files)
            )
        ]
    )
    embed_query = embed_text(content=user_query)
    output = qdrant_client.query_points(
        collection_name = "repo_knowledge",
        query= embed_query,
        query_filter=q_filter,
        search_params=models.SearchParams(
            hnsw_ef=128,
            exact=False
        ),
        limit = top_k
    )

    return output



