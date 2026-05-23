# SmartAssist USSD

> **AI for everyone — including the 600 million Africans with no internet.**

SmartAssist is an AI-powered USSD assistant that lets any mobile phone user
(feature phone or smartphone, with or without internet) access a Claude-powered
AI by simply dialling a shortcode like `*123#`.

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| ![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white) **Python 3.12** | Core language | |
| ![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white) **FastAPI** | Async API framework | USSD webhook + Admin API |
| ![Anthropic](https://img.shields.io/badge/Claude-AI-D4A017?logo=anthropic&logoColor=white) **Claude Haiku** | LLM (Anthropic) | AI responses — cheapest + fastest |
| ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white) **PostgreSQL 16** | Relational DB | Users, interaction history |
| ![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white) **Redis 7** | In-memory cache | Sessions, AI cache, rate limits |
| ![Africa's Talking](https://img.shields.io/badge/Africa's%20Talking-00A859?logoColor=white) **Africa's Talking** | Telecom API | USSD gateway + SMS delivery |
| ![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white) **Docker Compose** | Container orchestration | DB + Redis |
| ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?logo=sqlalchemy&logoColor=white) **SQLAlchemy 2.0** | ORM (async) | Database layer |
| ![Alembic](https://img.shields.io/badge/Alembic-grey) **Alembic** | DB migrations | Schema versioning |
| ![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white) **pytest-asyncio** | Test framework | Async test suite |

---

## What the System Does

```
Any mobile phone dials *123#
          │
          │  (no internet required — works on feature phones)
          ▼
┌─────────────────────────────────┐
│    Africa's Talking Gateway     │
│    (USSD network operator)      │
└────────────────┬────────────────┘
                 │  POST /ussd
                 │  form-encoded payload:
                 │  sessionId, phoneNumber, text
                 ▼
┌────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                            │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              USSD State Machine                          │ │
│  │  Parses accumulated text (e.g. "1*2" = Business→Tip 2)  │ │
│  │  Routes to correct handler based on menu depth           │ │
│  └────────────────────────┬─────────────────────────────────┘ │
│           ┌───────────────┼───────────────┐                   │
│           ▼               ▼               ▼                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
│  │    Redis     │ │    Claude    │ │  PostgreSQL  │          │
│  │              │ │    Haiku     │ │              │          │
│  │ • Sessions   │ │              │ │ • Users      │          │
│  │ • AI cache   │ │ • Business   │ │ • Interaction│          │
│  │ • Rate limit │ │ • Farming    │ │   history    │          │
│  │ • User flag  │ │ • Health     │ │ • Analytics  │          │
│  │ • Knowledge  │ │ • Education  │ │              │          │
│  │   seed cache │ │ • General    │ │              │          │
│  └──────────────┘ └──────────────┘ └──────────────┘          │
└────────────────────────────┬───────────────────────────────────┘
                             │  CON <text>  (continue)
                             │  END <text>  (end session)
                             ▼
                    ┌────────────────┐
                    │ Africa's       │
                    │ Talking        │──→ SMS fallback (long answers)
                    │ (delivers to   │
                    │  user's phone) │
                    └────────────────┘
                             │
                             ▼
                      User's Phone
                    ┌────────────────┐
                    │ SmartAssist AI │
                    │ 1.Business     │
                    │ 2.Farming      │
                    │ 3.Health       │
                    │ 4.Education    │
                    │ 5.Ask AI       │
                    │ 6.Account      │
                    └────────────────┘
```

---

## Request Flow (detailed)

```
 User Input                 System                         External
 ──────────                 ──────                         ────────

 Dials *123#
        │
        │──── POST /ussd ──────────────▶ FastAPI
                                              │
                                              ├─ Check Redis: user exists?
                                              │    (avoids DB hit every request)
                                              │
                                              ├─ Parse "text" input
                                              │    ""     → main menu
                                              │    "1"    → business menu
                                              │    "1*2"  → business bookkeeping
                                              │    "1*5*Q"→ free AI question
                                              │
                                              ├─ Rate limit check
                                              │    Redis INCR ussd:rate:{phone}:{hour}
                                              │    Max 50 req/hour per phone
                                              │
                         ┌────────────────────┤
                         │  Pre-defined topic │
                         │  OR free question  │
                         └────────────────────┤
                                              │
                                              ├─ Check Redis AI cache
                                              │    Hit  → return cached (0 tokens)
                                              │    Miss → call Claude Haiku
                                              │              ↓
                                              │         Anthropic API
                                              │         (system prompt cached)
                                              │              ↓
                                              │         Response stored in Redis
                                              │         (AI_CACHE_TTL = 24 h)
                                              │
                                              ├─ Response > 155 chars?
                                              │    Yes → send full answer via SMS
                                              │          show truncated on USSD
                                              │    No  → show full on USSD
                                              │
                                              ├─ Log interaction to PostgreSQL
                                              │    (background task, own session)
                                              │
 CON / END text ◀──────── Plain text ─────────┘
 displayed on phone
```

---

## Menu Structure

```
*123#
└── SmartAssist AI
    ├── 1. Business
    │   ├── 1. Pricing tips          ──▶ AI: How to price products in Africa
    │   ├── 2. Bookkeeping           ──▶ AI: Simple bookkeeping for small business
    │   ├── 3. Marketing             ──▶ AI: Low-cost marketing ideas
    │   ├── 4. Get customers         ──▶ AI: Attract and retain customers
    │   ├── 5. My question           ──▶ CON: "Your business question:" → AI answer
    │   └── 0. Main menu
    │
    ├── 2. Farming
    │   ├── 1. Soil tips             ──▶ AI (or knowledge cache)
    │   ├── 2. Pest control          ──▶ AI (or knowledge cache)
    │   ├── 3. Best crops            ──▶ AI (or knowledge cache)
    │   ├── 4. Market prices         ──▶ AI (or knowledge cache)
    │   ├── 5. My question           ──▶ CON: free question → AI answer
    │   └── 0. Main menu
    │
    ├── 3. Health (same pattern — nutrition, hygiene, maternal, child)
    ├── 4. Education (same pattern — study, career, maths, English)
    │
    ├── 5. Ask AI
    │   └── CON: "Ask AI anything:" → free question → AI answer (general)
    │
    └── 6. Account
        ├── 1. My stats              ──▶ END: total queries, name, role, member since
        ├── 2. Set my name           ──▶ CON: "Enter your name:" → saves to DB
        ├── 3. Set profession        ──▶ CON: Farmer / Student / Business / Other
        └── 0. Main menu
```

---

## Feature Overview

### ✅ Phase 1 — MVP (built)

| Feature | Detail |
|---|---|
| USSD menu navigation | 5 categories + account, unlimited depth |
| AI responses | Claude Haiku — Africa-focused, < 155 chars |
| Prompt caching | Anthropic caches system prompts → ~90% token savings |
| Response caching | Redis caches AI answers for 24 h → zero API cost on repeat |
| Offline knowledge seed | 16 pre-written responses seeded at startup → zero first-call latency |
| SMS fallback | Long answers auto-delivered via SMS + truncated on USSD |
| User profiles | Name + profession stored; profession personalises AI prompts |
| Rate limiting | 50 queries/phone/hour via Redis counter |
| Session management | Redis-backed, 5-min TTL (USSD standard timeout) |
| Interaction logging | Every AI query logged to PostgreSQL for analytics |
| Admin API | Stats, user list, interaction history with pagination |
| CLI simulator | Test full USSD sessions locally without Africa's Talking |
| Docker Compose | PostgreSQL + Redis launched with one command |
| Alembic migrations | Schema versioning for production DB management |
| Test suite | 20+ async tests covering all menu paths and edge cases |

### 🔜 Phase 2 — Planned

| Feature | Detail |
|---|---|
| Kinyarwanda | Full menu + AI responses in Kinyarwanda |
| Swahili + French | Additional language options |
| Admin dashboard | React/Next.js analytics panel |
| Daily tip broadcast | Scheduled SMS to opted-in users |
| Voice / IVR | Speech-to-text over phone calls |
| Market data | Live crop prices from agricultural APIs |
| Expanded knowledge | 100+ pre-seeded answers, zero AI cost for FAQs |

---

## Quick Start

### 1. Clone and configure

```bash
git clone <your-repo>
cd ussd
cp .env.example .env
```

Edit `.env` and fill in your keys:

```env
ANTHROPIC_API_KEY=sk-ant-...       # get from console.anthropic.com
AT_USERNAME=your_at_username       # Africa's Talking username
AT_API_KEY=your_at_api_key         # Africa's Talking API key
AT_SHORTCODE=SMARTASSIST           # your registered shortcode
AT_ENVIRONMENT=sandbox             # "sandbox" or "production"
```

### 2. Start infrastructure

```bash
docker compose up db redis -d
```

Or run the full stack including the app:

```bash
docker compose up --build
```

### 3. Install dependencies and run

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Server is live at **http://localhost:8000**
Swagger docs at **http://localhost:8000/docs**

### 4. Test with the CLI simulator

```bash
python simulator/cli_sim.py
```

```
══════════════════════════════════════════════════
   SmartAssist USSD Simulator
══════════════════════════════════════════════════
  Phone : +250788123456
  Server: http://localhost:8000

┌──────────────────────────────────────┐
│  SmartAssist AI                      │
│  1.Business                          │
│  2.Farming                           │
│  3.Health                            │
│  4.Education                         │
│  5.Ask AI                            │
│  6.Account                           │
└──────────────────────────────────────┘
  Your input: _
```

### 5. Run tests

```bash
pytest
```

---

## Africa's Talking Setup

### Sandbox (development)

1. Sign up at [africastalking.com](https://africastalking.com)
2. Go to **Sandbox → USSD → Create channel** (e.g. `*384*72275#`)
3. Set callback URL: `https://your-server.com/ussd`
4. Use AT's built-in simulator to send test dials

### Expose localhost with ngrok

```bash
ngrok http 8000
# Paste the HTTPS URL into your AT USSD channel callback
```

### Production

```env
AT_ENVIRONMENT=production
AT_USERNAME=your_live_username
AT_API_KEY=your_live_key
AT_SHORTCODE=your_registered_shortcode
```

---

## API Reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/ussd` | Africa's Talking | USSD webhook (form-encoded) |
| `POST` | `/simulate` | None | Local simulator (JSON) |
| `GET`  | `/admin/stats` | None* | Aggregated analytics |
| `GET`  | `/admin/users` | None* | User list (paginated) |
| `GET`  | `/admin/interactions` | None* | Interaction log (paginated) |
| `GET`  | `/health` | None | Health check |
| `GET`  | `/docs` | None | Swagger UI |

> *Add Bearer token middleware before deploying to production.

### `POST /simulate` — example

```bash
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+250788000001", "text": "1*1", "session_id": "abc123"}'
```

Response:
```
END Add your cost + 30% profit minimum. Test price on 5 customers. If all buy instantly, raise price 10%. Track weekly.
```

### `GET /admin/stats` — example

```json
{
  "total_users": 142,
  "total_interactions": 1893,
  "total_tokens_used": 47250,
  "cache_hit_rate": 0.74,
  "sms_sent": 38,
  "interactions_by_category": {
    "business": 612,
    "farming": 504,
    "health": 311,
    "education": 287,
    "general": 179
  }
}
```

---

## Project Structure

```
ussd/
├── app/
│   ├── main.py                 # FastAPI app, lifespan, startup validation
│   ├── config.py               # All settings via pydantic-settings + .env
│   ├── database.py             # Async SQLAlchemy engine + session factory
│   │
│   ├── models/
│   │   ├── user.py             # User profile (phone, name, profession, language)
│   │   └── interaction.py      # AI query log (category, question, response, tokens)
│   │
│   ├── services/
│   │   ├── menu_service.py     # ★ USSD state machine — core routing logic
│   │   ├── ai_service.py       # Claude Haiku integration with prompt caching
│   │   ├── session_service.py  # Redis: sessions, AI cache, rate limit, user flag
│   │   ├── knowledge_service.py# 16 pre-seeded offline responses (zero API cost)
│   │   └── sms_service.py      # Africa's Talking SMS for long responses
│   │
│   ├── routes/
│   │   ├── ussd.py             # POST /ussd (AT webhook) + POST /simulate
│   │   └── admin.py            # GET /admin/stats|users|interactions
│   │
│   └── schemas/
│       └── ussd.py             # Pydantic request/response models
│
├── simulator/
│   └── cli_sim.py              # Terminal USSD simulator (no AT needed)
│
├── tests/
│   ├── conftest.py             # Fixtures: mock Redis, DB, AI
│   └── test_ussd_menu.py       # 20+ async tests — all menu paths
│
├── alembic/
│   └── env.py                  # Async-compatible Alembic environment
│
├── docker-compose.yml          # PostgreSQL 16 + Redis 7
├── Dockerfile                  # Production container
├── requirements.txt            # All Python dependencies
├── alembic.ini                 # Alembic config
├── pytest.ini                  # Test config
└── .env.example                # All required environment variables
```

---

## Cost Model

With all caching layers active:

| Scenario | Cost |
|---|---|
| Pre-defined topic, first user | **$0** (knowledge seed cache) |
| Pre-defined topic, 2nd+ user | **$0** (Redis 24 h cache) |
| Free question, first time asked | **< $0.0005** (Claude Haiku + prompt cache) |
| Free question, asked again within 24 h | **$0** (Redis cache) |
| Expected blended cost | **< $0.0001 per interaction** |

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/kinyarwanda-support`
3. Make changes and add tests
4. Run `pytest` — all tests must pass
5. Open a PR describing what you built

---

## License

MIT License — free to use, modify, and deploy.

---

*Built with ❤️ for African communities — making AI accessible to everyone, everywhere.*
