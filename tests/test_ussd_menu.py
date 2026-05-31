"""
Tests for the USSD menu state machine (menu_service.process_ussd).

Each test simulates what Africa's Talking sends after a user's keypress:
  text=""          →  fresh dial
  text="1"         →  user pressed 1 from main menu
  text="1*2"       →  user pressed 2 inside business submenu
  text="1*5*query" →  user typed a free-form question in the business category
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.services.menu_service import process_ussd

SESSION = "test-session-001"
PHONE   = "+250788000001"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def ussd(text: str, db, session=SESSION, phone=PHONE) -> str:
    return await process_ussd(session, phone, text, db)


def is_con(r: str) -> bool:
    return r.startswith("CON ")


def is_end(r: str) -> bool:
    return r.startswith("END ")


# ── Main menu ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_main_menu_fresh_dial(mock_db):
    r = await ussd("", mock_db)
    assert is_con(r)
    assert "SmartAssist" in r
    assert "1.Business" in r
    assert "5.Ask AI" in r
    assert "6.Account" in r


@pytest.mark.asyncio
async def test_main_menu_back_from_option_0(mock_db):
    r = await ussd("0", mock_db)
    assert is_con(r)
    assert "SmartAssist" in r


@pytest.mark.asyncio
async def test_invalid_main_option(mock_db):
    r = await ussd("9", mock_db)
    assert is_end(r)
    assert "Invalid" in r


# ── Business submenu ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_business_submenu_shown(mock_db):
    r = await ussd("1", mock_db)
    assert is_con(r)
    assert "Business" in r
    assert "1.Pricing" in r
    assert "5.My question" in r


@pytest.mark.asyncio
async def test_business_back_to_main(mock_db):
    r = await ussd("1*0", mock_db)
    assert is_con(r)
    assert "SmartAssist" in r


@pytest.mark.asyncio
async def test_business_predefined_topic(mock_db, mock_ai):
    """Pre-defined topic 1 (pricing) returns CON with More/Detail/Back options."""
    r = await ussd("1*1", mock_db)
    assert is_con(r), f"Expected CON, got: {r[:80]}"
    mock_ai.assert_awaited_once()
    assert "Test AI response" in r
    assert "1.More tips" in r
    assert "2.More detail" in r
    assert "0.Back" in r


@pytest.mark.asyncio
async def test_business_free_question_prompt(mock_db):
    """Selecting 5 (My Question) shows a prompt asking for the question."""
    r = await ussd("1*5", mock_db)
    assert is_con(r)
    assert "question" in r.lower()


@pytest.mark.asyncio
async def test_business_free_question_answered(mock_db, mock_ai):
    """After typing a question, AI is called and session ends."""
    r = await ussd("1*5*How do I price my shirts?", mock_db)
    assert is_end(r)
    mock_ai.assert_awaited_once()
    call_args = mock_ai.call_args
    assert "How do I price my shirts?" in call_args.kwargs.get("question", "")
    assert call_args.kwargs.get("category") == "business"


# ── Farming submenu ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_farming_submenu_shown(mock_db):
    r = await ussd("2", mock_db)
    assert is_con(r)
    assert "Farming" in r
    assert "1.Soil" in r


@pytest.mark.asyncio
async def test_farming_predefined_topic(mock_db, mock_ai):
    r = await ussd("2*3", mock_db)  # Best crops
    assert is_con(r), f"Expected CON, got: {r[:80]}"
    mock_ai.assert_awaited_once()
    assert call_category(mock_ai) == "farming"
    assert "1.More tips" in r


# ── Health submenu ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_submenu_shown(mock_db):
    r = await ussd("3", mock_db)
    assert is_con(r)
    assert "Health" in r


@pytest.mark.asyncio
async def test_health_free_question(mock_db, mock_ai):
    r = await ussd("3*5*What food helps with anemia?", mock_db)
    assert is_end(r)
    assert call_category(mock_ai) == "health"


# ── Education submenu ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_education_submenu_shown(mock_db):
    r = await ussd("4", mock_db)
    assert is_con(r)
    assert "Education" in r


# ── Ask AI direct (option 5 from main) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_ask_ai_prompt(mock_db):
    r = await ussd("5", mock_db)
    assert is_con(r)
    assert "question" in r.lower()


@pytest.mark.asyncio
async def test_ask_ai_answered(mock_db, mock_ai):
    r = await ussd("5*What is inflation?", mock_db)
    assert is_end(r)
    mock_ai.assert_awaited_once()
    assert call_category(mock_ai) == "general"
    assert "What is inflation?" in mock_ai.call_args.kwargs.get("question", "")


# ── Account menu ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_account_menu_shown(mock_db):
    r = await ussd("6", mock_db)
    assert is_con(r)
    assert "Account" in r
    assert "1.My stats" in r


@pytest.mark.asyncio
async def test_account_stats(mock_db):
    """Stats screen must show 'Queries:' and end the session."""
    from unittest.mock import MagicMock
    from datetime import datetime, timezone

    user_mock = MagicMock()
    user_mock.name = "Alice"
    user_mock.profession = "farmer"
    user_mock.language = "en"
    user_mock.sms_opt_out = False
    user_mock.daily_tips_enabled = False
    user_mock.daily_tip_category = None
    user_mock.total_queries = 7
    user_mock.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=user_mock)
    mock_db.execute = AsyncMock(return_value=result_mock)

    r = await ussd("6*1", mock_db)
    assert is_end(r)
    assert "Queries: 7" in r
    assert "Alice" in r


@pytest.mark.asyncio
async def test_account_set_name_prompt(mock_db):
    r = await ussd("6*2", mock_db)
    assert is_con(r)
    assert "name" in r.lower()


@pytest.mark.asyncio
async def test_account_set_name_saves(mock_db):
    r = await ussd("6*2*John Manzi", mock_db)
    assert is_end(r)
    assert "John Manzi" in r


@pytest.mark.asyncio
async def test_account_set_profession_menu(mock_db):
    r = await ussd("6*3", mock_db)
    assert is_con(r)
    assert "1.Farmer" in r


@pytest.mark.asyncio
async def test_account_set_profession_farmer(mock_db):
    r = await ussd("6*3*1", mock_db)
    assert is_end(r)
    assert "farmer" in r.lower()


# ── Rate limiting ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_blocks(mock_db, mock_redis):
    """When rate limit is exceeded, user gets a friendly error."""
    # 51st increment exceeds the 50/hour limit
    mock_redis.incr = AsyncMock(return_value=51)

    r = await ussd("5*Tell me about farming", mock_db)
    assert is_end(r)
    assert "limit" in r.lower()


# ── New high-impact features ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_menu_has_emergency_option(mock_db):
    """Health submenu must include option 7 for emergency numbers."""
    r = await ussd("3", mock_db)
    assert is_con(r)
    assert "7.Emergency" in r


@pytest.mark.asyncio
async def test_health_emergency_shows_numbers(mock_db):
    """Option 7 in health menu returns static emergency numbers."""
    r = await ussd("3*7", mock_db)
    assert is_end(r)
    assert "555" in r


@pytest.mark.asyncio
async def test_farming_market_prices_shows_district_menu(mock_db):
    """Farming option 4 (Market prices) must show district selection, not AI."""
    r = await ussd("2*4", mock_db)
    assert is_con(r)
    assert "district" in r.lower() or "Kigali" in r


@pytest.mark.asyncio
async def test_tip_has_send_sms_option(mock_db, mock_ai):
    """After a predefined tip, option 3 must be 'Send SMS'."""
    r = await ussd("1*1", mock_db)
    assert is_con(r)
    assert "3.Send SMS" in r


@pytest.mark.asyncio
async def test_tip_has_feedback_options(mock_db, mock_ai):
    """After a predefined tip, helpful/not helpful options must be present."""
    r = await ussd("2*1", mock_db)
    assert is_con(r)
    assert "4.Helpful" in r
    assert "5.Not helpful" in r


@pytest.mark.asyncio
async def test_feedback_helpful_returns_thanks(mock_db, mock_ai):
    """Pressing 4 (Helpful) after a tip should return a thank-you END response."""
    r = await ussd("1*1*4", mock_db)
    assert is_end(r)
    assert "thanks" in r.lower() or "urakoze" in r.lower()


@pytest.mark.asyncio
async def test_feedback_not_helpful_returns_thanks(mock_db, mock_ai):
    """Pressing 5 (Not helpful) should also return a thank-you END response."""
    r = await ussd("1*2*5", mock_db)
    assert is_end(r)
    assert "thanks" in r.lower() or "urakoze" in r.lower()


@pytest.mark.asyncio
async def test_pagination_splits_long_response(mock_db):
    """A free-form AI response where SMS fails should trigger CON pagination."""
    from unittest.mock import patch
    from app.services.ai_service import AIResult

    long_text = ("A word " * 50).strip()  # ~350 chars, well over _PAGE_SIZE=160
    with patch(
        "app.services.menu_service.ai_service.get_ai_response",
        new_callable=AsyncMock,
        return_value=AIResult(text=long_text, tokens_used=80, from_cache=False),
    ), patch(
        "app.services.menu_service.sms_service.send_sms",
        new_callable=AsyncMock,
        return_value=False,  # SMS fails → fallback to pagination
    ):
        r = await ussd("5*What is a long answer?", mock_db)
    assert is_con(r), f"Expected CON for paginated response, got: {r[:80]}"
    assert "1.Next" in r
    assert "0.Stop" in r


# ── Helpers ───────────────────────────────────────────────────────────────────

from unittest.mock import AsyncMock  # noqa: E402 — needed by fixtures above


def call_category(mock_ai) -> str:
    """Return the `category` kwarg from the last AI call."""
    return mock_ai.call_args.kwargs.get("category", "")
