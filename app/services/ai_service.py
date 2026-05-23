"""
Claude AI service — generates concise, USSD-friendly responses.

Cost optimisations:
  1. System-prompt caching via cache_control (Anthropic prompt caching)
  2. Redis response caching — same question answered once per 24 h
  3. claude-haiku-4-5-20251001 — cheapest + fastest model, perfect for USSD
  4. Hard token limit (max_ai_tokens=150) prevents runaway costs
"""
import logging
from typing import NamedTuple

import anthropic

from ..config import get_settings
from . import session_service

log = logging.getLogger(__name__)
settings = get_settings()

# ── System prompts (cached by Anthropic after first use) ─────────────────────

_BASE_RULES = """
STRICT OUTPUT RULES:
- Maximum 160 characters total (critical — USSD display limit)
- One focused, actionable tip only
- Plain text only — NO bullet points, NO hashtags, NO emojis, NO markdown
- Simple English, Grade 8 level
- Start directly with the advice — no greetings or preamble
""".strip()

SYSTEM_PROMPTS: dict[str, str] = {
    "business": f"""You are a practical business advisor for African small business owners.
Your users run small shops, market stalls, or service businesses in East/Central Africa.
Give real, immediately actionable advice suited to low-resource African markets.
{_BASE_RULES}""",

    "farming": f"""You are an agricultural expert advising smallholder farmers in Africa.
Your users grow staple crops (maize, beans, cassava) or vegetables in East/Central Africa.
Give practical farming advice suited to African climate, soils, and limited resources.
{_BASE_RULES}""",

    "health": f"""You are a health information assistant.
Provide general wellness information — nutrition, hygiene, maternal health, child health.
NEVER diagnose, NEVER prescribe medication, ALWAYS recommend seeing a doctor for serious symptoms.
{_BASE_RULES}""",

    "education": f"""You are a helpful study and career guide for African students.
Your users are secondary or university students needing practical academic help.
Give study techniques, career guidance, or simple explanations.
{_BASE_RULES}""",

    "general": f"""You are a helpful AI assistant for people accessing you via USSD on a mobile phone.
Your users are in Africa and may have limited internet access — this may be their only AI tool.
Give practical, relevant, and respectful advice.
{_BASE_RULES}""",
}


class AIResult(NamedTuple):
    text: str
    tokens_used: int
    from_cache: bool


async def get_ai_response(
    question: str,
    category: str,
    phone_number: str,
) -> AIResult:
    """
    Get an AI response for a USSD user.

    Returns AIResult(text, tokens_used, from_cache).
    Raises exceptions — callers must handle gracefully.
    """
    # 1. Check Redis cache first (saves API cost)
    cached = await session_service.get_cached_ai_response(category, question)
    if cached:
        log.debug("AI cache hit: [%s] %s", category, question[:60])
        return AIResult(text=cached, tokens_used=0, from_cache=True)

    # 2. Call Claude
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    system_text = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["general"])

    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.max_ai_tokens,
        system=[
            {
                "type": "text",
                "text": system_text,
                # Prompt caching — Anthropic caches this after first use
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": question}],
    )

    response_text = message.content[0].text.strip()
    tokens = message.usage.input_tokens + message.usage.output_tokens

    # 3. Save to Redis cache
    await session_service.cache_ai_response(category, question, response_text)

    log.info(
        "AI call: [%s] %d tokens | phone=%s | q=%s",
        category, tokens, phone_number, question[:60],
    )
    return AIResult(text=response_text, tokens_used=tokens, from_cache=False)
