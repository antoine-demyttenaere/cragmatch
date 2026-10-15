"""Token usage logging. No DB, no network: plain objects and caplog."""

import logging
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.rag.llm import TokenCounter, UsageLogger


def make_result(message: AIMessage) -> LLMResult:
    return LLMResult(generations=[[ChatGeneration(message=message)]])


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


def test_token_counter_adds_up_every_model_call():
    counter = TokenCounter()
    first = AIMessage(
        content="{}", usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    )
    second = AIMessage(
        content="{}", usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}
    )

    counter.on_llm_end(make_result(first), run_id=uuid4())
    counter.on_llm_end(make_result(second), run_id=uuid4())
    counter.on_llm_end(make_result(AIMessage(content="{}")), run_id=uuid4())

    assert counter.input_tokens == 17
    assert counter.output_tokens == 8
