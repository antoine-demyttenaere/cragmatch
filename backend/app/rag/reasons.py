from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.rag.llm import UsageLogger, get_chat_model


# The shape we ask Claude to return. These live here, not in schemas/,
# because they're never sent to API clients; they're only the format
# of Claude's answer inside the reasons chain.
class MatchReason(BaseModel):
    sector_id: int
    reason: str = Field(description="One short sentence explaining the match.")


class MatchReasons(BaseModel):
    reasons: list[MatchReason]


REASONS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You explain why climbing sectors match a user's search.
You get the search text and a list of sectors, each with an id and its details.
For every sector, write ONE short sentence (max ~20 words) saying why it fits
the search. Use ONLY the details given for that sector; do not add facts from
your own knowledge about these places. If a sector only partly fits, say so
honestly (e.g. "Short approach, but it can get crowded").""",
        ),
        ("human", "Search: {query}\n\nSectors:\n{sectors}"),
    ]
)


def format_sectors(docs: list[Document]) -> str:
    # The id is how Claude's answer is matched back to a sector
    # (format_docs in chain.py has no ids, so it can't be reused here).
    return "\n".join(f"id={doc.metadata['sector_id']} | {doc.page_content}" for doc in docs)


def build_reasons_chain(llm: BaseChatModel) -> Runnable:
    # json_schema is the same API feature as Stage 3's output_format; the default
    # forced tool call doesn't work with Sonnet 5's default thinking.
    # Input: {"query": str, "sectors": str}. Output: a MatchReasons instance.
    # The callback brings back the token log that explain_matches() had. Callbacks
    # set with with_config reach every step inside the chain, including the model.
    chain = REASONS_PROMPT | llm.with_structured_output(MatchReasons, method="json_schema")
    return chain.with_config(callbacks=[UsageLogger("reasons")])


@lru_cache(maxsize=1)
def get_reasons_chain() -> Runnable:
    # One Anthropic client per process, like services/llm.py. lru_cache doesn't
    # cache exceptions, so a failed build is retried on the next call.
    return build_reasons_chain(get_chat_model())
