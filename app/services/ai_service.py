"""
Groq AI service — generates concise, USSD-friendly responses via Llama models.

Cost optimisations applied
──────────────────────────
1. Redis response caching — same (category, question) pair is answered once
   per AI_CACHE_TTL (default 24 h); zero API cost on cache hits.
2. llama-3.1-8b-instant — Groq's fastest model; ideal for USSD latency.
3. Hard token ceiling (MAX_AI_TOKENS=150) keeps responses short and cheap.
4. 3-attempt retry with back-off for transient network/API errors.

Personalisation
───────────────
When a user has set their profession (farmer / student / business owner / other)
via the Account menu, it is injected as extra context into the system prompt.

Language support
────────────────
When a user has selected Kinyarwanda (language="rw") in the Account menu,
an instruction is appended to the system prompt so the model responds in
Kinyarwanda (Ikinyarwanda).
"""
from __future__ import annotations

import asyncio
import logging
from typing import NamedTuple

from groq import AsyncGroq, APIConnectionError, APITimeoutError, InternalServerError

from ..config import get_settings
from . import session_service

log = logging.getLogger(__name__)
settings = get_settings()

# ── System prompts ────────────────────────────────────────────────────────────

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


# ── Retry config ──────────────────────────────────────────────────────────────

_RETRY_DELAYS = (0.3, 0.8)  # seconds between attempts 1→2 and 2→3


# ── Main function ─────────────────────────────────────────────────────────────

async def get_ai_response(
    question: str,
    category: str,
    phone_number: str,
    user_profession: str | None = None,
    language: str = "en",
) -> AIResult:
    """
    Return an AI response for a USSD user via Groq (Llama).

    1. Checks Redis cache (category + question as key).
    2. On miss, calls Groq with up to 3 attempts on transient errors.
    3. Stores the result in Redis for AI_CACHE_TTL seconds.

    Args:
        question        — the user's question or the pre-defined topic prompt
        category        — business | farming | health | education | general
        phone_number    — used for logging only
        user_profession — injected into system prompt for personalisation (optional)
        language        — "en" (default) or "rw" (Kinyarwanda); controls reply language

    Raises on non-retriable API errors — callers must catch.
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

    # 3. Call Groq with retry on transient errors
    client = AsyncGroq(api_key=settings.groq_api_key)
    last_exc: Exception | None = None

    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            completion = await client.chat.completions.create(
                model=settings.groq_model,
                max_tokens=settings.max_ai_tokens,
                messages=[
                    {"role": "system", "content": system_text},
                    {"role": "user",   "content": question},
                ],
            )
            break
        except (APIConnectionError, APITimeoutError, InternalServerError) as exc:
            last_exc = exc
            if delay is None:
                raise
            log.warning(
                "Groq call failed (attempt %d): %s — retrying in %.1fs",
                attempt + 1, exc, delay,
            )
            await asyncio.sleep(delay)
    else:
        raise last_exc  # type: ignore[misc]

    response_text = completion.choices[0].message.content.strip()
    tokens        = completion.usage.prompt_tokens + completion.usage.completion_tokens

    # 4. Save to Redis cache
    await session_service.cache_ai_response(category, question, response_text)

    log.info(
        "Groq call [%s] %d tokens | lang=%s | phone=%s | q=%s",
        category, tokens, language, phone_number, question[:60],
    )
    return AIResult(text=response_text, tokens_used=tokens, from_cache=False)
