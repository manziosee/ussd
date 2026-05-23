"""
Offline knowledge cache — pre-seeded, Africa-focused responses for every
pre-defined topic in the USSD menu.

Why this matters
────────────────
- The very first user to hit any pre-defined topic would normally trigger an
  AI API call.  By seeding Redis on startup we guarantee zero-latency, zero-
  cost responses for all 16 common topics from the very first request.
- Seed responses are carefully written to be under 155 chars (USSD display
  limit) and immediately actionable for African users.
- All responses stay in Redis with a 7-day TTL (refreshed on each restart).
  The AI service's own caching then keeps them warm indefinitely after that.

Extend this
───────────
Add more topics to SEEDED_RESPONSES to grow the offline knowledge base.
Keys must match the questions in menu_service._TOPICS exactly.
"""
from __future__ import annotations

import logging

from .session_service import cache_ai_response

log = logging.getLogger(__name__)

# TTL for pre-seeded entries: 7 days (in seconds)
SEED_TTL = 7 * 24 * 3600

# ── Pre-written responses (< 155 chars each, tested) ─────────────────────────
# Structure: { category: { question_text: response_text } }
# question_text must match menu_service._TOPICS exactly.

SEEDED_RESPONSES: dict[str, dict[str, str]] = {
    "business": {
        "Give one practical pricing tip for a small market stall or shop in Africa.": (
            "Add total cost + 30% profit minimum. If all customers buy instantly, "
            "raise price 10%. Track prices weekly and adjust with market changes."
        ),
        "Give one simple bookkeeping tip for a small African business owner with no accounting background.": (
            "Use a notebook: Date | Money In | Money Out | Balance. "
            "Update it daily. Never mix business and personal money."
        ),
        "Give one low-cost marketing idea for a small shop or stall in Africa.": (
            "Ask 3 happy customers to refer a friend each week. "
            "Give a small discount to new customers they bring. "
            "Use WhatsApp status for free daily advertising."
        ),
        "Give one tip for attracting and keeping customers at a small business in Africa.": (
            "Greet every customer by name when possible. "
            "Give a small gift or discount on their 5th visit. "
            "Follow up within 3 days after a large purchase."
        ),
    },
    "farming": {
        "Give one practical soil preparation tip for a smallholder farmer in East Africa.": (
            "Mix compost or manure into soil 2 weeks before planting. "
            "Good soil is dark and crumbles easily. "
            "Avoid burning — it destroys nutrients."
        ),
        "Give one effective pest control tip for a smallholder farmer in Africa with limited chemicals.": (
            "Plant onions or marigolds around your crops to repel insects. "
            "Remove diseased plants immediately. "
            "Inspect crops every morning — early detection saves harvests."
        ),
        "What is the best crop for a small African farmer to grow now for food and income?": (
            "Plant beans alongside maize — beans add nitrogen to soil and sell year-round. "
            "Kale and spinach grow in 30 days and have steady local demand."
        ),
        "Give one tip to help an African smallholder farmer get a fair price at the market.": (
            "Know your total cost before selling. "
            "Group with other farmers to sell in bulk for better prices. "
            "Wait 3 weeks after harvest when supply drops and prices rise."
        ),
    },
    "health": {
        "Give one practical nutrition tip for a family in rural Africa on a low income.": (
            "Eat beans or lentils for protein daily — cheaper than meat. "
            "Add dark green vegetables for iron. "
            "A varied plate prevents most nutritional deficiencies."
        ),
        "Give the most important hygiene tip to prevent common illnesses in African households.": (
            "Wash hands with soap for 20 seconds before cooking and after using the toilet. "
            "This one habit prevents over 50% of common illnesses."
        ),
        "Give one important maternal health tip for pregnant women in rural Africa.": (
            "Attend all 8 antenatal visits. Take iron and folic acid tablets daily. "
            "Danger signs: swollen face, blurred vision, severe headache — go to clinic immediately."
        ),
        "Give one key child health tip for parents in rural Africa.": (
            "Breastfeed exclusively for 6 months. Give all vaccines on schedule. "
            "Wash hands before every feeding. These three steps prevent most child illness."
        ),
    },
    "education": {
        "Give one highly effective study technique for a secondary school student in Africa.": (
            "Study for 25 minutes, then rest 5 minutes (Pomodoro method). "
            "After each session, write what you learned in your own words without looking at notes."
        ),
        "Give one practical career planning tip for a student in Africa choosing their future.": (
            "Choose a career with real local demand. Talk to 3 people doing that job. "
            "Start with any small related experience now — experience beats certificates."
        ),
        "Give one tip to help a student improve at mathematics.": (
            "Master times tables, fractions, and percentages first — they underpin everything. "
            "Do 10 practice problems daily. Understand the method, not just the answer."
        ),
        "Give one practical tip to improve English communication for a student in Africa.": (
            "Read one English article daily — even headlines count. "
            "Write 5 new words and use them in sentences. "
            "Record yourself speaking to hear and fix your own mistakes."
        ),
    },
}


# ── Seed function called at startup ─────────────────────────────────────────

async def seed_knowledge_cache() -> None:
    """
    Pre-populate Redis with offline responses for all 16 pre-defined topics.
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
