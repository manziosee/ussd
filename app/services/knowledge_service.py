"""
Offline knowledge cache — pre-seeded, Africa-focused responses for every
pre-defined topic in the USSD menu.

Why this matters
────────────────
- The very first user to hit any pre-defined topic would normally trigger an
  AI API call.  By seeding Redis on startup we guarantee zero-latency, zero-
  cost responses for all 15 common topics from the very first request.
- Seed responses are written to be under 110 chars — the safe display limit
  when the full post-tip navigation footer (_MORE_OPTIONS, 68 chars) is
  appended inside a 182-char CON response (182 - 4 - 68 = 110).
- All responses stay in Redis with a 7-day TTL (refreshed on each restart).
  The AI service's own caching then keeps them warm indefinitely after that.

Extend this
───────────
Add more topics to SEEDED_RESPONSES to grow the offline knowledge base.
Keys must match the questions in menu_service._TOPICS exactly.
Note: farming topic "4" (Market prices) is DB-backed, not AI — no entry here.
"""
from __future__ import annotations

import logging

from .session_service import cache_ai_response

log = logging.getLogger(__name__)

# TTL for pre-seeded entries: 7 days (in seconds)
SEED_TTL = 7 * 24 * 3600

# ── Pre-written responses (≤110 chars each) ───────────────────────────────────
# Structure: { category: { question_text: response_text } }
# question_text must match menu_service._TOPICS exactly.

SEEDED_RESPONSES: dict[str, dict[str, str]] = {
    "business": {
        "Give one practical pricing tip for a small market stall or shop in Africa.": (
            "Price = cost + 30% profit min. If stock sells instantly, raise 10%."
            " Check competitor prices weekly."
        ),
        "Give one simple bookkeeping tip for a small African business owner with no accounting background.": (
            "Use a notebook: Date | In | Out | Balance."
            " Update daily. Never mix business and personal money."
        ),
        "Give one low-cost marketing idea for a small shop or stall in Africa.": (
            "Ask customers to refer friends weekly. Give small discount to new referrals."
            " Use WhatsApp Status for free ads."
        ),
        "Give one tip for attracting and keeping customers at a small business in Africa.": (
            "Greet regulars by name. Give a small reward on their 5th visit."
            " Follow up in 3 days after big purchases."
        ),
    },
    "farming": {
        "Give one practical soil preparation tip for a smallholder farmer in East Africa.": (
            "Add compost 2 weeks before planting. Good soil is dark and crumbles easily."
            " Never burn crop waste."
        ),
        "Give one effective pest control tip for a smallholder farmer in Africa with limited chemicals.": (
            "Plant onions around crops to repel insects. Remove sick plants immediately."
            " Inspect crops each morning."
        ),
        "What is the best crop for a small African farmer to grow now for food and income?": (
            "Grow beans with maize: beans fix nitrogen and sell year-round."
            " Kale grows in 30 days, always in demand."
        ),
        # Farming option 4 (Market prices) is DB-backed — no AI seed entry.
    },
    "health": {
        "Give one practical nutrition tip for a family in rural Africa on a low income.": (
            "Eat beans daily for cheap protein. Add dark greens for iron."
            " A varied plate prevents nutritional gaps."
        ),
        "Give the most important hygiene tip to prevent common illnesses in African households.": (
            "Wash hands with soap for 20 seconds before meals and after toilet."
            " This prevents most common illnesses."
        ),
        "Give one important maternal health tip for pregnant women in rural Africa.": (
            "Attend 8 antenatal visits. Take iron and folic acid every day."
            " Severe headache or swollen face: see a doctor."
        ),
        "Give one key child health tip for parents in rural Africa.": (
            "Breastfeed exclusively for 6 months. Give all vaccines on schedule."
            " Wash hands before every feeding."
        ),
    },
    "education": {
        "Give one highly effective study technique for a secondary school student in Africa.": (
            "Study 25 min, rest 5 min (Pomodoro). After each session,"
            " write what you learned without looking at notes."
        ),
        "Give one practical career planning tip for a student in Africa choosing their future.": (
            "Pick a career with local demand. Talk to 3 people doing that job."
            " Any related experience beats certificates."
        ),
        "Give one tip to help a student improve at mathematics.": (
            "Master times tables, fractions, and percentages."
            " Do 10 problems daily. Understand the method, not the answer."
        ),
        "Give one practical tip to improve English communication for a student in Africa.": (
            "Read one article in English daily. Write 5 new words in sentences."
            " Record yourself to catch and fix mistakes."
        ),
    },
}


# ── Seed function called at startup ─────────────────────────────────────────

async def seed_knowledge_cache() -> None:
    """
    Pre-populate Redis with offline responses for all 15 pre-defined topics.
    Uses a 7-day TTL so they stay warm even if no user asks for a while.
    Skips any key that already has a longer TTL (e.g. a recent AI response).
    """
    seeded = 0
    skipped = 0

    from .session_service import get_redis, _ai_key  # local import to avoid circular

    r = get_redis()

    for category, topics in SEEDED_RESPONSES.items():
        for question, response in topics.items():
            key = _ai_key(category, question)
            existing_ttl = await r.ttl(key)
            # Only seed if the key is missing or has a shorter TTL than our seed TTL
            if existing_ttl < SEED_TTL:
                await r.setex(key, SEED_TTL, response)
                seeded += 1
            else:
                skipped += 1

    log.info(
        "Knowledge cache seeded: %d responses written, %d already current.",
        seeded, skipped,
    )
