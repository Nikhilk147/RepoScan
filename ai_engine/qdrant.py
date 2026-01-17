import qdrant_client.http.api_client
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

client = QdrantClient(url=os.getenv("QDRANT_ENDPOINT"),api_key=os.getenv("QDRANT_API_KEY"))


def get_chunk_code():
    return RecursiveCharacterTextSplitter(
        chunk_size = 800,
        chunk_overlap = 150,
        separators = [
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
    if not client.collection_exists("repo_knowledge"):
        client.create_collection(
            collection_name = "repo_knowledge",
            vectors_config = models.VectorParams(
                size = 384,
                distance = models.Distance.COSINE
            ),
            hnsw_config = models.HnswConfigDiff(
                m= 16,
                ef_construct=200,
                full_scan_threshold = 10000,
                on_disk  = True
            ),
            optimizers_config= models.OptimizersConfigDiff(
                indexing_threshold=20000,
                deleted_threshold=0.2,
                vacuum_min_vector_number= 1000,
                default_segment_number = 0,
                flush_interval_sec = 10

            )
        )
        client.create_payload_index(
            collection_name="repo_knowledge",
            field_name="commit_id",
            field_schema="keyword"
        )

        # Create keyword index for repo_name
        client.create_payload_index(
            collection_name="repo_knowledge",
            field_name="repo_name",
            field_schema="keyword"
        )

        # Create keyword index for path
        client.create_payload_index(
            collection_name="repo_knowledge",
            field_name="path",
            field_schema="keyword"
        )

def embed_text(content:list[str]):
    return embedding_model.encode(
        content,
        show_progress_bar = False,
        normalize_embeddings=True
    ).tolist()

chunker = get_chunk_code()


# def ingest_repo(commit_id,code_content,repo_name,path):
#     chunks = chunker.split_text(code_content)
#     embed_texts = embed_text(chunks)
#     points = []
#     for idx, (chunk, embedding) in enumerate(zip(chunks, embed_texts)):
#         payload = {
#             "repo_name": repo_name,
#             "commit_id": commit_id,
#             "path": path,
#             "text": chunk,
#             "language": path.split(".")[-1],
#             "chunk_index": idx
#         }
#         point = models.PointStruct(
#             id = idx,
#             payload = payload,
#             vector = embedding
#         )
#         points.append(point)
#     qdrant_client.upsert(
#         collection_name = "repo_knowledge",
#         points = points
#     )

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
    output = client.query_points(
        collection_name = "repo_knowledge",
        query= embed_query,
        query_filter=q_filter,
        search_params=models.SearchParams(
            hnsw_ef=128,
            exact=False
        ),
        limit = top_k
    )
    print(f"Search chunk function in qdrant output: {output}")

    return output

def delete_chunk(repo_name:str,commit_id:str):
    """
    Delete all the chunk with the specified repo_name and commit_id
    :param repo_name:
    :param commit_id:
    :return:
    """
    client.delete(
        collection_name="repo_knowledge",
        points_selector= models.FilterSelector(
            filter = models.Filter(
                must = [
                    models.FieldCondition(
                        key = "repo_name",
                        match = models.MatchValue(value = repo_name)
                    ),
                    models.FieldCondition(
                        key = "commit_id",
                        match = models.MatchValue(value = commit_id)
                    )
                ]
            )
        )
    )
