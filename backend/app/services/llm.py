"""Claude model name and the token usage log line, shared by app/rag/."""

import logging

logger = logging.getLogger(__name__)

LLM_MODEL = "claude-sonnet-5"


def log_tokens(purpose: str, input_tokens: int, output_tokens: int) -> None:
    logger.info("Claude %s: %d in / %d out tokens", purpose, input_tokens, output_tokens)
