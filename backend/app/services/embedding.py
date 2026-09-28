import voyageai

from app.core.config import settings

voyage = voyageai.Client(api_key=settings.voyage_api_key)
EMBED_MODEL = "voyage-3.5"


def embed_query(text: str) -> list[float]:
    # TODO: call voyage.embed([text], model=EMBED_MODEL, input_type="query")
    # and return the single vector (result.embeddings[0]).
    # Note "query", not "document": this is the search side.
    ...
