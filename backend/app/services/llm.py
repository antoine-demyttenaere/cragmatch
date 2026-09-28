import anthropic

from app.core.config import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# One place to change the model for every Claude call in the app.
LLM_MODEL = "claude-sonnet-5"
