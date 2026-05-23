"""
USSD menu state machine.

Africa's Talking sends a POST with:
  sessionId, serviceCode, phoneNumber, text (accumulated, *-separated)

We return:  "CON <text>" to continue the session (show next menu / prompt)
            "END <text>" to end the session

Menu tree:
  Main Menu
  ├── 1. Business  → tips + free question
  ├── 2. Farming   → tips + free question
  ├── 3. Health    → tips + free question
  ├── 4. Education → tips + free question
  ├── 5. Ask AI    → free-form question
  └── 6. Account   → stats, set name, set profession
"""
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..models.user import User
from ..models.interaction import Interaction
from ..services import ai_service, sms_service, session_service
from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# ── Menu text constants ───────────────────────────────────────────────────────

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
    "0.Main menu"
)

# Pre-defined topic questions per category (sent to AI with category system prompt)
_TOPICS: dict[str, dict[str, str]] = {
    "business": {
        "1": "Give one practical tip for pricing products to make profit at a small market stall in Africa.",
        "2": "Give one simple bookkeeping tip a small African business owner with no accounting background can use today.",
        "3": "Give one low-cost marketing idea for a small shop or market stall in Africa.",
        "4": "Give one tip for attracting new customers to a small business in a local African market.",
    },
    "farming": {
        "1": "Give one practical soil preparation tip for a smallholder farmer in East Africa growing maize or vegetables.",
        "2": "Give one effective pest control tip for a smallholder farmer in Africa with limited chemicals.",
        "3": "Recommend the best crop for a small African farmer to grow now for both food and income.",
        "4": "Give one tip to help an African smallholder farmer get a fair price for their harvest at the market.",
    },
    "health": {
        "1": "Give one practical nutrition tip for a family in rural Africa on a low income.",
        "2": "Give the most important hygiene tip to prevent common illnesses in African households.",
        "3": "Give one important maternal health tip for pregnant women in rural Africa.",
        "4": "Give one key child health tip for parents in rural Africa.",
    },
    "education": {
        "1": "Give one highly effective study technique for a secondary school student in Africa.",
        "2": "Give one practical career planning tip for a student in Africa choosing their future path.",
        "3": "Give one tip to help a student improve at mathematics.",
        "4": "Give one practical tip to improve English communication skills for a student in Africa.",
    },
}


# ── Main entry point ──────────────────────────────────────────────────────────

async def process_ussd(
    session_id: str,
    phone_number: str,
    text: str,
    db: AsyncSession,
) -> str:
    """
    Parse the accumulated USSD text and return the appropriate CON/END response.
    """
    # Ensure user record exists
    await _ensure_user(phone_number, db)

    # Parse inputs
    clean_text = (text or "").strip()
    inputs = [p.strip() for p in clean_text.split("*")] if clean_text else []

    if not inputs:
        return MAIN_MENU

    level1 = inputs[0]
    sub = inputs[1:]  # remaining inputs after the first choice

    if level1 == "1":
        return await _handle_category("business", BUSINESS_MENU, sub, session_id, phone_number, db)
    elif level1 == "2":
        return await _handle_category("farming", FARMING_MENU, sub, session_id, phone_number, db)
    elif level1 == "3":
        return await _handle_category("health", HEALTH_MENU, sub, session_id, phone_number, db)
    elif level1 == "4":
        return await _handle_category("education", EDUCATION_MENU, sub, session_id, phone_number, db)
    elif level1 == "5":
        return await _handle_ask_ai(sub, session_id, phone_number, db)
    elif level1 == "6":
        return await _handle_account(sub, phone_number, db)
    elif level1 == "0":
        return MAIN_MENU
    else:
        return "END Invalid option. Please dial again."


# ── Category handler (Business / Farming / Health / Education) ────────────────

async def _handle_category(
    category: str,
    menu_text: str,
    sub: list[str],
    session_id: str,
    phone_number: str,
    db: AsyncSession,
) -> str:
    if not sub:
        return menu_text

    choice = sub[0]

    if choice == "0":
        return MAIN_MENU

    # Option 5 — free-form question
    if choice == "5":
        if len(sub) == 1:
            return f"CON Your {category} question:"
        question = "*".join(sub[1:])  # restore any * the user may have typed
        return await _ask_and_respond(question, category, session_id, phone_number, db)

    # Options 1-4 — pre-defined topic
    topic_map = _TOPICS.get(category, {})
    if choice in topic_map:
        question = topic_map[choice]
        return await _ask_and_respond(question, category, session_id, phone_number, db)

    return f"END Invalid option."


# ── Ask AI direct (option 5 from main menu) ───────────────────────────────────

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


# ── Account menu ──────────────────────────────────────────────────────────────

async def _handle_account(sub: list[str], phone_number: str, db: AsyncSession) -> str:
    if not sub:
        return ACCOUNT_MENU

    choice = sub[0]

    if choice == "0":
        return MAIN_MENU

    elif choice == "1":
        # Show stats
        user = await _get_user(phone_number, db)
        name_str = f"Name: {user.name}\n" if user.name else ""
        prof_str = f"Role: {user.profession}\n" if user.profession else ""
        return (
            f"END My Account\n"
            f"{name_str}"
            f"{prof_str}"
            f"Queries: {user.total_queries}\n"
            f"Member since: {user.created_at.strftime('%b %Y')}"
        )

    elif choice == "2":
        # Set name
        if len(sub) == 1:
            return "CON Enter your name:"
        name = " ".join(sub[1:])[:100]
        await _update_user(phone_number, {"name": name}, db)
        await session_service.clear_profile_cache(phone_number)
        return f"END Name saved: {name}\nDial again to continue."

    elif choice == "3":
        # Set profession
        if len(sub) == 1:
            return (
                "CON Select profession:\n"
                "1.Farmer\n"
                "2.Student\n"
                "3.Business owner\n"
                "4.Other"
            )
        prof_map = {"1": "farmer", "2": "student", "3": "business owner", "4": "other"}
        profession = prof_map.get(sub[1])
        if not profession:
            return "END Invalid option."
        await _update_user(phone_number, {"profession": profession}, db)
        await session_service.clear_profile_cache(phone_number)
        return f"END Profession saved: {profession}\nAI will now personalise tips for you."

    return "END Invalid option."


# ── Core AI call + formatting ─────────────────────────────────────────────────

async def _ask_and_respond(
    question: str,
    category: str,
    session_id: str,
    phone_number: str,
    db: AsyncSession,
) -> str:
    """Call AI, format response, log to DB. Returns CON/END string."""
    if not question.strip():
        return "END Please enter a question."

    try:
        result = await ai_service.get_ai_response(question, category, phone_number)
        ai_text = result.text
        tokens = result.tokens_used
        from_cache = result.from_cache

    except Exception as exc:
        log.error("AI service error for %s: %s", phone_number, exc)
        return "END Sorry, AI is busy. Please try again in a moment."

    # ── Decide whether to offer SMS ──────────────────────────────────────────
    sms_offered = len(ai_text) > settings.sms_char_limit
    sms_sent = False

    if sms_offered:
        # Auto-send full answer via SMS and show short version on USSD
        full_sms = sms_service.format_sms_response(category, question, ai_text)
        sms_sent = await sms_service.send_sms(phone_number, full_sms)
        # Truncate for USSD display
        display_text = ai_text[: settings.sms_char_limit - 3] + "..."
        sms_note = "\n\nFull answer sent via SMS." if sms_sent else ""
        response_str = f"END {display_text}{sms_note}"
    else:
        response_str = f"END {ai_text}"

    # ── Log interaction to DB (fire-and-forget, don't block USSD response) ──
    asyncio.create_task(
        _log_interaction(
            session_id=session_id,
            phone_number=phone_number,
            category=category,
            question=question,
            response=ai_text,
            tokens_used=tokens,
            from_cache=from_cache,
            sms_sent=sms_sent,
            db=db,
        )
    )

    return response_str


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _ensure_user(phone_number: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.phone_number == phone_number))
    if result.scalar_one_or_none() is None:
        db.add(User(phone_number=phone_number))
        await db.commit()


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


async def _log_interaction(
    session_id: str,
    phone_number: str,
    category: str,
    question: str,
    response: str,
    tokens_used: int,
    from_cache: bool,
    sms_sent: bool,
    db: AsyncSession,
) -> None:
    try:
        interaction = Interaction(
            session_id=session_id,
            phone_number=phone_number,
            category=category,
            question=question,
            response=response,
            tokens_used=tokens_used,
            from_cache=from_cache,
            sms_sent=sms_sent,
        )
        db.add(interaction)
        # Increment user query counter
        await db.execute(
            update(User)
            .where(User.phone_number == phone_number)
            .values(total_queries=User.total_queries + 1)
        )
        await db.commit()
    except Exception as exc:
        log.error("Failed to log interaction: %s", exc)
