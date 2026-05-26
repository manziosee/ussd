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

Input sanitisation
──────────────────
Raw AT text goes through _sanitize() before any routing:
  • Trailing # stripped (AT sometimes appends it)
  • Double-* collapses into a single separator (e.g. "1**2" → ["1","2"])
  • Leading/trailing whitespace removed from every segment
  • Total text capped at 200 chars — rejects abusive inputs

"More tips" CON flow (predefined topics 1-4 per category)
──────────────────────────────────────────────────────────
After the first tip, the response is CON (not END), offering:
  1.More tips  → AI generates a fresh variation tip
  0.Main menu  → back to root

Text accumulates: "1*2" → first tip, "1*2*1" → variation,
"1*2*1*1" → another variation, "1*2*0" → main menu.
_handle_category detects post_actions = sub[1:] to route accordingly.

Session resume after drop
─────────────────────────
On every CON response the current text (menu position) is saved to Redis
under ussd:resume:{phone} with a 10-minute TTL.
When a user re-dials after a drop (text="", new sessionId, resume exists)
they see:
  "CON Resume where you left off? 1.Yes - <label>  2.New session"
Pressing 1 re-processes the saved text; pressing 2 clears it and shows
the normal main menu.

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
_MAX_USSD_BODY = 182               # safe AT limit (chars total, incl. CON/END prefix)
_MORE_OPTIONS  = "\n1.More tips\n0.Main menu"   # 22 chars — appended to tip CON responses

# ── Max raw text length — guards against excessively long / malformed inputs ──
_MAX_INPUT_LEN = 200

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

# ── Resume position labels ────────────────────────────────────────────────────

_CAT_LABELS: dict[str, str] = {
    "1": "Business", "2": "Farming", "3": "Health",
    "4": "Education", "5": "Ask AI", "6": "Account",
}
_ROUTE_TO_CAT: dict[str, str] = {
    "1": "business", "2": "farming", "3": "health", "4": "education",
}
_TOPIC_SHORT: dict[str, dict[str, str]] = {
    "business":  {"1": "Pricing",    "2": "Bookkeeping", "3": "Marketing",  "4": "Customers"},
    "farming":   {"1": "Soil tips",  "2": "Pest ctrl",   "3": "Best crops", "4": "Prices"},
    "health":    {"1": "Nutrition",  "2": "Hygiene",     "3": "Maternal",   "4": "Child hlth"},
    "education": {"1": "Study tips", "2": "Career",      "3": "Math",       "4": "English"},
}


def _get_position_label(level1: str, sub: list[str]) -> str:
    """Human-readable label for the resume prompt, e.g. 'Business: Bookkeeping'."""
    cat_label = _CAT_LABELS.get(level1, "Menu")
    cat_key   = _ROUTE_TO_CAT.get(level1)
    if not sub or not cat_key:
        return cat_label
    topic = _TOPIC_SHORT.get(cat_key, {}).get(sub[0])
    return f"{cat_label}: {topic}" if topic else cat_label


# ── Input sanitisation ────────────────────────────────────────────────────────

def _sanitize(text: str) -> tuple[str, list[str]]:
    """
    Clean raw USSD text and split into input segments.

    Returns (clean_text, segments) where:
      clean_text — normalised string suitable as a Redis resume key
      segments   — list of non-empty, stripped segment strings

    Handles:
      • Trailing '#' from AT (e.g. "*384*72275#" → stripped by AT, but just in case)
      • Double-star  "1**2"  → ["1", "2"]  (empty segments discarded)
      • Whitespace around segments  " 1 * 2 " → ["1", "2"]
      • Length guard: inputs > 200 chars treated as empty (returns error flag)
    """
    raw = (text or "").strip().rstrip("#").strip()

    # Length guard — prevent excessively long / abusive inputs
    if len(raw) > _MAX_INPUT_LEN:
        return "__TOO_LONG__", []

    segments = [p.strip() for p in raw.split("*") if p.strip()]
    return raw, segments


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
    await _ensure_user_cached(phone_number, db)

    # 1. Sanitise input
    clean, inputs = _sanitize(text)
    if clean == "__TOO_LONG__":
        return "END Input too long. Please dial again."

    # 2. Handle fresh dial (text is empty / no segments)
    if not inputs:
        resume = await session_service.get_resume_position(phone_number)
        if resume:
            already_offered = await session_service.was_resume_offered(session_id)
            if not already_offered:
                await session_service.mark_resume_offered(session_id)
                label = resume.get("label", "last session")
                return (
                    f"CON Resume where you left off?\n"
                    f"1.Yes - {label}\n"
                    "2.New session"
                )
        return MAIN_MENU

    level1 = inputs[0]
    sub    = inputs[1:]

    # 3. Handle resume decision — the user responded to the "Resume?" prompt
    if await session_service.was_resume_offered(session_id):
        await session_service.clear_resume_offered(session_id)
        if level1 == "1":
            resume = await session_service.get_resume_position(phone_number)
            await session_service.clear_resume_position(phone_number)
            if resume and resume.get("text"):
                # Re-process with the saved text; the inner call handles routing
                return await process_ussd(session_id, phone_number, resume["text"], db)
        else:
            # "2" = new session, or any unexpected input → clear and show main menu
            await session_service.clear_resume_position(phone_number)
        return MAIN_MENU

    # 4. Normal routing — capture response so we can save position afterwards
    route = {
        "1": ("business",  BUSINESS_MENU),
        "2": ("farming",   FARMING_MENU),
        "3": ("health",    HEALTH_MENU),
        "4": ("education", EDUCATION_MENU),
    }

    if level1 in route:
        cat, menu = route[level1]
        response = await _handle_category(cat, menu, sub, session_id, phone_number, db)
    elif level1 == "5":
        response = await _handle_ask_ai(sub, session_id, phone_number, db)
    elif level1 == "6":
        response = await _handle_account(sub, phone_number, db)
    elif level1 == "0":
        response = MAIN_MENU
    else:
        response = "END Invalid option. Please dial again."

    # 5. Save / clear resume position
    #    • CON and not at root → save so user can resume if signal drops
    #    • END or explicit "0" → clear (session ended or user navigated to root)
    if response.startswith("CON") and level1 != "0":
        label = _get_position_label(level1, sub)
        await session_service.set_resume_position(phone_number, clean, label)
    else:
        await session_service.clear_resume_position(phone_number)

    return response


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
      []           → show category menu
      ["2"]        → first view of topic tip      (CON with More/Back)
      ["2","1"]    → "More tips" after first tip  (CON with More/Back)
      ["2","1","1"]→ another variation            (CON with More/Back)
      ["2","0"]    → back to main menu
      ["5"]        → prompt for free-form question
      ["5","q"]    → submit free-form question
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

    # post_actions: inputs received after the first tip was shown
    #   sub=["2"]         → []       first view of topic
    #   sub=["2","1"]     → ["1"]    first "More tips"
    #   sub=["2","1","1"] → ["1","1"]  second "More tips"
    #   sub=["2","0"]     → ["0"]    back to main
    post_actions = sub[1:]

    if not post_actions:
        return await _ask_and_respond(
            topic_map[choice], category, session_id, phone_number, db, show_more=True
        )

    last_action = post_actions[-1]

    if last_action == "0":
        return MAIN_MENU

    if last_action == "1":
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
        name_line = f"Name: {user.name}\n"           if user.name       else ""
        prof_line = f"Role: {user.profession}\n"      if user.profession else ""
        lang_line = f"Lang: {'Kinyarwanda' if user.language == 'rw' else 'English'}\n"
        sms_line  = "SMS: off\n"                      if user.sms_opt_out else ""
        since     = user.created_at.strftime("%b %Y") if user.created_at  else "recently"
        return (
            "END My Account\n"
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
            return f"END SMS alerts {status}.\nDial again to continue."
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

    show_more=True  → return CON with "1.More tips / 0.Main menu"
                       (used for pre-defined topics so users can keep browsing)
    show_more=False → return END (used for free-form questions)
    """
    question = question.strip()
    if not question:
        return "END Please enter a question."

    # Rate limit
    allowed, _remaining = await session_service.check_rate_limit(phone_number)
    if not allowed:
        return "END You have reached the hourly limit. Please try again later."

    # User preferences (profession, language, sms_opt_out)
    prefs       = await _get_cached_user_prefs(phone_number, db)
    profession  = prefs.get("profession")
    language    = prefs.get("language", "en") or "en"
    sms_opt_out = prefs.get("sms_opt_out", False)

    # Call AI service
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

    # Format response
    sms_sent = False

    if show_more:
        # Reserve space: "CON " (4) + options (22) = 26 overhead
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

    # Log interaction in background (own DB session — safe after HTTP response)
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
    """Create user record if it doesn't exist; skip if Redis flags it exists."""
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
    Old cache entries missing any of the three required keys are invalidated.
    """
    profile = await session_service.get_cached_profile(phone_number)
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
