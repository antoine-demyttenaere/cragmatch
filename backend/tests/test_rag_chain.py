"""app/rag chain tests. No network: retriever and model are RunnableLambda fakes."""

import logging

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from app.core.config import settings
from app.rag import query_parsing, reasons
from app.rag.chain import build_rag_chain, format_docs
from app.rag.llm import get_chat_model
from app.rag.query_parsing import PARSE_SYSTEM_PROMPT, build_parse_chain, get_parse_chain
from app.rag.reasons import (
    MatchReason,
    MatchReasons,
    build_reasons_chain,
    format_sectors,
    get_reasons_chain,
)
from app.schemas.search import ParsedFilters
from app.scripts import rag_playground
from app.services.llm import LLM_MODEL

USAGE = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
CLEAR = ParsedFilters(
    understood=True, min_grade="6b", max_grade="6b", max_distance_km=200, style="sport"
)


def make_docs() -> list[Document]:
    return [
        Document(page_content="first text", metadata={"name": "Poble", "crag": "Siurana"}),
        Document(page_content="second text", metadata={"name": "Grau", "crag": "Margalef"}),
    ]


def test_chat_model_uses_llm_model_and_settings_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    model = get_chat_model()

    assert model.model == LLM_MODEL
    assert model.anthropic_api_key.get_secret_value() == "test-key"


def test_chat_model_has_timeout_retries_and_max_tokens(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    model = get_chat_model()
    assert model.default_request_timeout == 20.0
    assert model.max_retries == 2
    assert model.max_tokens == 1024

    assert get_chat_model(max_tokens=300).max_tokens == 300


def test_format_docs_joins_in_order_with_blank_lines():
    assert format_docs(make_docs()) == "first text\n\nsecond text"


def test_format_docs_empty_is_empty_string():
    assert format_docs([]) == ""


def test_rag_chain_fills_prompt_and_returns_string():
    queries = []
    prompts = []

    def fake_retrieve(query):
        queries.append(query)
        return make_docs()

    def fake_llm(prompt_value):
        prompts.append(prompt_value)
        return AIMessage(content="Try Poble.", usage_metadata=USAGE)

    chain = build_rag_chain(RunnableLambda(fake_retrieve), RunnableLambda(fake_llm))
    answer = chain.invoke("beginner crag")

    assert answer == "Try Poble."
    assert queries == ["beginner crag"]
    system, human = prompts[0].to_messages()
    assert "first text" in system.content
    assert "second text" in system.content
    assert human.content == "beginner crag"


def test_step_6_5_prints_each_stage_and_calls_retriever_twice(monkeypatch, capsys):
    retriever_calls = []

    def fake_retrieve(query):
        retriever_calls.append(query)
        return make_docs()

    class FakeStore:
        def as_retriever(self, **kwargs):
            return RunnableLambda(fake_retrieve)

    fake_llm = RunnableLambda(lambda _: AIMessage(content="Try Poble.", usage_metadata=USAGE))
    monkeypatch.setattr(rag_playground, "get_vector_store", lambda: FakeStore())
    monkeypatch.setattr(rag_playground, "get_chat_model", lambda: fake_llm)

    rag_playground.step_6_5()

    output = capsys.readouterr().out
    assert len(retriever_calls) == 2
    assert "Poble" in output and "Grau" in output
    # Only the (b) part prints the filled system prompt.
    assert "Answer using ONLY" in output
    assert "Sectors:\nfirst text\n\nsecond text" in output
    assert "quiet crag with a short approach" in output
    assert "AIMessage" in output and "input_tokens" in output
    assert "after StrOutputParser ===\nTry Poble." in output
    assert "the composed chain, same query ===\nTry Poble." in output


class FakeStructuredModel:
    """Stands in for ChatAnthropic: records with_structured_output and the prompt."""

    def __init__(self, answer: BaseModel | None = None) -> None:
        self.answer = answer or MatchReasons(
            reasons=[MatchReason(sector_id=1, reason="Short approach.")]
        )
        self.schema = None
        self.kwargs: dict = {}
        self.prompts: list = []

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        self.kwargs = kwargs

        def respond(prompt_value):
            self.prompts.append(prompt_value)
            return self.answer

        return RunnableLambda(respond)


@pytest.fixture
def clean_reasons_cache():
    # A fake must never stay cached for later tests.
    get_reasons_chain.cache_clear()
    yield
    get_reasons_chain.cache_clear()


@pytest.fixture
def clean_parse_cache():
    get_parse_chain.cache_clear()
    yield
    get_parse_chain.cache_clear()


def test_format_sectors_prefixes_each_doc_with_its_sector_id():
    docs = [
        Document(page_content="first text", metadata={"sector_id": 1}),
        Document(page_content="second text", metadata={"sector_id": 2}),
    ]

    assert format_sectors(docs) == "id=1 | first text\nid=2 | second text"


def test_reasons_chain_fills_prompt_and_asks_for_json_schema():
    fake = FakeStructuredModel()

    answer = build_reasons_chain(fake).invoke(
        {"query": "short approach", "sectors": "id=1 | first text"}
    )

    assert answer == MatchReasons(reasons=[MatchReason(sector_id=1, reason="Short approach.")])
    assert fake.schema is MatchReasons
    assert fake.kwargs["method"] == "json_schema"
    system, human = fake.prompts[0].to_messages()
    assert "Use ONLY the details given" in system.content
    assert human.content == "Search: short approach\n\nSectors:\nid=1 | first text"


class FakeJsonModel:
    """A real chat model (so it fires on_llm_end) that answers with fixed JSON.

    The RunnableLambda fakes never reach the callbacks. This builds the same
    model | PydanticOutputParser pair ChatAnthropic builds for json_schema, offline.
    """

    def __init__(self, json_text: str) -> None:
        self.json_text = json_text

    def with_structured_output(self, schema, **kwargs):
        model = GenericFakeChatModel(
            messages=iter([AIMessage(content=self.json_text, usage_metadata=USAGE)])
        )
        return model | PydanticOutputParser(pydantic_object=schema)


def test_reasons_chain_logs_token_usage(caplog):
    caplog.set_level(logging.INFO, logger="app.services.llm")
    fake = FakeJsonModel('{"reasons": [{"sector_id": 1, "reason": "Short approach."}]}')

    answer = build_reasons_chain(fake).invoke({"query": "q", "sectors": "id=1 | t"})

    assert answer == MatchReasons(reasons=[MatchReason(sector_id=1, reason="Short approach.")])
    assert "Claude reasons: 10 in / 5 out tokens" in caplog.text


def test_get_reasons_chain_is_built_once(monkeypatch, clean_reasons_cache):
    builds = []

    def fake_factory():
        builds.append(1)
        return FakeStructuredModel()

    monkeypatch.setattr(reasons, "get_chat_model", fake_factory)

    assert get_reasons_chain() is get_reasons_chain()
    assert len(builds) == 1


def test_parse_chain_fills_prompt_and_asks_for_json_schema():
    fake = FakeStructuredModel(answer=CLEAR)

    answer = build_parse_chain(fake).invoke({"query": "around 6b, sport"})

    assert answer == CLEAR
    assert fake.schema is ParsedFilters
    assert fake.kwargs["method"] == "json_schema"
    system, human = fake.prompts[0].to_messages()
    assert system.content == PARSE_SYSTEM_PROMPT
    assert human.content == "around 6b, sport"


def test_parse_chain_logs_token_usage(caplog):
    caplog.set_level(logging.INFO, logger="app.services.llm")

    answer = build_parse_chain(FakeJsonModel(CLEAR.model_dump_json())).invoke({"query": "q"})

    assert answer == CLEAR
    assert "Claude natural_search: 10 in / 5 out tokens" in caplog.text


def test_get_parse_chain_is_built_once(monkeypatch, clean_parse_cache):
    builds = []

    def fake_factory():
        builds.append(1)
        return FakeStructuredModel(answer=CLEAR)

    monkeypatch.setattr(query_parsing, "get_chat_model", fake_factory)

    assert get_parse_chain() is get_parse_chain()
    assert len(builds) == 1
