"""RAG chain tests. No network: retriever and model are RunnableLambda fakes."""

from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.core.config import settings
from app.rag.chain import build_rag_chain, format_docs
from app.rag.llm import get_chat_model
from app.scripts import rag_playground
from app.services.llm import LLM_MODEL

USAGE = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


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
