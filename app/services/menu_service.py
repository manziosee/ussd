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
  ├─ 1. Business    →  4 tips · My question · Calculator
  ├─ 2. Farming     →  4 tips · My question · Market prices · Nearby offices
  ├─ 3. Health      →  4 tips · My question · Nearby clinics · Emergency
  ├─ 4. Education   →  4 tips · My question · Nearby schools
  ├─ 5. Ask AI      →  free-form question  (paginated for long answers)
  └─ 6. Account     →  stats · name · profession · language · SMS · Daily tips

After each predefined tip (CON response):
  1.More tips      →  variation tip (different angle on same topic)
  2.More detail    →  elaboration tip (builds on what was just shown)
  3.Send SMS       →  deliver full tip to user's phone as SMS
  4.Helpful        →  positive feedback (stored in DB)
  5.Not helpful    →  negative feedback (stored in DB)
  0.Back           →  main menu

Free-form responses > 160 chars are paginated:
  CON [first 160 chars]
  1.Next
  0.Stop

Input sanitisation
──────────────────
_sanitize(): strips '#', collapses '**', trims whitespace, rejects >200 chars.

Session resume after drop
─────────────────────────
Position saved on every CON → offered on fresh dial if within 10-min TTL.

Multilingual error messages
───────────────────────────
_t(key, language) returns English or Kinyarwanda error string.
Language is fetched from profile cache once per request and threaded through.

Bug notes
─────────
_log_interaction_bg() creates its OWN DB session (AsyncSessionLocal) — safe
for fire-and-forget via asyncio.create_task.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import AsyncSessionLocal
from ..models.feedback import Feedback
from ..models.interaction import Interaction
from ..models.market_price import MarketPrice
from ..models.user import User
from ..services import ai_service, session_service, sms_service

log = logging.getLogger(__name__)
settings = get_settings()

# ── AT USSD body limit & navigation suffix ────────────────────────────────────
_MAX_USSD_BODY = 182
# Options appended after each predefined tip
_MORE_OPTIONS  = "\n1.More tips\n2.More detail\n3.Send SMS\n4.Helpful\n5.Not helpful\n0.Back"
_MAX_INPUT_LEN = 200
# Page size for paginated free-form answers (leaves room for "CON " + "\n1.Next\n0.Stop")
_PAGE_SIZE     = 160  # 182 - 4 ("CON ") - 14 ("\n1.Next\n0.Stop") = 164; use 160 for safety
_PAGE_NAV      = "\n1.Next\n0.Stop"

# ── Multilingual error strings ─────────────────────────────────────────────────

_STRINGS: dict[str, dict[str, str]] = {
    "invalid_option": {
        "en": "Invalid option. Please try again.",
        "rw": "Amahitamo mabi. Ongera ugerageze.",
    },
    "invalid_choice": {
        "en": "Invalid choice.",
        "rw": "Ihitamo mabi.",
    },
    "invalid_number": {
        "en": "Please enter a valid number (digits only).",
        "rw": "Injiza umubare ukuri (imibare gusa).",
    },
    "too_long": {
        "en": "Input too long. Please dial again.",
        "rw": "Injiza ndende cyane. Vugisha inomero.",
    },
    "no_question": {
        "en": "Please enter a question.",
        "rw": "Injiza ikibazo cyawe.",
    },
    "ai_busy": {
        "en": "AI is busy. Please try again in a moment.",
        "rw": "AI iraruhutse. Ongera ugerageze.",
    },
    "rate_limit": {
        "en": "Hourly limit reached. Please try again later.",
        "rw": "Wageze ku mupaka w'isaha. Ongera ugerageze nyuma.",
    },
    "name_empty": {
        "en": "Name cannot be empty. Dial again.",
        "rw": "Izina ntirishobora kuba ubusa. Vugisha inomero.",
    },
    "no_services": {
        "en": "No services listed for this area yet.",
        "rw": "Nta serivisi zianditswe muri uwo murenge.",
    },
    "system_error": {
        "en": "System error. Please try again.",
        "rw": "Ikibazo cya sisitemu. Ongera ugerageze.",
    },
    "sms_sent": {
        "en": "Tip sent to your number. Dial again for more.",
        "rw": "Inama yoherejwe kuri numero yawe. Vugisha kugira ngo ubone indi.",
    },
    "sms_failed": {
        "en": "Could not send SMS. Please try again.",
        "rw": "Ntibyashobotse kohereza SMS. Ongera ugerageze.",
    },
    "feedback_thanks": {
        "en": "Thanks for your feedback! Dial again for more.",
        "rw": "Urakoze icyo watuganiriye! Vugisha kugira ngo ubone indi.",
    },
    "no_prices": {
        "en": "No prices listed yet. Try again tomorrow.",
        "rw": "Nta biciro bihari ubu. Ongera ugerageze ejo.",
    },
}


def _t(key: str, lang: str = "en") -> str:
    """Return the localised string for key in lang (falls back to English)."""
    bucket = _STRINGS.get(key, {})
    return bucket.get(lang) or bucket.get("en") or key


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
    "6.Calculator\n"
    "0.Main menu"
)

FARMING_MENU = (
    "CON Farming Guide\n"
    "1.Soil tips\n"
    "2.Pest control\n"
    "3.Best crops\n"
    "4.Market prices\n"
    "5.My question\n"
    "6.Nearby offices\n"
    "0.Main menu"
)

HEALTH_MENU = (
    "CON Health Info\n"
    "1.Nutrition tips\n"
    "2.Hygiene tips\n"
    "3.Maternal health\n"
    "4.Child health\n"
    "5.My question\n"
    "6.Nearby clinics\n"
    "7.Emergency\n"
    "0.Main menu"
)

EDUCATION_MENU = (
    "CON Education Help\n"
    "1.Study tips\n"
    "2.Career guide\n"
    "3.Math help\n"
    "4.English tips\n"
    "5.My question\n"
    "6.Nearby schools\n"
    "0.Main menu"
)

ACCOUNT_MENU = (
    "CON My Account\n"
    "1.My stats\n"
    "2.Set my name\n"
    "3.Set profession\n"
    "4.Language\n"
    "5.SMS alerts\n"
    "6.Daily tips\n"
    "0.Main menu"
)

CALCULATOR_MENU = (
    "CON Calculator\n"
    "1.Profit check\n"
    "2.Loan payment\n"
    "0.Back"
)

DISTRICT_MENU = (
    "CON Select your district:\n"
    "1.Kigali\n"
    "2.Musanze\n"
    "3.Huye\n"
    "4.Rubavu\n"
    "5.Kayonza\n"
    "0.Back"
)

# Pre-defined topic questions sent to AI per category
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
        # Note: farming option "4" (Market prices) is handled by _handle_market_prices, not AI
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
    "business":  {"1": "Pricing",    "2": "Bookkeeping", "3": "Marketing",  "4": "Customers",  "6": "Calculator"},
    "farming":   {"1": "Soil tips",  "2": "Pest ctrl",   "3": "Best crops", "4": "Prices",     "6": "Offices"},
    "health":    {"1": "Nutrition",  "2": "Hygiene",     "3": "Maternal",   "4": "Child hlth", "6": "Clinics",  "7": "Emergency"},
    "education": {"1": "Study tips", "2": "Career",      "3": "Math",       "4": "English",    "6": "Schools"},
}


def _get_position_label(level1: str, sub: list[str]) -> str:
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

    Handles:
      • Trailing '#'    — strip (AT sometimes appends it)
      • Double-star '**' — empty segments discarded
      • Whitespace      — stripped from every segment
      • Length guard    — inputs > 200 chars rejected ("__TOO_LONG__")
    """
    raw = (text or "").strip().rstrip("#").strip()
    if len(raw) > _MAX_INPUT_LEN:
        return "__TOO_LONG__", []
    segments = [p.strip() for p in raw.split("*") if p.strip()]
    return raw, segments


# ── Pagination helpers ────────────────────────────────────────────────────────

def _split_pages(text: str, size: int = _PAGE_SIZE) -> list[str]:
    """Split text into chunks of at most `size` chars, preferring word boundaries."""
    if len(text) <= size:
        return [text]
    pages = []
    remaining = text
    while len(remaining) > size:
        cut = remaining[:size].rfind(" ")
        if cut < size * 0.7:
            cut = size
        pages.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        pages.append(remaining)
    return pages


async def _make_paged_or_end(session_id: str, ai_text: str) -> str:
    """
    If text fits in one page return END, otherwise store remaining pages in
    Redis and return first page as CON with 1.Next / 0.Stop navigation.
    """
    pages = _split_pages(ai_text)
    if len(pages) == 1:
        return f"END {ai_text}"
    await session_service.set_paged_response(session_id, pages[1:])
    return f"CON {pages[0]}{_PAGE_NAV}"


# ── Main entry point ───────────────────────────────────────────────────────────

async def process_ussd(
    session_id: str,
    phone_number: str,
    text: str,
    db: AsyncSession,
) -> str:
    """Parse accumulated USSD text and return the appropriate CON / END string."""
    await _ensure_user_cached(phone_number, db)

    # Fetch user prefs once — used for language, profession, sms_opt_out
    prefs    = await _get_cached_user_prefs(phone_number, db)
    language = prefs.get("language", "en") or "en"

    # Sanitise
    clean, inputs = _sanitize(text)
    if clean == "__TOO_LONG__":
        return f"END {_t('too_long', language)}"

    # ── First-time onboarding: new users choose language then profession ───────
    if not prefs.get("onboarded", True):
        return await _handle_onboarding(inputs, phone_number, db)

    # ── Pagination: active if we stashed pages for a previous response ─────────
    if inputs and await session_service.has_pending_pages(session_id):
        last_seg = inputs[-1]
        if last_seg == "1":
            page = await session_service.pop_next_page(session_id)
            has_more = await session_service.has_pending_pages(session_id)
            if page:
                if has_more:
                    await session_service.set_resume_position(phone_number, clean, "AI response")
                    return f"CON {page}{_PAGE_NAV}"
                else:
                    await session_service.clear_resume_position(phone_number)
                    return f"END {page}"
        elif last_seg == "0":
            await session_service.clear_paged_response(session_id)
            await session_service.clear_resume_position(phone_number)
            return MAIN_MENU
        else:
            await session_service.clear_paged_response(session_id)

    # ── Fresh dial ────────────────────────────────────────────────────────────
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

    # ── Resume decision ───────────────────────────────────────────────────────
    if await session_service.was_resume_offered(session_id):
        await session_service.clear_resume_offered(session_id)
        if level1 == "1":
            resume = await session_service.get_resume_position(phone_number)
            await session_service.clear_resume_position(phone_number)
            if resume and resume.get("text"):
                return await process_ussd(session_id, phone_number, resume["text"], db)
        else:
            await session_service.clear_resume_position(phone_number)
        return MAIN_MENU

    # ── Normal routing ────────────────────────────────────────────────────────
    route = {
        "1": ("business",  BUSINESS_MENU),
        "2": ("farming",   FARMING_MENU),
        "3": ("health",    HEALTH_MENU),
        "4": ("education", EDUCATION_MENU),
    }

    if level1 in route:
        cat, menu = route[level1]
        response = await _handle_category(cat, menu, sub, session_id, phone_number, db, prefs, language)
    elif level1 == "5":
        response = await _handle_ask_ai(sub, session_id, phone_number, db, language)
    elif level1 == "6":
        response = await _handle_account(sub, phone_number, db, language)
    elif level1 == "0":
        response = MAIN_MENU
    else:
        response = f"END {_t('invalid_option', language)}"

    # ── Save / clear resume position ──────────────────────────────────────────
    if response.startswith("CON") and level1 != "0":
        label = _get_position_label(level1, sub)
        await session_service.set_resume_position(phone_number, clean, label)
    else:
        await session_service.clear_resume_position(phone_number)

    return response


# ── First-time onboarding ─────────────────────────────────────────────────────

async def _handle_onboarding(
    inputs: list[str],
    phone_number: str,
    db: AsyncSession,
) -> str:
    """
    Two-step setup for new users: language → profession → MAIN_MENU.

    inputs=[]      → language choice
    inputs=["1"]   → English selected, show profession menu
    inputs=["2"]   → Kinyarwanda selected, show profession menu (in Kinyarwanda)
    inputs=["X","Y"] → save language + profession, mark onboarded, return main menu
    """
    _LANG_MENU = (
        "CON Welcome to SmartAssist!\n"
        "Choose language:\n"
        "1.English\n"
        "2.Kinyarwanda"
    )
    _PROF_EN = (
        "CON Your role:\n"
        "1.Farmer\n"
        "2.Student\n"
        "3.Business owner\n"
        "4.Other"
    )
    _PROF_RW = (
        "CON Urimo iki:\n"
        "1.Umuhinzi\n"
        "2.Umunyeshuri\n"
        "3.Ubucuruzi\n"
        "4.Ikindi"
    )

    if not inputs:
        return _LANG_MENU

    lang_map = {"1": "en", "2": "rw"}
    lang = lang_map.get(inputs[0])
    if not lang:
        return _LANG_MENU

    if len(inputs) == 1:
        return _PROF_RW if lang == "rw" else _PROF_EN

    prof_map = {"1": "farmer", "2": "student", "3": "business owner", "4": "other"}
    profession = prof_map.get(inputs[1])
    if not profession:
        return _PROF_RW if lang == "rw" else _PROF_EN

    await _update_user(phone_number, {"language": lang, "profession": profession, "onboarded": True}, db)
    await session_service.clear_profile_cache(phone_number)
    return MAIN_MENU


# ── Category handler ───────────────────────────────────────────────────────────

async def _handle_category(
    category: str,
    menu_text: str,
    sub: list[str],
    session_id: str,
    phone_number: str,
    db: AsyncSession,
    prefs: dict,
    language: str = "en",
) -> str:
    """
    Route within a category.

    sub  = everything after the level-1 digit:
      []             → show category menu
      ["2"]          → first tip (CON with More/Detail/Send/Rate/Back)
      ["2","1"]      → "More tips" variation
      ["2","2"]      → "More detail" elaboration
      ["2","3"]      → "Send SMS" — send full tip to phone
      ["2","4"]      → "Helpful" feedback
      ["2","5"]      → "Not helpful" feedback
      ["2","0"]      → main menu
      ["4"]          → market prices (farming) or AI tip (others)
      ["5"]          → prompt for free question
      ["5","q"]      → free question (paginated if long)
      ["6"]          → calculator (business) OR services directory (others)
      ["7"]          → emergency numbers (health only)
    """
    if not sub:
        return menu_text

    choice = sub[0]

    if choice == "0":
        return MAIN_MENU

    # ── Option 5: free question ───────────────────────────────────────────────
    if choice == "5":
        if len(sub) == 1:
            label = category.capitalize()
            return f"CON Your {label} question:"
        question = "*".join(sub[1:])
        return await _ask_and_respond(question, category, session_id, phone_number, db, prefs)

    # ── Option 6: calculator (business) OR services directory ─────────────────
    if choice == "6":
        if category == "business":
            return await _handle_calculator(sub[1:], language)
        return await _handle_services(sub[1:], category, language)

    # ── Health option 7: emergency numbers ───────────────────────────────────
    if choice == "7" and category == "health":
        return _handle_emergency(language)

    # ── Farming option 4: real market prices (DB-backed, not AI guess) ────────
    if choice == "4" and category == "farming":
        return await _handle_market_prices(sub[1:], db, language)

    # ── Options 1–4 (and 1–3 for farming): predefined topics ─────────────────
    topic_map = _TOPICS.get(category, {})
    if choice not in topic_map:
        return f"END {_t('invalid_option', language)}"

    # post_actions = inputs after the first topic digit
    #   sub=["2"]             → []      first view
    #   sub=["2","1"]         → ["1"]   More tips
    #   sub=["2","2"]         → ["2"]   More detail
    #   sub=["2","3"]         → ["3"]   Send SMS
    #   sub=["2","4"]         → ["4"]   Helpful
    #   sub=["2","5"]         → ["5"]   Not helpful
    #   sub=["2","0"]         → ["0"]   back to main
    post_actions = sub[1:]

    if not post_actions:
        return await _ask_and_respond(
            topic_map[choice], category, session_id, phone_number, db, prefs, show_more=True
        )

    last_action = post_actions[-1]

    if last_action == "0":
        return MAIN_MENU

    if last_action == "1":
        variation_q = topic_map[choice] + " Give a completely different, fresh practical tip."
        return await _ask_and_respond(
            variation_q, category, session_id, phone_number, db, prefs, show_more=True
        )

    if last_action == "2":
        prev = await session_service.get_last_ai_response(phone_number, category)
        if prev:
            elaboration_q = (
                f"Building on this tip: {prev[:120]}\n\n"
                "Give ONE specific, additional action step that the user can take today."
            )
        else:
            elaboration_q = (
                topic_map[choice]
                + " Give one specific, follow-up action step with more practical detail."
            )
        return await _ask_and_respond(
            elaboration_q, category, session_id, phone_number, db, prefs, show_more=True
        )

    if last_action == "3":
        # Send full tip to user's phone as SMS
        tip = await session_service.get_last_ai_response(phone_number, category)
        if not tip:
            return f"END {_t('sms_failed', language)}"
        ok = await sms_service.send_sms(phone_number, tip)
        if ok:
            return f"END {_t('sms_sent', language)}"
        return f"END {_t('sms_failed', language)}"

    if last_action == "4":
        asyncio.create_task(
            _save_feedback_bg(session_id, phone_number, category, rating=1)
        )
        return f"END {_t('feedback_thanks', language)}"

    if last_action == "5":
        asyncio.create_task(
            _save_feedback_bg(session_id, phone_number, category, rating=-1)
        )
        return f"END {_t('feedback_thanks', language)}"

    return f"END {_t('invalid_option', language)}"


# ── Market prices (Farming menu option 4) ─────────────────────────────────────

async def _handle_market_prices(
    sub: list[str],
    db: AsyncSession,
    language: str = "en",
) -> str:
    """
    Show real crop market prices from DB, by district.

    sub = everything after the "4" choice in the Farming menu:
      []      → DISTRICT_MENU
      ["0"]   → back to Farming menu
      ["1-5"] → prices for that district
    """
    from ..data.services import DISTRICTS, DISTRICT_LABELS

    if not sub:
        return DISTRICT_MENU

    choice = sub[0]
    if choice == "0":
        return FARMING_MENU

    district = DISTRICTS.get(choice)
    if not district:
        return f"END {_t('invalid_option', language)}"

    result = await db.execute(
        select(MarketPrice)
        .where(MarketPrice.district == district)
        .order_by(MarketPrice.crop)
    )
    prices = result.scalars().all()

    if not prices:
        return f"END {_t('no_prices', language)}"

    district_label = DISTRICT_LABELS.get(district, district.capitalize())
    lines = [f"END {district_label} Market Prices"]
    for p in prices[:6]:
        lines.append(f"{p.crop}: {p.price_rwf:,} RWF/{p.unit}")

    # Add last-updated timestamp from most recent entry
    latest = max(p.updated_at for p in prices)
    lines.append(f"\nUpdated: {latest.strftime('%d %b %Y')}")

    output = "\n".join(lines)
    if len(output) > _MAX_USSD_BODY:
        output = output[: _MAX_USSD_BODY - 1] + "…"
    return output


# ── Emergency numbers (Health menu option 7) ──────────────────────────────────

def _handle_emergency(language: str = "en") -> str:
    from ..data.emergency import EMERGENCY_EN, EMERGENCY_RW
    return EMERGENCY_RW if language == "rw" else EMERGENCY_EN


# ── Financial calculator (Business menu option 6) ──────────────────────────────

async def _handle_calculator(sub: list[str], language: str = "en") -> str:
    """
    Pure-math USSD calculator — zero AI cost, zero network calls.

    sub = everything after the "6" choice in the Business menu:
      []                 → show calculator menu
      ["1"]              → profit: enter cost price
      ["1", cost]        → profit: enter selling price
      ["1", cost, price] → profit: show result
      ["2"]              → loan: enter principal
      ["2", P]           → loan: enter annual interest rate (%)
      ["2", P, r]        → loan: enter number of months
      ["2", P, r, n]     → loan: show result
      ["0"]              → back to Business menu
    """
    if not sub:
        return CALCULATOR_MENU

    mode = sub[0]
    args = sub[1:]

    if mode == "0":
        return BUSINESS_MENU

    # ── Profit calculator ─────────────────────────────────────────────────────
    if mode == "1":
        if not args:
            return "CON Enter cost price (RWF):\n(amount you paid)"
        cost_str = args[0]
        if not cost_str.lstrip("0").isdigit() or not cost_str.isdigit():
            return f"END {_t('invalid_number', language)}"
        cost = int(cost_str)

        if len(args) == 1:
            return "CON Enter selling price (RWF):\n(amount you charge)"
        price_str = args[1]
        if not price_str.isdigit():
            return f"END {_t('invalid_number', language)}"
        price = int(price_str)

        if price == 0:
            return f"END {_t('invalid_number', language)}"

        profit = price - cost
        margin = profit / price * 100
        profit_100 = profit * 100

        if profit <= 0:
            advice = "Below cost! Raise price."
        elif margin < 15:
            advice = "Low margin. Aim for 20%+."
        elif margin < 30:
            advice = "Decent margin. Keep tracking."
        else:
            advice = "Great margin!"

        return (
            "END Profit Analysis\n"
            f"Cost:    {cost:,} RWF\n"
            f"Price:   {price:,} RWF\n"
            f"Profit:  {profit:,} RWF/item\n"
            f"Margin:  {margin:.1f}%\n"
            f"x100 items: {profit_100:,} RWF\n"
            f"{advice}"
        )

    # ── Loan payment calculator ───────────────────────────────────────────────
    if mode == "2":
        if not args:
            return "CON Enter loan amount (RWF):"
        principal_str = args[0]
        if not principal_str.isdigit():
            return f"END {_t('invalid_number', language)}"
        principal = int(principal_str)

        if len(args) == 1:
            return "CON Annual interest rate (%):\n(e.g. 18 for 18%/yr)"
        rate_str = args[1]
        try:
            annual_rate = float(rate_str)
            if annual_rate < 0:
                raise ValueError
        except ValueError:
            return f"END {_t('invalid_number', language)}"

        if len(args) == 2:
            return "CON Loan duration (months):\n(e.g. 12 = 1 year)"
        months_str = args[2]
        if not months_str.isdigit() or int(months_str) <= 0:
            return f"END {_t('invalid_number', language)}"
        months = int(months_str)

        monthly_rate = annual_rate / 12 / 100
        if monthly_rate == 0:
            monthly = principal / months
        else:
            factor  = (1 + monthly_rate) ** months
            monthly = principal * monthly_rate * factor / (factor - 1)

        total          = monthly * months
        total_interest = total - principal

        return (
            "END Loan Calculator\n"
            f"Loan:    {principal:,} RWF\n"
            f"Rate:    {annual_rate:.1f}%/yr\n"
            f"Term:    {months} months\n"
            f"Monthly: {monthly:,.0f} RWF\n"
            f"Total:   {total:,.0f} RWF\n"
            f"Interest:{total_interest:,.0f} RWF"
        )

    return f"END {_t('invalid_option', language)}"


# ── Nearby services directory (Farming / Health / Education option 6) ──────────

async def _handle_services(
    sub: list[str],
    service_type: str,
    language: str = "en",
) -> str:
    from ..data.services import DISTRICTS, DISTRICT_LABELS, SERVICES, SERVICE_LABELS

    _back: dict[str, str] = {
        "farming":   FARMING_MENU,
        "health":    HEALTH_MENU,
        "education": EDUCATION_MENU,
    }

    if not sub:
        return DISTRICT_MENU

    choice = sub[0]
    if choice == "0":
        return _back.get(service_type, MAIN_MENU)

    district = DISTRICTS.get(choice)
    if not district:
        return f"END {_t('invalid_option', language)}"

    services = SERVICES.get(district, {}).get(service_type, [])
    if not services:
        return f"END {_t('no_services', language)}"

    district_label = DISTRICT_LABELS.get(district, district.capitalize())
    type_label     = SERVICE_LABELS.get(service_type, "Services")

    header = f"END {type_label} - {district_label}"
    lines  = [header]
    for svc in services[:3]:
        entry = f"{svc['name']}\nTel: {svc['tel']}"
        if svc.get("note"):
            entry += f"\n{svc['note']}"
        lines.append(entry)

    output = "\n\n".join(lines)
    if len(output) > _MAX_USSD_BODY:
        output = output[: _MAX_USSD_BODY - 1] + "…"
    return output


# ── Ask AI (main menu option 5) ────────────────────────────────────────────────

async def _handle_ask_ai(
    sub: list[str],
    session_id: str,
    phone_number: str,
    db: AsyncSession,
    language: str = "en",
) -> str:
    if not sub:
        return "CON Ask AI anything:\n(type your question)"
    question = "*".join(sub)
    prefs = await _get_cached_user_prefs(phone_number, db)
    return await _ask_and_respond(question, "general", session_id, phone_number, db, prefs)


# ── Account menu ───────────────────────────────────────────────────────────────

async def _handle_account(
    sub: list[str],
    phone_number: str,
    db: AsyncSession,
    language: str = "en",
) -> str:
    if not sub:
        return ACCOUNT_MENU

    choice = sub[0]

    if choice == "0":
        return MAIN_MENU

    elif choice == "1":
        user = await _get_user(phone_number, db)
        name_line  = f"Name: {user.name}\n"            if user.name         else ""
        prof_line  = f"Role: {user.profession}\n"       if user.profession   else ""
        lang_name  = "Kinyarwanda" if (user.language or "en") == "rw" else "English"
        lang_line  = f"Lang: {lang_name}\n"
        sms_line   = "SMS: off\n"                       if user.sms_opt_out  else ""
        tips_cat   = user.daily_tip_category or "auto"
        tips_line  = f"Daily tips: {tips_cat}\n" if user.daily_tips_enabled  else ""
        since      = user.created_at.strftime("%b %Y") if user.created_at    else "recently"
        return (
            "END My Account\n"
            f"{name_line}{prof_line}{lang_line}{sms_line}{tips_line}"
            f"Queries: {user.total_queries}\n"
            f"Since: {since}"
        )

    elif choice == "2":
        if len(sub) == 1:
            return "CON Enter your name:"
        name = " ".join(sub[1:])[:100].strip()
        if not name:
            return f"END {_t('name_empty', language)}"
        await _update_user(phone_number, {"name": name}, db)
        await session_service.clear_profile_cache(phone_number)
        return f"END Name saved: {name}\nDial again to continue."

    elif choice == "3":
        if len(sub) == 1:
            return (
                "CON Select your role:\n"
                "1.Farmer\n"
                "2.Student\n"
                "3.Business owner\n"
                "4.Other"
            )
        prof_map   = {"1": "farmer", "2": "student", "3": "business owner", "4": "other"}
        profession = prof_map.get(sub[1])
        if not profession:
            return f"END {_t('invalid_choice', language)}"
        await _update_user(phone_number, {"profession": profession}, db)
        await session_service.clear_profile_cache(phone_number)
        return (
            f"END Role saved: {profession}\n"
            "AI will personalise tips for you.\n"
            "Dial again to continue."
        )

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
        lang     = lang_map.get(action)
        if not lang:
            return f"END {_t('invalid_choice', language)}"
        await _update_user(phone_number, {"language": lang}, db)
        await session_service.clear_profile_cache(phone_number)
        lang_name = "Kinyarwanda" if lang == "rw" else "English"
        return (
            f"END Language set: {lang_name}\n"
            "AI will now reply in your language.\n"
            "Dial again to continue."
        )

    elif choice == "5":
        user = await _get_user(phone_number, db)
        if len(sub) == 1:
            status = "OFF" if user.sms_opt_out else "ON"
            toggle = "Turn off SMS" if not user.sms_opt_out else "Turn on SMS"
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
        return f"END {_t('invalid_option', language)}"

    elif choice == "6":
        user = await _get_user(phone_number, db)

        if len(sub) == 1:
            if user.daily_tips_enabled:
                cat = (user.daily_tip_category or "auto").capitalize()
                return (
                    f"CON Daily tips: ON\n"
                    f"Category: {cat}\n"
                    "1.Turn off\n"
                    "2.Change category\n"
                    "0.Back"
                )
            else:
                return (
                    "CON Daily tips: OFF\n"
                    "Get a morning SMS tip daily.\n"
                    "1.Turn on\n"
                    "0.Back"
                )

        action = sub[1]

        if action == "0":
            return ACCOUNT_MENU

        if action == "1":
            new_val = not user.daily_tips_enabled
            await _update_user(phone_number, {"daily_tips_enabled": new_val}, db)
            await session_service.clear_profile_cache(phone_number)
            if new_val:
                return (
                    "END Daily tips enabled!\n"
                    "You'll get a morning SMS tip daily.\n"
                    "Dial again to continue."
                )
            return "END Daily tips disabled.\nDial again to continue."

        if action == "2" and user.daily_tips_enabled:
            if len(sub) == 2:
                return (
                    "CON Select tip category:\n"
                    "1.Business\n"
                    "2.Farming\n"
                    "3.Health\n"
                    "4.Education\n"
                    "0.Back"
                )
            cat_map = {"1": "business", "2": "farming", "3": "health", "4": "education"}
            new_cat = cat_map.get(sub[2])
            if not new_cat:
                return f"END {_t('invalid_choice', language)}"
            await _update_user(phone_number, {"daily_tip_category": new_cat}, db)
            await session_service.clear_profile_cache(phone_number)
            return (
                f"END Daily tips: {new_cat.capitalize()}\n"
                "Dial again to continue."
            )

        return f"END {_t('invalid_option', language)}"

    return f"END {_t('invalid_option', language)}"


# ── Core AI call + formatting ──────────────────────────────────────────────────

async def _ask_and_respond(
    question: str,
    category: str,
    session_id: str,
    phone_number: str,
    db: AsyncSession,
    prefs: dict,
    show_more: bool = False,
) -> str:
    """
    Call AI (or knowledge cache), format response, fire-and-forget log.

    prefs       — dict from _get_cached_user_prefs (profession, language, sms_opt_out)
    show_more   — True for predefined topics (CON + More/Detail/Send/Rate/Back)
                  False for free-form questions (END, or paginated CON if long)
    """
    question = question.strip()
    if not question:
        language = prefs.get("language", "en")
        return f"END {_t('no_question', language)}"

    language    = prefs.get("language", "en") or "en"
    profession  = prefs.get("profession")
    sms_opt_out = prefs.get("sms_opt_out", False)

    # Rate limit
    allowed, _remaining = await session_service.check_rate_limit(phone_number)
    if not allowed:
        return f"END {_t('rate_limit', language)}"

    # AI call
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
        return f"END {_t('ai_busy', language)}"

    # Save last response for "More detail" and "Send SMS" follow-up
    await session_service.set_last_ai_response(phone_number, category, ai_text)

    sms_sent = False

    if show_more:
        # CON with navigation — overhead = len("CON ") + len(_MORE_OPTIONS) = 4 + 68 = 72
        max_tip = _MAX_USSD_BODY - len("CON ") - len(_MORE_OPTIONS)
        if len(ai_text) > max_tip:
            ai_text = ai_text[:max_tip - 1] + "…"
        response_str = f"CON {ai_text}{_MORE_OPTIONS}"

    elif not sms_opt_out and settings.sms_enabled and len(ai_text) > settings.sms_char_limit:
        # Long response: send full answer via SMS, show truncated on USSD
        full_sms = sms_service.format_sms_response(category, question, ai_text)
        sms_sent = await sms_service.send_sms(phone_number, full_sms)
        if sms_sent:
            display      = ai_text[: settings.sms_char_limit - 3] + "..."
            response_str = f"END {display}\n\nFull answer sent via SMS."
        else:
            # SMS failed — paginate instead
            response_str = await _make_paged_or_end(session_id, ai_text)

    elif len(ai_text) > settings.sms_char_limit:
        # sms_opt_out=True or SMS disabled — paginate long answers
        response_str = await _make_paged_or_end(session_id, ai_text)

    else:
        response_str = f"END {ai_text}"

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
    """Return cached user prefs. Invalidates stale entries missing required keys."""
    profile = await session_service.get_cached_profile(phone_number)
    if profile and {"profession", "language", "sms_opt_out", "onboarded"}.issubset(profile):
        return profile
    user  = await _get_user(phone_number, db)
    prefs = {
        "name":               user.name,
        "profession":         user.profession,
        "language":           user.language or "en",
        "sms_opt_out":        bool(user.sms_opt_out),
        "daily_tips_enabled": bool(user.daily_tips_enabled),
        "daily_tip_category": user.daily_tip_category,
        # Default True so existing cached profiles without this key pass through
        "onboarded":          bool(getattr(user, "onboarded", True)),
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
    """Background task — own DB session, safe after HTTP response is sent."""
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


async def _save_feedback_bg(
    session_id: str,
    phone_number: str,
    category: str,
    rating: int,
) -> None:
    """Background task — save user rating to feedback table."""
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                Feedback(
                    session_id=session_id,
                    phone_number=phone_number,
                    category=category,
                    rating=rating,
                )
            )
            await db.commit()
    except Exception as exc:
        log.error("Failed to save feedback for %s: %s", phone_number, exc)
