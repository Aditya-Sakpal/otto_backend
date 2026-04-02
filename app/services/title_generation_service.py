"""
Auto-generate conversation titles for Ask Otto threads using OpenAI.

Similar to ChatGPT's auto-title feature — generates a concise title
from the first user message in a conversation.
"""
import openai
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Use the first API key if multiple are provided (comma-separated)
_api_key = settings.OPENAI_API_KEY.split(",")[0].strip() if settings.OPENAI_API_KEY else ""
_client = openai.AsyncOpenAI(api_key=_api_key) if _api_key else None

TITLE_GENERATION_PROMPT = (
    "Generate a short, descriptive title (maximum 7 words) for a conversation "
    "that starts with the following user message. The title should capture the "
    "main topic or intent. Return ONLY the title text, no quotes, no punctuation "
    "at the end, no explanation."
)


async def generate_conversation_title(user_message: str) -> str | None:
    """
    Generate a concise title for a conversation based on the first user message.

    Returns None if title generation fails (caller should handle gracefully).
    """
    if not _client:
        logger.warning("OpenAI client not configured — skipping title generation")
        return None

    try:
        response = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": TITLE_GENERATION_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=30,
            temperature=0.7,
        )
        title = response.choices[0].message.content.strip()
        # Safety: truncate if somehow too long
        if len(title) > 100:
            title = title[:97] + "..."
        return title
    except Exception as e:
        logger.error(f"Failed to generate conversation title: {e}")
        return None
