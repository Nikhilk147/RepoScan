from qdrant_client import QdrantClient
from qdrant_client import models
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import os

from transformers.masking_utils import chunked_overlay

load_dotenv()
from langchain_text-spitter import RecursiveTextSpitter

embedding_model = SentenceTransformer(
    'sentence-transformers/all-MiniLM-L6-v2'
)

qdrant_client = QdrantClient(url = os.getenv("QDRANT_ENDPOINT") ,api_key = os.getenv("QDRANT_API_KEY") )

def get_chunk_code(repo_path,content):
    return RecursiveTextSpitter(
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
    qdrant_client.create_collection(
        collection_name = "repo_knowledge",
        vectors_config = models.VectorsConfig(
            size = 384,
            distance = models.Distance.COSINE
        ),
        hnsw_config = models.HnswConfig(
            m= 16,
            ef_construct=200,
            full_scan_threshold = 10000
        ),
        optimizers_config= models.OptimizersConfig(
            indexing_threshold=20000
        )
    )

