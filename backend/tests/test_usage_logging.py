"""Token usage logging. No DB, no network: plain objects and caplog."""

import logging
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.rag.llm import UsageLogger
from app.services.llm import log_usage


def make_result(message: AIMessage) -> LLMResult:
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def test_log_usage_reads_an_anthropic_response(caplog):
    caplog.set_level(logging.INFO, logger="app.services.llm")
    response = SimpleNamespace(usage=SimpleNamespace(input_tokens=12, output_tokens=3))

    log_usage("natural_search", response)

    assert "Claude natural_search: 12 in / 3 out tokens" in caplog.text


def test_usage_logger_logs_tokens_of_a_model_call(caplog):
    caplog.set_level(logging.INFO, logger="app.services.llm")
    message = AIMessage(
        content="{}",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )

    UsageLogger("reasons").on_llm_end(make_result(message), run_id=uuid4())

    assert "Claude reasons: 10 in / 5 out tokens" in caplog.text


def test_usage_logger_skips_a_message_without_usage(caplog):
    caplog.set_level(logging.INFO, logger="app.services.llm")

    UsageLogger("reasons").on_llm_end(make_result(AIMessage(content="{}")), run_id=uuid4())

    assert "Claude" not in caplog.text
