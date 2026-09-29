from langchain_postgres import PGVector
from langchain_voyageai import VoyageAIEmbeddings

from app.core.config import settings
from app.services.embedding import EMBED_MODEL

COLLECTION = "sectors"


def get_embeddings() -> VoyageAIEmbeddings:
    # Same model as Stage 3 (EMBED_MODEL = "voyage-3.5"). Vectors from
    # different models live in different "spaces" and can't be compared.
    return VoyageAIEmbeddings(model=EMBED_MODEL, api_key=settings.voyage_api_key)


def get_vector_store() -> PGVector:
    return PGVector(
        embeddings=get_embeddings(),
        connection=settings.database_url,   # same Postgres, same psycopg driver
        collection_name=COLLECTION,
        embedding_length=1024,              # voyage-3.5 vectors have 1024 numbers
    )
