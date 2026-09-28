import anthropic
from app.core.config import settings
import logging
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
# One place to change the model for every Claude call in the app.
LLM_MODEL = "claude-sonnet-5"


def log_usage(purpose: str, response) -> None:
    logger.info(
        "Claude %s: %d in / %d out tokens",
        purpose,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

