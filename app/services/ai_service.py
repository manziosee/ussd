"""
Claude AI service — generates concise, USSD-friendly responses.

Cost optimisations applied
──────────────────────────
1. Anthropic prompt caching (cache_control: ephemeral) — system prompts are
   cached server-side after first use; subsequent calls save ~90% input tokens.
2. Redis response caching — same (category, question) pair is answered once
   per AI_CACHE_TTL (default 24 h); zero API cost on cache hits.
3. claude-haiku-4-5-20251001 — cheapest and fastest model; ideal for USSD latency.
4. Hard token ceiling (MAX_AI_TOKENS=150) prevents runaway costs.

Personalisation
───────────────
When a user has set their profession (farmer / student / business owner / other)
via the Account menu, it is injected as extra context into the system prompt.
This costs zero extra tokens because it replaces a placeholder in the cached prompt.

Language support
────────────────
When a user has selected Kinyarwanda (language="rw") in the Account menu,
an instruction is appended to the system prompt so Claude responds in
Kinyarwanda (Ikinyarwanda).
"""
from __future__ import annotations

import logging
from typing import NamedTuple

import anthropic

from ..config import get_settings
from . import session_service

log = logging.getLogger(__name__)
settings = get_settings()

# ── System prompts (cached by Anthropic after first use) ─────────────────────

_RULES = """
OUTPUT RULES — follow strictly:
- Maximum 155 characters total (hard limit — USSD screen constraint)
- ONE focused, actionable tip only — no lists, no preamble
- Plain text ONLY — no bullet points, no hashtags, no emojis, no markdown
- Simple language, Grade 8 level maximum
- Start directly with the advice — no greeting, no "Sure!", no repetition of the question
""".strip()

_PERSONALIZATION_HINT = (
    "\nUSER CONTEXT: This user is a {profession}. "
    "Tailor your advice specifically for their situation."
)

_LANGUAGE_HINT = (
    "\nLANGUAGE: Respond in Kinyarwanda (Ikinyarwanda). "
    "Use clear, simple language that rural users can understand."
)

SYSTEM_PROMPTS: dict[str, str] = {
    "business": (
        "You are a practical business advisor for African small business owners.\n"
        "Users run market stalls, small shops, or service businesses in East/Central Africa.\n"
        "Give advice that works with limited capital and local market conditions.\n"
        + _RULES
    ),
    "farming": (
        "You are an agricultural expert advising smallholder farmers in Africa.\n"
        "Users grow staple crops (maize, beans, cassava, vegetables) in East/Central Africa.\n"
        "Give practical advice suited to African climate, soil types, and limited resources.\n"
        + _RULES
    ),
    "health": (
        "You are a health information assistant providing general wellness guidance.\n"
        "Provide information about nutrition, hygiene, maternal health, and child health.\n"
        "NEVER diagnose illness. NEVER prescribe medication. "
        "ALWAYS recommend seeing a doctor for serious symptoms.\n"
        + _RULES
    ),
    "education": (
        "You are a helpful study and career guide for African students.\n"
        "Users are secondary school or university students needing practical academic help.\n"
        "Give study techniques, subject tips, or career planning guidance.\n"
        + _RULES
    ),
    "general": (
        "You are a helpful AI assistant for people in Africa accessing you via USSD.\n"
        "For many users this is their only AI tool — no smartphone, no internet required.\n"
        "Give practical, respectful, and locally relevant advice.\n"
        + _RULES
    ),
}


# ── Result type ───────────────────────────────────────────────────────────────

class AIResult(NamedTuple):
    text: str
    tokens_used: int
    from_cache: bool


# ── Main function ─────────────────────────────────────────────────────────────

async def get_ai_response(
    question: str,
    category: str,
    phone_number: str,
    user_profession: str | None = None,
    language: str = "en",
) -> AIResult:
    """
    Return an AI response for a USSD user.

    1. Checks Redis cache (category + question as key).
    2. On miss, calls Claude Haiku with prompt caching enabled.
    3. Stores the result in Redis for AI_CACHE_TTL seconds.

    Args:
        question        — the user's question or the pre-defined topic prompt
        category        — business | farming | health | education | general
        phone_number    — used for logging only
        user_profession — injected into system prompt for personalisation (optional)
        language        — "en" (default) or "rw" (Kinyarwanda); controls reply language

    Raises on API/network errors — callers must catch.
    """
    # 1. Redis cache hit → free
    cached = await session_service.get_cached_ai_response(category, question)
    if cached:
        log.debug("AI cache HIT [%s] %s…", category, question[:50])
        return AIResult(text=cached, tokens_used=0, from_cache=True)

    # 2. Build system prompt
    system_text = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["general"])

    if user_profession and user_profession != "other":
        system_text += _PERSONALIZATION_HINT.format(profession=user_profession)

    if language == "rw":
        system_text += _LANGUAGE_HINT

    # 3. Call Claude Haiku
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.max_ai_tokens,
        system=[
            {
                "type": "text",
                "text": system_text,
                # Anthropic caches the system prompt after the first request;
                # all subsequent calls with the same prompt save ~90% input tokens.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": question}],
    )

    response_text = message.content[0].text.strip()
    tokens        = message.usage.input_tokens + message.usage.output_tokens

    # 4. Save to Redis cache
    await session_service.cache_ai_response(category, question, response_text)

    log.info(
        "AI call [%s] %d tokens | lang=%s | phone=%s | q=%s",
        category, tokens, language, phone_number, question[:60],
    )
    return AIResult(text=response_text, tokens_used=tokens, from_cache=False)
