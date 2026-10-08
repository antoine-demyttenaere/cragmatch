from langchain_anthropic import ChatAnthropic

from app.core.config import settings
from app.services.llm import LLM_MODEL


def get_chat_model(max_tokens: int = 1024) -> ChatAnthropic:
    # Same timeout and retries as services/llm.py, so both paths fail the same way.
    # Settings are read here, not at import, so a test can swap the key.
    return ChatAnthropic(
        model=LLM_MODEL,
        api_key=settings.anthropic_api_key,
        timeout=20.0,
        max_retries=2,
        max_tokens=max_tokens,
    )
