"""Natural-language query to ParsedFilters: the LangChain version of Stage 3's parsing.

Same prompt and same ParsedFilters schema as Stage 3; only the plumbing changes.
"""

from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.rag.llm import UsageLogger, get_chat_model
from app.schemas.search import ParsedFilters

# No { or } allowed in this text: it goes into a prompt template, where they
# would become variables.
PARSE_SYSTEM_PROMPT = """You extract structured climbing search filters from a
natural-language request. The user is in Barcelona, Catalonia, looking for
climbing sectors.
- understood: set this to false if the query has nothing to do with finding
  a climbing sector — no grade, location, distance, or style hint at all
  (e.g. off-topic questions, gibberish, or requests unrelated to climbing).
  Otherwise true, even for vague-but-real requests like "something easy
  near Barcelona".
  Example — understood=false: "what is your favorite color", "asdf asdf",
  "tell me a joke". These have zero climbing content, even if grammatically
  well-formed questions.
- min_grade / max_grade: French climbing grades. Grades 1-5 are a plain
  number with an optional "+" (e.g. "3", "4+", "5"), with NO letter.
  Grades 6-9 always have a letter a/b/c and an optional "+" (e.g. "6a",
  "6a+", "7c+"). Never combine a number 1-5 with a letter. If the user
  doesn't mention a grade, use "4" to "9c+".
- max_distance_km: a straight-line distance in km from Barcelona. If the user
  gives a travel time instead (e.g. "1.5 hours"), convert it assuming
  mountain-road driving at roughly 80 km/h average, then round sensibly.
  If nothing is mentioned, use 200.
- style: "sport", "boulder", "trad", or "multi-pitch" if mentioned, otherwise
  null.
"""

PARSE_PROMPT = ChatPromptTemplate.from_messages(
    [("system", PARSE_SYSTEM_PROMPT), ("human", "{query}")]
)


def build_parse_chain(llm: BaseChatModel) -> Runnable:
    # json_schema is the same API feature as Stage 3's output_format; the default
    # forced tool call doesn't work with Sonnet 5's default thinking. The field
    # descriptions of ParsedFilters travel in the schema and act as instructions.
    # Input: {"query": str}. Output: a ParsedFilters instance.
    chain = PARSE_PROMPT | llm.with_structured_output(ParsedFilters, method="json_schema")
    return chain.with_config(callbacks=[UsageLogger("natural_search")])


@lru_cache(maxsize=1)
def get_parse_chain() -> Runnable:
    # Build the ChatAnthropic model (get_chat_model()) once per process.
    # lru_cache doesn't cache exceptions, so a failed build is retried on the next call.
    return build_parse_chain(get_chat_model())
