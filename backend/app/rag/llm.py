from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.config import settings
from app.services.llm import LLM_MODEL, log_tokens


def get_chat_model(max_tokens: int = 1024) -> ChatAnthropic:
    # 20 s per attempt instead of the SDK's 600 s default, and 2 retries, so a slow
    # Claude call fails fast instead of hanging a request.
    # Settings are read here, not at import, so a test can swap the key.
    return ChatAnthropic(
        model=LLM_MODEL,
        api_key=settings.anthropic_api_key,
        timeout=20.0,
        max_retries=2,
        max_tokens=max_tokens,
    )


def _token_usage(response: LLMResult) -> dict | None:
    try:
        generation = response.generations[0][0]
    except IndexError:
        return None
    return getattr(getattr(generation, "message", None), "usage_metadata", None)


class UsageLogger(BaseCallbackHandler):
    # with_structured_output returns only the parsed object, so usage is read where
    # LangChain still sees the raw message: the model's on_llm_end event.
    # LangChain catches exceptions raised in a callback, so logging can never
    # break a request.
    def __init__(self, purpose: str) -> None:
        super().__init__()
        self.purpose = purpose

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = _token_usage(response)
        if usage:
            log_tokens(self.purpose, usage["input_tokens"], usage["output_tokens"])


class TokenCounter(BaseCallbackHandler):
    # One instance per request, passed at invoke: the chains are cached and
    # shared between threads, so counts kept on them would mix requests.
    def __init__(self) -> None:
        super().__init__()
        self.input_tokens = 0
        self.output_tokens = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = _token_usage(response)
        if usage:
            self.input_tokens += usage["input_tokens"]
            self.output_tokens += usage["output_tokens"]
