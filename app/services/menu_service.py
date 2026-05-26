"""
USSD menu state machine — core logic of SmartAssist.

Africa's Talking sends POST /ussd with:
  sessionId, serviceCode, phoneNumber, text (all inputs, *-separated)

We return:
  "CON <text>"  →  keep session open  (user sees menu + can respond)
  "END <text>"  →  close session      (user sees final message)

Menu tree
─────────
  Main Menu
  ├─ 1. Business    →  4 pre-defined tips + free question
  ├─ 2. Farming     →  4 pre-defined tips + free question
  ├─ 3. Health      →  4 pre-defined tips + free question
  ├─ 4. Education   →  4 pre-defined tips + free question
  ├─ 5. Ask AI      →  free-form question
  └─ 6. Account     →  stats · name · profession · language · SMS settings

"More tips" flow (predefined topics 1-4 per category)
──────────────────────────────────────────────────────
After the first tip, the response is CON (not END), offering:
  1.More tips  → AI generates a fresh variation tip
  0.Main menu  → back to root

The AT text accumulates: "1*2" → first tip, "1*2*1" → variation,
"1*2*1*1" → another variation, "1*2*0" → main menu.
_handle_category detects post_actions = sub[1:] to route accordingly.

Bug notes
─────────
_log_interaction_bg() creates its OWN DB session (AsyncSessionLocal) so it
is safe to fire-and-forget via asyncio.create_task; it no longer shares the
request-scoped session that closes when the HTTP response is sent.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import AsyncSessionLocal
from ..models.interaction import Interaction
from ..models.user import User
from ..services import ai_service, session_service, sms_service

log = logging.getLogger(__name__)
settings = get_settings()

# ── AT USSD response body limit ───────────────────────────────────────────────
_MAX_USSD_BODY  = 182              # safe AT limit (chars total incl. CON/END prefix)
_MORE_OPTIONS   = "\n1.More tips\n0.Main menu"   # appended to CON tip responses (22 chars)

# ── Static menu strings ───────────────────────────────────────────────────────

MAIN_MENU = (
    "CON SmartAssist AI\n"
    "1.Business\n"
    "2.Farming\n"
    "3.Health\n"
    "4.Education\n"
    "5.Ask AI\n"
    "6.Account"
)

BUSINESS_MENU = (
    "CON Business Advisor\n"
    "1.Pricing tips\n"
    "2.Bookkeeping\n"
    "3.Marketing\n"
    "4.Get customers\n"
    "5.My question\n"
    "0.Main menu"
)

FARMING_MENU = (
    "CON Farming Guide\n"
    "1.Soil tips\n"
    "2.Pest control\n"
    "3.Best crops\n"
    "4.Market prices\n"
    "5.My question\n"
    "0.Main menu"
)

HEALTH_MENU = (
    "CON Health Info\n"
    "1.Nutrition tips\n"
    "2.Hygiene tips\n"
    "3.Maternal health\n"
    "4.Child health\n"
    "5.My question\n"
    "0.Main menu"
)

EDUCATION_MENU = (
    "CON Education Help\n"
    "1.Study tips\n"
    "2.Career guide\n"
    "3.Math help\n"
    "4.English tips\n"
    "5.My question\n"
    "0.Main menu"
)

ACCOUNT_MENU = (
    "CON My Account\n"
    "1.My stats\n"
    "2.Set my name\n"
    "3.Set profession\n"
    "4.Language\n"
    "5.SMS alerts\n"
    "0.Main menu"
)

# Pre-defined topic questions sent to AI (or knowledge cache) per category
_TOPICS: dict[str, dict[str, str]] = {
    "business": {
        "1": "Give one practical pricing tip for a small market stall or shop in Africa.",
        "2": "Give one simple bookkeeping tip for a small African business owner with no accounting background.",
        "3": "Give one low-cost marketing idea for a small shop or stall in Africa.",
        "4": "Give one tip for attracting and keeping customers at a small business in Africa.",
    },
    "farming": {
        "1": "Give one practical soil preparation tip for a smallholder farmer in East Africa.",
        "2": "Give one effective pest control tip for a smallholder farmer in Africa with limited chemicals.",
        "3": "What is the best crop for a small African farmer to grow now for food and income?",
        "4": "Give one tip to help an African smallholder farmer get a fair price at the market.",
    },
    "health": {
        "1": "Give one practical nutrition tip for a family in rural Africa on a low income.",
        "2": "Give the most important hygiene tip to prevent common illnesses in African households.",
        "3": "Give one important maternal health tip for pregnant women in rural Africa.",
        "4": "Give one key child health tip for parents in rural Africa.",
    },
    "education": {
        "1": "Give one highly effective study technique for a secondary school student in Africa.",
        "2": "Give one practical career planning tip for a student in Africa choosing their future.",
        "3": "Give one tip to help a student improve at mathematics.",
        "4": "Give one practical tip to improve English communication for a student in Africa.",
    },
}


# ── Main entry point ───────────────────────────────────────────────────────────

async def process_ussd(
    session_id: str,
    phone_number: str,
    text: str,
    db: AsyncSession,
) -> str:
    """
    Parse accumulated USSD text and return the appropriate CON / END string.
    Called once per user keypress.
    """
    # Ensure user record exists (idempotent; skipped if Redis flags it exists)
    await _ensure_user_cached(phone_number, db)

    clean  = (text or "").strip()
    inputs = [p.strip() for p in clean.split("*")] if clean else []

    if not inputs:
        return MAIN_MENU

    level1 = inputs[0]
    sub    = inputs[1:]

    route = {
        "1": ("business",  BUSINESS_MENU),
        "2": ("farming",   FARMING_MENU),
        "3": ("health",    HEALTH_MENU),
        "4": ("education", EDUCATION_MENU),
    }

    if level1 in route:
        cat, menu = route[level1]
        return await _handle_category(cat, menu, sub, session_id, phone_number, db)
    elif level1 == "5":
        return await _handle_ask_ai(sub, session_id, phone_number, db)
    elif level1 == "6":
        return await _handle_account(sub, phone_number, db)
    elif level1 == "0":
        return MAIN_MENU
    else:
        return "END Invalid option. Please dial again."


# ── Category handler ───────────────────────────────────────────────────────────

async def _handle_category(
    category: str,
    menu_text: str,
    sub: list[str],
    session_id: str,
    phone_number: str,
    db: AsyncSession,
) -> str:
    """
    Route within a category (business / farming / health / education).

    sub  = everything after the level-1 digit:
      []        → show category menu
      ["2"]     → first view of bookkeeping tip  (returns CON with More/Back)
      ["2","1"] → "More tips" after bookkeeping  (returns CON with More/Back)
      ["2","0"] → go back to main menu
      ["5"]     → prompt for free-form question
      ["5","q"] → free-form question text
    """
    if not sub:
        return menu_text

    choice = sub[0]

    if choice == "0":
        return MAIN_MENU

    # ── Free-form question in this category ───────────────────────────────────
    if choice == "5":
        if len(sub) == 1:
            label = category.capitalize()
            return f"CON Your {label} question:"
        question = "*".join(sub[1:])
        return await _ask_and_respond(question, category, session_id, phone_number, db)

    # ── Pre-defined topics 1–4 ────────────────────────────────────────────────
    topic_map = _TOPICS.get(category, {})
    if choice not in topic_map:
        return "END Invalid option."

    # post_actions: inputs after the first topic selection
    # e.g. sub=["2"]        → []          first view
    #      sub=["2","1"]    → ["1"]       "More tips" once
    #      sub=["2","1","1"]→ ["1","1"]   "More tips" twice
    #      sub=["2","0"]    → ["0"]       back to main
    post_actions = sub[1:]

    if not post_actions:
        # First view — show tip with continuation options
        return await _ask_and_respond(
            topic_map[choice], category, session_id, phone_number, db, show_more=True
        )

    last_action = post_actions[-1]

    if last_action == "0":
        return MAIN_MENU

    if last_action == "1":
        # User wants a fresh variation on the same topic
        variation_q = topic_map[choice] + " Give a completely different, fresh practical tip."
        return await _ask_and_respond(
            variation_q, category, session_id, phone_number, db, show_more=True
        )

    return "END Invalid option."


# ── Ask AI direct (option 5 from main menu) ────────────────────────────────────

async def _handle_ask_ai(
    sub: list[str],
    session_id: str,
    phone_number: str,
    db: AsyncSession,
) -> str:
    if not sub:
        return "CON Ask AI anything:\n(type your question)"
    question = "*".join(sub)
    return await _ask_and_respond(question, "general", session_id, phone_number, db)


# ── Account menu ───────────────────────────────────────────────────────────────

async def _handle_account(
    sub: list[str],
    phone_number: str,
    db: AsyncSession,
) -> str:
    """
    Account sub-menu.

    Options:
      1 — My stats
      2 — Set name
      3 — Set profession
      4 — Language  (English / Kinyarwanda)
      5 — SMS alerts toggle
      0 — Main menu
    """
    if not sub:
        return ACCOUNT_MENU

    choice = sub[0]

    if choice == "0":
        return MAIN_MENU

    # ── 1. My stats ──────────────────────────────────────────────────────────
    elif choice == "1":
        user = await _get_user(phone_number, db)
        name_line = f"Name: {user.name}\n"   if user.name       else ""
        prof_line = f"Role: {user.profession}\n" if user.profession else ""
        lang_line = f"Lang: {'Kinyarwanda' if user.language == 'rw' else 'English'}\n"
        sms_line  = "SMS: off\n" if user.sms_opt_out else ""
        since     = user.created_at.strftime("%b %Y") if user.created_at else "recently"
        return (
            f"END My Account\n"
            f"{name_line}"
            f"{prof_line}"
            f"{lang_line}"
            f"{sms_line}"
            f"Queries: {user.total_queries}\n"
            f"Since: {since}"
        )

    # ── 2. Set name ───────────────────────────────────────────────────────────
    elif choice == "2":
        if len(sub) == 1:
            return "CON Enter your name:"
        name = " ".join(sub[1:])[:100].strip()
        if not name:
            return "END Name cannot be empty. Dial again."
        await _update_user(phone_number, {"name": name}, db)
        await session_service.clear_profile_cache(phone_number)
        return f"END Name saved: {name}\nDial again to continue."

    # ── 3. Set profession ─────────────────────────────────────────────────────
    elif choice == "3":
        if len(sub) == 1:
            return (
                "CON Select your role:\n"
                "1.Farmer\n"
                "2.Student\n"
                "3.Business owner\n"
                "4.Other"
            )
        prof_map = {"1": "farmer", "2": "student", "3": "business owner", "4": "other"}
        profession = prof_map.get(sub[1])
        if not profession:
            return "END Invalid choice."
        await _update_user(phone_number, {"profession": profession}, db)
        await session_service.clear_profile_cache(phone_number)
        return (
            f"END Role saved: {profession}\n"
            "AI will personalise tips for you.\n"
            "Dial again to continue."
        )

    # ── 4. Language ───────────────────────────────────────────────────────────
    elif choice == "4":
        if len(sub) == 1:
            return (
                "CON Select language:\n"
                "1.English\n"
                "2.Kinyarwanda\n"
                "0.Back"
            )
        action = sub[1]
        if action == "0":
            return ACCOUNT_MENU
        lang_map = {"1": "en", "2": "rw"}
        lang = lang_map.get(action)
        if not lang:
            return "END Invalid choice."
        await _update_user(phone_number, {"language": lang}, db)
        await session_service.clear_profile_cache(phone_number)
        lang_name = "Kinyarwanda" if lang == "rw" else "English"
        return (
            f"END Language set: {lang_name}\n"
            "AI will now reply in your language.\n"
            "Dial again to continue."
        )

    # ── 5. SMS alerts ─────────────────────────────────────────────────────────
    elif choice == "5":
        user = await _get_user(phone_number, db)
        if len(sub) == 1:
            status  = "OFF" if user.sms_opt_out else "ON"
            toggle  = "Turn off SMS" if not user.sms_opt_out else "Turn on SMS"
            return (
                f"CON SMS alerts: {status}\n"
                f"1.{toggle}\n"
                "0.Back"
            )
        action = sub[1]
        if action == "0":
            return ACCOUNT_MENU
        if action == "1":
            new_val = not user.sms_opt_out
            await _update_user(phone_number, {"sms_opt_out": new_val}, db)
            await session_service.clear_profile_cache(phone_number)
            status = "disabled" if new_val else "enabled"
            return (
                f"END SMS alerts {status}.\n"
                "Dial again to continue."
            )
        return "END Invalid option."

    return "END Invalid option."


# ── Core AI call + formatting ──────────────────────────────────────────────────

async def _ask_and_respond(
    question: str,
    category: str,
    session_id: str,
    phone_number: str,
    db: AsyncSession,
    show_more: bool = False,
) -> str:
    """
    Call AI (or knowledge cache), format the response, fire-and-forget log.

    show_more=True  → return CON with "1.More tips / 0.Main menu" options
                       (used for pre-defined topic picks so users can keep browsing)
    show_more=False → return END  (used for free-form questions)
    """
    question = question.strip()
    if not question:
        return "END Please enter a question."

    # ── Rate limit ───────────────────────────────────────────────────────────
    allowed, _remaining = await session_service.check_rate_limit(phone_number)
    if not allowed:
        return "END You have reached the hourly limit. Please try again later."

    # ── User preferences (profession, language, sms_opt_out) ─────────────────
    prefs      = await _get_cached_user_prefs(phone_number, db)
    profession = prefs.get("profession")
    language   = prefs.get("language", "en") or "en"
    sms_opt_out = prefs.get("sms_opt_out", False)

    # ── Call AI service ───────────────────────────────────────────────────────
    try:
        result = await ai_service.get_ai_response(
            question=question,
            category=category,
            phone_number=phone_number,
            user_profession=profession,
            language=language,
        )
        ai_text    = result.text
        tokens     = result.tokens_used
        from_cache = result.from_cache
    except Exception as exc:
        log.error("AI error for %s: %s", phone_number, exc)
        return "END AI is busy. Please try again in a moment."

    # ── Format response ───────────────────────────────────────────────────────
    sms_sent = False

    if show_more:
        # CON response with navigation options
        # Reserve space: 4 ("CON ") + len(_MORE_OPTIONS) = 4 + 22 = 26
        max_tip = _MAX_USSD_BODY - len("CON ") - len(_MORE_OPTIONS)
        if len(ai_text) > max_tip:
            ai_text = ai_text[:max_tip - 1] + "…"
        response_str = f"CON {ai_text}{_MORE_OPTIONS}"

    elif not sms_opt_out and len(ai_text) > settings.sms_char_limit:
        # Long free-form answer → truncate for USSD + send full via SMS
        full_sms = sms_service.format_sms_response(category, question, ai_text)
        sms_sent = await sms_service.send_sms(phone_number, full_sms)
        display  = ai_text[: settings.sms_char_limit - 3] + "..."
        note     = "\n\nFull answer sent via SMS." if sms_sent else ""
        response_str = f"END {display}{note}"

    else:
        response_str = f"END {ai_text}"

    # ── Log interaction in background (own DB session) ────────────────────────
    asyncio.create_task(
        _log_interaction_bg(
            session_id=session_id,
            phone_number=phone_number,
            category=category,
            question=question,
            response=ai_text,
            tokens_used=tokens,
            from_cache=from_cache,
            sms_sent=sms_sent,
        )
    )

    return response_str


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def _ensure_user_cached(phone_number: str, db: AsyncSession) -> None:
    """Create user record if it doesn't exist; skip if Redis says it already does."""
    if await session_service.user_exists_cached(phone_number):
        return
    result = await db.execute(select(User).where(User.phone_number == phone_number))
    if result.scalar_one_or_none() is None:
        db.add(User(phone_number=phone_number))
        await db.commit()
    await session_service.mark_user_exists(phone_number)


async def _get_user(phone_number: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.phone_number == phone_number))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(phone_number=phone_number)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def _update_user(phone_number: str, fields: dict, db: AsyncSession) -> None:
    await db.execute(
        update(User).where(User.phone_number == phone_number).values(**fields)
    )
    await db.commit()


async def _get_cached_user_prefs(phone_number: str, db: AsyncSession) -> dict:
    """
    Return cached user preferences: profession, language, sms_opt_out, name.
    Checks Redis profile cache first; falls back to DB on miss.
    """
    profile = await session_service.get_cached_profile(phone_number)
    # Require all expected keys to be present before trusting the cached value;
    # old cache entries may be missing sms_opt_out / language.
    if profile and {"profession", "language", "sms_opt_out"}.issubset(profile):
        return profile

    user = await _get_user(phone_number, db)
    prefs: dict = {
        "name":        user.name,
        "profession":  user.profession,
        "language":    user.language or "en",
        "sms_opt_out": bool(user.sms_opt_out),
    }
    await session_service.cache_profile(phone_number, prefs)
    return prefs


async def _log_interaction_bg(
    *,
    session_id: str,
    phone_number: str,
    category: str,
    question: str,
    response: str,
    tokens_used: int,
    from_cache: bool,
    sms_sent: bool,
) -> None:
    """
    Background task — creates its OWN DB session so it runs safely after the
    HTTP response has been sent and the request session has been closed.
    """
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                Interaction(
                    session_id=session_id,
                    phone_number=phone_number,
                    category=category,
                    question=question,
                    response=response,
                    tokens_used=tokens_used,
                    from_cache=from_cache,
                    sms_sent=sms_sent,
                )
            )
            await db.execute(
                update(User)
                .where(User.phone_number == phone_number)
                .values(total_queries=User.total_queries + 1)
            )
            await db.commit()
    except Exception as exc:
        log.error("Failed to log interaction for %s: %s", phone_number, exc)
