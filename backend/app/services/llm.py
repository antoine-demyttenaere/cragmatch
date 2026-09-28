import anthropic
from app.core.config import settings
import logging
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(
    api_key=settings.anthropic_api_key,
    timeout=20.0,     # seconds per attempt (default is 600)
    max_retries=2,    # the default, written out so it's a visible decision
    )


LLM_MODEL = "claude-sonnet-5"


def log_usage(purpose: str, response) -> None:
    logger.info(
        "Claude %s: %d in / %d out tokens",
        purpose,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

