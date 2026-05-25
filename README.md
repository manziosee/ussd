# SmartAssist USSD

> **AI for everyone — including the 600 million Africans with no internet.**

SmartAssist is an AI-powered USSD assistant that lets any mobile phone user
(feature phone or smartphone, with or without internet) access a Claude-powered
AI by simply dialling a shortcode like `*123#`.

---

## Technology Stack

| | Technology | Role |
|---|---|---|
| ![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=flat&logo=python&logoColor=white) | **Python 3.12** | Core language |
| ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white) | **FastAPI** | Async API framework |
| ![Anthropic](https://img.shields.io/badge/Claude_Haiku-D4A017?style=flat&logoColor=white) | **Claude Haiku** | AI responses (Anthropic) |
| ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white) | **PostgreSQL (Neon)** | Cloud-hosted serverless DB |
| ![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white) | **Redis / fakeredis** | Sessions, AI cache, rate limits |
| ![Africa's Talking](https://img.shields.io/badge/Africa's_Talking-00A859?style=flat&logoColor=white) | **Africa's Talking** | USSD gateway + SMS delivery |
| ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white) | **Docker Compose** | Optional local DB + Redis |
| ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy_2.0-D71F00?style=flat&logoColor=white) | **SQLAlchemy 2.0** | Async ORM |
| ![Alembic](https://img.shields.io/badge/Alembic-grey?style=flat) | **Alembic** | Database migrations |
| ![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=flat&logo=pytest&logoColor=white) | **pytest-asyncio** | Async test suite |

---

## What the System Does

Any mobile phone dials `*123#`. No internet. No smartphone. No app download.
The user navigates a simple text menu powered by Claude AI.

```
Any mobile phone dials *123#
          │
          │  No internet required — works on any feature phone
          ▼
┌─────────────────────────────────┐
│    Africa's Talking Gateway     │
│      (USSD network layer)       │
└────────────────┬────────────────┘
                 │  POST /ussd  (form-encoded)
                 │  sessionId · phoneNumber · text
                 ▼
┌────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                           │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                  USSD State Machine                      │ │
│  │  Parses accumulated text  e.g. "1*2" = Business → Tip 2 │ │
│  │  Routes to correct handler based on input depth          │ │
│  └────────────────────────┬─────────────────────────────────┘ │
│           ┌───────────────┼────────────────┐                  │
│           ▼               ▼                ▼                  │
│  ┌──────────────┐ ┌───────────────┐ ┌───────────────┐        │
│  │    Redis     │ │ Claude Haiku  │ │  PostgreSQL   │        │
│  │  (fakeredis  │ │  (Anthropic)  │ │   on Neon     │        │
│  │   in dev)    │ │               │ │               │        │
│  │ · Sessions   │ │ · Business    │ │ · Users       │        │
│  │ · AI cache   │ │ · Farming     │ │ · Interaction │        │
│  │ · Rate limit │ │ · Health      │ │   history     │        │
│  │ · Knowledge  │ │ · Education   │ │ · Analytics   │        │
│  │   seed cache │ │ · General     │ │               │        │
│  └──────────────┘ └───────────────┘ └───────────────┘        │
└───────────────────────────┬────────────────────────────────────┘
                            │  "CON …" (continue) / "END …" (end)
                            ▼
                   Africa's Talking
                   delivers to phone ──→ SMS fallback (long answers)
                            │
                            ▼
                     User's Phone
                  ┌─────────────────┐
                  │ SmartAssist AI  │
                  │ 1.Business      │
                  │ 2.Farming       │
                  │ 3.Health        │
                  │ 4.Education     │
                  │ 5.Ask AI        │
                  │ 6.Account       │
                  └─────────────────┘
```

---

## Request Flow

```
 User Input              System                          External
 ──────────              ──────                          ────────

 Dials *123#
      │
      │── POST /ussd ──────────────▶ FastAPI
                                         │
                                         ├─ user_exists in Redis?
                                         │    Yes → skip DB lookup
                                         │    No  → INSERT user row
                                         │
                                         ├─ Rate limit check
                                         │    Redis INCR per phone/hour
                                         │    Blocked at 50 req/hr
                                         │
                                         ├─ Parse "text" input
                                         │    ""      → main menu (CON)
                                         │    "1"     → business menu (CON)
                                         │    "1*2"   → bookkeeping tip
                                         │    "1*5*Q" → free AI question
                                         │
                                         ├─ Check Redis AI cache
                                         │    HIT  → return cached (free)
                                         │    MISS → Claude Haiku API
                                         │            system prompt cached
                                         │            response saved to Redis
                                         │
                                         ├─ Response > 155 chars?
                                         │    Yes → SMS via Africa's Talking
                                         │          show truncated on USSD
                                         │
                                         └─ Log to PostgreSQL (background)

 CON / END ◀──────────── Plain text ─────┘
 shown on phone
```

---

## Menu Structure

```
*123#
└── SmartAssist AI
    ├── 1. Business
    │   ├── 1. Pricing tips      →  AI (knowledge cache first)
    │   ├── 2. Bookkeeping       →  AI (knowledge cache first)
    │   ├── 3. Marketing         →  AI (knowledge cache first)
    │   ├── 4. Get customers     →  AI (knowledge cache first)
    │   ├── 5. My question       →  CON: "Your question:" → AI answer
    │   └── 0. Main menu
    │
    ├── 2. Farming   (Soil · Pest control · Best crops · Market prices · My question)
    ├── 3. Health    (Nutrition · Hygiene · Maternal health · Child health · My question)
    ├── 4. Education (Study tips · Career guide · Math help · English tips · My question)
    │
    ├── 5. Ask AI
    │   └── CON: "Ask AI anything:" → free question → AI answer
    │
    └── 6. Account
        ├── 1. My stats       →  query count · name · role · member since
        ├── 2. Set my name    →  CON: "Enter your name:" → saved to DB
        ├── 3. Set profession →  Farmer / Student / Business / Other
        └── 0. Main menu
```

---

## Features

### ✅ Phase 1 — MVP (complete)

| Feature | Detail |
|---|---|
| **USSD menu navigation** | 5 categories + account, unlimited depth via state machine |
| **AI responses** | Claude Haiku — Africa-focused, under 155 chars |
| **Anthropic prompt caching** | System prompts cached server-side → ~90% token savings |
| **Redis response cache** | Same answer cached 24 h → zero API cost on repeat questions |
| **Offline knowledge seed** | 16 pre-written responses loaded at startup → zero latency & zero cost for all pre-defined topics |
| **SMS fallback** | Long answers auto-sent via Africa's Talking SMS |
| **User profiles** | Name + profession stored; AI personalises tips based on profession |
| **Rate limiting** | 50 queries / phone / hour via Redis counter |
| **Session management** | Redis-backed, 5-min TTL (USSD standard) |
| **fakeredis fallback** | Server runs without Redis in dev (auto-detected, in-memory) |
| **Neon PostgreSQL** | Serverless cloud DB, SSL auto-configured |
| **Interaction logging** | Every query logged to PostgreSQL for analytics |
| **Admin API** | Stats, user list, interaction history |
| **CLI simulator** | Full USSD session testing locally — no Africa's Talking needed |
| **Alembic migrations** | Async-compatible schema versioning |
| **Test suite** | 23 async tests, fully mocked (no external services required) |

### 🔜 Phase 2 — Planned

| Feature | Detail |
|---|---|
| Kinyarwanda support | Full menus + AI responses in Kinyarwanda |
| Swahili + French | Additional language options |
| Admin dashboard | React/Next.js analytics panel |
| Daily tip broadcast | Scheduled SMS to opted-in users |
| Voice / IVR | Speech-to-text over phone calls |
| Market prices | Live crop prices from agricultural APIs |

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/manziosee/ussd.git
cd ussd
cp .env.example .env
```

Edit `.env`:

```env
# AI (required for free-form questions)
ANTHROPIC_API_KEY=sk-ant-...

# Africa's Talking
AT_USERNAME=sandbox
AT_API_KEY=your_sandbox_key
AT_SHORTCODE=12345
AT_ENVIRONMENT=sandbox

# Database — Neon (recommended) or local PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
```

### 2. Install and run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

> **No Redis? No problem.** The server auto-detects when Redis is unavailable
> and falls back to an in-memory `fakeredis` store — perfect for development.

> **Database options:**
> - **Neon** (recommended) — free serverless PostgreSQL at [neon.tech](https://neon.tech). SSL is configured automatically.
> - **Docker** — run `docker compose up db redis -d` for local PostgreSQL + Redis.

### 3. Test with the CLI simulator

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

### 4. Run tests

```bash
pytest
```

All 23 tests pass with no external services required (Redis, DB, and AI are all mocked).

---

## Africa's Talking Setup

### Sandbox (development)

1. Sign up at [africastalking.com](https://africastalking.com)
2. Go to **Sandbox → USSD → Create channel** (e.g. `*384*72275#`)
3. Set the callback URL to your server: `https://your-server.com/ussd`
4. Test using AT's built-in simulator

### Expose localhost with ngrok

```bash
ngrok http 8000
# Paste the HTTPS URL into your AT USSD channel callback
```

### Go to production

```env
AT_ENVIRONMENT=production
AT_USERNAME=your_live_username
AT_API_KEY=your_live_key
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/ussd` | Africa's Talking USSD webhook (form-encoded) |
| `POST` | `/simulate` | Local simulator — JSON body |
| `GET` | `/admin/stats` | Aggregated analytics |
| `GET` | `/admin/users` | User list (paginated) |
| `GET` | `/admin/interactions` | Interaction history (paginated, filterable by category) |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

### Example — `/simulate`

```bash
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+250788000001", "text": "2*3", "session_id": "s1"}'
```

```
END Plant beans alongside maize — beans add nitrogen to soil and sell
year-round. Kale and spinach grow in 30 days and have steady local demand.
```

### Example — `/admin/stats`

```json
{
  "total_users": 1,
  "total_interactions": 4,
  "total_tokens_used": 0,
  "cache_hit_rate": 1.0,
  "sms_sent": 0,
  "interactions_by_category": {
    "business": 1,
    "farming": 1,
    "health": 1,
    "education": 1
  }
}
```

> `total_tokens_used: 0` and `cache_hit_rate: 1.0` — all responses served from
> the offline knowledge seed cache. Zero AI API cost.

---

## Cost Model

| Scenario | API Cost |
|---|---|
| Pre-defined topic (1–4 in any category) | **$0** — knowledge seed cache |
| Same free question asked again within 24 h | **$0** — Redis response cache |
| New free-form question | **< $0.0005** — Claude Haiku + prompt cache |
| **Blended average** | **< $0.0001 per interaction** |

---

## Project Structure

```
ussd/
├── app/
│   ├── main.py                  # FastAPI app, lifespan, startup validation
│   ├── config.py                # All settings via pydantic-settings + .env
│   ├── database.py              # Async SQLAlchemy, Neon SSL auto-config
│   ├── models/
│   │   ├── user.py              # User profile (phone, name, profession, language)
│   │   └── interaction.py       # AI query log (tokens, cache hit, SMS sent)
│   ├── services/
│   │   ├── menu_service.py      # ★ USSD state machine — core routing logic
│   │   ├── ai_service.py        # Claude Haiku + Anthropic prompt caching
│   │   ├── session_service.py   # Redis: sessions · AI cache · rate limit · fakeredis fallback
│   │   ├── knowledge_service.py # 16 pre-seeded offline responses (zero API cost)
│   │   └── sms_service.py       # Africa's Talking SMS for long responses
│   ├── routes/
│   │   ├── ussd.py              # POST /ussd + POST /simulate
│   │   └── admin.py             # GET /admin/stats|users|interactions
│   └── schemas/
│       └── ussd.py              # Pydantic schemas
├── simulator/
│   └── cli_sim.py               # Terminal USSD simulator (no AT account needed)
├── tests/
│   ├── conftest.py              # Fixtures: mock Redis, DB, AI
│   └── test_ussd_menu.py        # 23 async tests — all menu paths + edge cases
├── alembic/
│   └── env.py                   # Async-compatible Alembic environment
├── docker-compose.yml           # PostgreSQL 16 + Redis 7 (optional, for local dev)
├── Dockerfile                   # Production container
├── requirements.txt
├── alembic.ini
├── pytest.ini
└── .env.example
```

---

## Live Test Results

Tested against **Neon PostgreSQL** + **fakeredis** (no Docker required):

| Test case | Input | Response |
|---|---|---|
| Fresh dial | `""` | `CON SmartAssist AI…` |
| Business menu | `"1"` | `CON Business Advisor…` |
| Pricing tip | `"1*1"` | `END Add total cost + 30% profit…` |
| Farming — best crops | `"2*3"` | `END Plant beans alongside maize…` |
| Health — hygiene | `"3*2"` | `END Wash hands with soap…` |
| Education — study | `"4*1"` | `END Study 25 min, rest 5 min…` |
| Set profession: farmer | `"6*3*1"` | `END Role saved: farmer…` |
| Ask AI prompt | `"5"` | `CON Ask AI anything:…` |
| Free question prompt | `"1*5"` | `CON Your Business question:` |

All pre-defined tips served from **knowledge cache — 0 tokens used, $0 cost**.

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/kinyarwanda`
3. Add changes + tests — `pytest` must pass
4. Open a PR

---

## License

MIT — free to use, modify, and deploy.

---

*Built for African communities — making AI accessible to everyone, everywhere.*
