# SmartAssist USSD

> **AI for everyone — including the 600 million Africans with no internet.**

SmartAssist is an AI-powered USSD assistant that lets any mobile phone user
(feature phone or smartphone, no internet required) access AI by simply dialling
a shortcode like `*123#`.  Responses are instant and cost the user nothing extra
beyond their normal USSD session.

---

## Technology Stack

| | Technology | Role |
|---|---|---|
| ![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=flat&logo=python&logoColor=white) | **Python 3.12** | Core language |
| ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white) | **FastAPI** | Async API framework (USSD app + SMS gateway) |
| ![Groq](https://img.shields.io/badge/Groq_Llama-FF6B35?style=flat&logoColor=white) | **Groq — Llama 3.1 8B** | Ultra-fast AI responses via Groq inference |
| ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white) | **PostgreSQL (Neon)** | Cloud-hosted serverless DB |
| ![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white) | **Redis** | Sessions, AI cache, rate limits |
| ![Jasmin](https://img.shields.io/badge/Jasmin_SMPP-2C3E50?style=flat&logoColor=white) | **Jasmin SMS Gateway** | Open-source SMPP gateway — own SMS infrastructure |
| ![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=flat&logo=rabbitmq&logoColor=white) | **RabbitMQ** | Jasmin message queue (AMQP) |
| ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white) | **Docker Compose** | Full-stack local deployment |
| ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy_2.0-D71F00?style=flat&logoColor=white) | **SQLAlchemy 2.0** | Async ORM |
| ![Alembic](https://img.shields.io/badge/Alembic-grey?style=flat) | **Alembic** | Database migrations |
| ![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=flat&logo=pytest&logoColor=white) | **pytest-asyncio** | 45-test async suite |

---

## System Architecture

```
Any mobile phone dials *123#  (no internet — works on any feature phone)
          │
          ▼
┌─────────────────────────────────┐
│       USSD Aggregator           │
│  (Africa's Talking or any       │
│   USSD network partner)         │
└────────────────┬────────────────┘
                 │  POST /ussd  (form-encoded)
                 │  sessionId · phoneNumber · text
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                 SmartAssist USSD App  (port 8000)               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                  USSD State Machine                        │ │
│  │  Parses accumulated text  e.g. "1*2" = Business → Tip 2  │ │
│  └──────────────────────┬─────────────────────────────────────┘ │
│           ┌─────────────┼────────────┐                          │
│           ▼             ▼            ▼                          │
│  ┌──────────────┐ ┌──────────┐ ┌───────────────┐              │
│  │    Redis     │ │  Groq    │ │  PostgreSQL   │              │
│  │  Sessions    │ │  Llama   │ │   (Neon)      │              │
│  │  AI cache    │ │  3.1 8B  │ │  Users        │              │
│  │  Rate limit  │ │  ~50ms   │ │  Interactions │              │
│  └──────────────┘ └──────────┘ └───────────────┘              │
│                                                                  │
│  Long answer → POST /sms/send                                   │
└───────────────────────┬──────────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────────┐
│              SMS Gateway API  (port 8001)                         │
│                                                                    │
│  • Validates E.164 phone number                                    │
│  • Detects country code (+250 → Rwanda, +254 → Kenya …)           │
│  • Routes to correct Jasmin connector (mtn_rw, safaricom_ke …)    │
│  • Auto-detects GSM7 vs UCS-2 encoding (Kinyarwanda support)      │
└───────────────────────┬───────────────────────────────────────────┘
                        │  POST /send  (form-encoded)
                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                  Jasmin SMPP Gateway  (port 1401/2775)            │
│                                                                    │
│  Configured SMPP connectors:                                       │
│    mtn_rw       →  MTN Rwanda      (SMPP)                         │
│    airtel_rw    →  Airtel Rwanda   (SMPP)                         │
│    safaricom_ke →  Safaricom Kenya (SMPP)                         │
│    mtn_ug       →  MTN Uganda      (SMPP)                         │
│    …add more via  telnet localhost 8990  (Jasmin CLI)             │
└───────────────────────┬───────────────────────────────────────────┘
                        │  SMPP v3.4
                        ▼
              Telecom Operator Network
                        │
                        ▼
                  User's Phone 📱
```

---

## Why Jasmin Instead of Twilio / Africa's Talking SMS?

| | Twilio / AT SMS | Jasmin SMPP |
|---|---|---|
| **Cost per SMS** | $0.0075–$0.02 | ~$0 (direct telecom rate) |
| **Infrastructure** | Third-party cloud | Your own server |
| **Latency** | 1–5 s (cloud relay) | < 500 ms (direct SMPP) |
| **Multi-country** | Per-provider setup | One gateway, all operators |
| **Data sovereignty** | Vendor's servers | Your servers |
| **Scaling** | Per-message billing | Fixed infra cost |

At 10 000 SMS/month, Jasmin pays for itself in the first month.

---

## Menu Structure

```
Dial *123# → Onboarding (new users: language + role) → Main Menu
└── SmartAssist AI
    ├── 1. Business
    │   ├── 1–4. Pricing / Bookkeeping / Marketing / Get customers  (AI tip → CON)
    │   │         └── 1.More tips · 2.More detail · 3.Send SMS · 4.Helpful · 5.Not helpful · 0.Back
    │   ├── 5. My question  (free AI question, paginated if long)
    │   └── 6. Calculator   (profit check · loan payment — zero AI cost)
    │
    ├── 2. Farming
    │   ├── 1–3. Soil / Pest control / Best crops  (AI tip)
    │   ├── 4. Market prices  (DB-backed — 5 Rwanda districts × 6 crops)
    │   ├── 5. My question
    │   └── 6. Nearby agri offices  (static directory)
    │
    ├── 3. Health
    │   ├── 1–4. Nutrition / Hygiene / Maternal / Child  (AI tip)
    │   ├── 5. My question
    │   ├── 6. Nearby clinics  (static directory)
    │   └── 7. Emergency numbers  (police 112 · ambulance 912 · fire 110)
    │
    ├── 4. Education
    │   ├── 1–4. Study / Career / Math / English  (AI tip)
    │   ├── 5. My question
    │   └── 6. Nearby schools  (static directory)
    │
    ├── 5. Ask AI  (free-form question, paginated CON for long answers)
    │
    └── 6. Account
        ├── 1. My stats    · 2. Set name  · 3. Set profession
        ├── 4. Language    · 5. SMS alerts · 6. Daily tips
        └── 0. Main menu
```

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/manziosee/ussd.git
cd ussd
```

Edit `.env` (key entries):

```env
# AI (Groq — free tier available at console.groq.com)
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant

# Database — Neon (free at neon.tech) or local Docker
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname

# SMS Gateway (points to the sms-gateway Docker service)
SMS_GATEWAY_URL=http://sms-gateway:8001

# Jasmin connector routing
SMS_GW_JASMIN_HOST=jasmin
SMS_GW_CONNECTOR_MAP_JSON={"250":"mtn_rw","254":"safaricom_ke"}

# USSD webhook security (leave empty for local dev / AT sandbox)
AT_API_KEY=
AT_WEBHOOK_TOKEN=
```

### 2. Run with Docker Compose

```bash
docker-compose up -d
```

This starts: PostgreSQL · Redis · RabbitMQ · Jasmin · SMS Gateway · USSD App.

```
Service          URL
───────────────────────────────────────────────────────
USSD app         http://localhost:8000
SMS Gateway      http://localhost:8001
Admin dashboard  http://localhost:8000/admin/dashboard?key=<ADMIN_API_KEY>
API docs         http://localhost:8000/docs
RabbitMQ UI      http://localhost:15672  (jasmin / jasmin)
Jasmin CLI       telnet localhost 8990   (admin / admin)
```

### 3. Configure Jasmin SMPP connectors

Connect to the Jasmin CLI and add one connector per telecom operator:

```bash
telnet localhost 8990
# Login: admin / admin

# Add a connector for MTN Rwanda
smppccm -a
> cid mtn_rw
> host smpp.mtn.rw
> port 2775
> username your_smpp_user
> password your_smpp_pass
> systype MTN
> ok

# Add an MT (Mobile Terminated) route so messages use this connector
mtrouter -a
> order 10
> type DefaultRoute
> connector smppc(mtn_rw)
> ok

# Persist and start
persist
smppccm -1 mtn_rw
quit
```

> **Test mode:** If you don't have real SMPP credentials yet, run Jasmin in loopback mode using `smpp.ozekisms.com:9500` as a free public test SMPP server.

### 4. Run without Docker (development)

```bash
# Install dependencies
pip install -r requirements.txt

# Start USSD app (uses fakeredis if Redis unavailable)
uvicorn app.main:app --reload --port 8000

# Start SMS Gateway (separate terminal)
cd sms_gateway
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

> **No Redis?** The server auto-detects unavailability and falls back to an in-memory
> `fakeredis` store — zero config for development.

### 5. Test with the CLI simulator

```bash
python simulator/cli_sim.py
```

```
══════════════════════════════════════════════════
   SmartAssist USSD Simulator
══════════════════════════════════════════════════
  Phone : +250788123456
  Server: http://localhost:8000

┌────────────────────────────────────┐
│  Welcome to SmartAssist!           │
│  Choose language:                  │
│  1.English                         │
│  2.Kinyarwanda                     │
└────────────────────────────────────┘
  Your input: _
```

### 6. Run tests

```bash
pytest
```

All 45 tests pass with no external services (Redis, DB, AI, Jasmin all mocked).

---

## SMS Gateway API

The SMS Gateway runs as a separate microservice on port 8001.

### Send a single SMS

```bash
curl -X POST http://localhost:8001/sms/send \
  -H "Content-Type: application/json" \
  -d '{"to": "+250788000001", "message": "Hello from SmartAssist!"}'
```

```json
{
  "success": true,
  "message_id": "01234-5678-uuid",
  "connector": "mtn_rw",
  "country_code": "250",
  "error": null
}
```

### Send bulk (daily tips)

```bash
curl -X POST http://localhost:8001/sms/send-bulk \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": ["+250788000001", "+254700000001", "+256700000001"],
    "message": "Daily tip: Set price = cost + 30% profit min.",
    "sender_id": "SmartAssist"
  }'
```

```json
{"sent": 3, "failed": 0, "results": [...]}
```

### Gateway health

```bash
curl http://localhost:8001/health
```

```json
{"status": "ok", "jasmin_reachable": true, "version": "1.0.0"}
```

---

## Admin API

All admin routes require `X-Admin-Key: <ADMIN_API_KEY>` header (or `?key=` for browser).

| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/dashboard` | HTML dashboard with charts |
| `GET` | `/admin/stats` | Aggregated analytics (users, queries, cache rate) |
| `GET` | `/admin/interactions` | Query history (paginated, filterable) |
| `GET` | `/admin/users` | User list |
| `GET` | `/admin/market-prices` | Crop price list |
| `PUT` | `/admin/market-prices` | Upsert a crop price |
| `POST` | `/admin/market-prices/bulk` | Bulk upsert market prices |
| `DELETE` | `/admin/market-prices/{id}` | Delete a price entry |
| `GET` | `/admin/feedback` | Helpful vs not-helpful counts by category |
| `POST` | `/ussd` | AT USSD webhook (form-encoded) |
| `POST` | `/simulate` | Local USSD simulator (JSON) |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

---

## Project Structure

```
ussd/
├── app/                          # ── USSD Application ──────────────────────
│   ├── main.py                   # FastAPI app, lifespan, startup validation
│   ├── config.py                 # All settings via pydantic-settings + .env
│   ├── auth.py                   # USSD webhook token + HMAC guard
│   ├── database.py               # Async SQLAlchemy, Neon SSL auto-config
│   ├── models/
│   │   ├── user.py               # Phone · name · profession · language · onboarded
│   │   ├── interaction.py        # AI query log (tokens, cache hit, SMS sent)
│   │   ├── market_price.py       # Crop prices per district
│   │   └── feedback.py           # User helpful/not-helpful ratings
│   ├── services/
│   │   ├── menu_service.py       # ★ USSD state machine (onboarding → main menu)
│   │   ├── ai_service.py         # Groq Llama 3.1 8B + Redis response cache + retry
│   │   ├── session_service.py    # Redis: sessions · cache · rate limit · pagination
│   │   ├── knowledge_service.py  # 15 pre-seeded offline responses (zero API cost)
│   │   └── sms_service.py        # HTTP client → SMS Gateway (/sms/send)
│   ├── routes/
│   │   ├── ussd.py               # POST /ussd (AT webhook) + POST /simulate
│   │   ├── admin.py              # /admin/* endpoints + HTML dashboard
│   │   └── cron.py               # POST /cron/daily-tips
│   ├── data/
│   │   ├── emergency.py          # Rwanda emergency numbers (EN + Kinyarwanda)
│   │   └── services.py           # Static agri/health/education directory
│   └── schemas/
│       └── ussd.py               # Pydantic schemas
│
├── sms_gateway/                  # ── SMS Gateway Microservice ──────────────
│   ├── main.py                   # FastAPI app on port 8001
│   ├── config.py                 # Settings (SMS_GW_ prefix)
│   ├── schemas.py                # SMSRequest · SMSResponse · BulkSMS*
│   ├── routes/
│   │   └── sms.py                # POST /sms/send · POST /sms/send-bulk · GET /health
│   ├── services/
│   │   ├── jasmin_client.py      # Jasmin HTTP API client + GSM7/UCS-2 detection
│   │   └── routing.py            # Country code → Jasmin connector name
│   ├── requirements.txt
│   └── Dockerfile
│
├── simulator/
│   └── cli_sim.py                # Terminal USSD simulator (no AT account needed)
├── tests/
│   ├── conftest.py               # Fixtures: mock Redis, DB, AI
│   ├── test_ussd_menu.py         # 30 async tests — all menu paths + edge cases
│   └── test_admin_routes.py      # 15 async tests — admin API + auth
├── alembic/
│   └── versions/                 # 4 migrations (users → interactions → market/feedback → onboarded)
├── docker-compose.yml            # Full stack: db · redis · rabbitmq · jasmin · sms-gw · app
├── docker-compose.dev.yml        # Hot-reload override
├── Dockerfile                    # Production app container
├── requirements.txt              # Main app dependencies
├── alembic.ini
├── pytest.ini
└── .env
```

---

## Cost Model

| Scenario | Cost |
|---|---|
| Pre-defined topic (1–4 in any category) | **$0** — knowledge seed cache |
| Same free question repeated within 24 h | **$0** — Redis response cache |
| New free-form question (Groq) | **< $0.0001** — Llama 3.1 8B at Groq pricing |
| SMS delivery (Jasmin direct SMPP) | **~$0** (direct telecom rate, no per-msg markup) |
| **Blended average per interaction** | **< $0.00005** |

---

## Features

| Feature | Detail |
|---|---|
| **First-time onboarding** | New users choose language + profession before main menu |
| **USSD state machine** | 5 categories, unlimited depth, input sanitisation |
| **Groq AI** | Llama 3.1 8B, ~50 ms median latency, 3-attempt retry with back-off |
| **Redis response cache** | Same answer cached 24 h — zero API cost on repeated questions |
| **Offline knowledge seed** | 15 pre-written responses at startup — zero latency & zero cost |
| **SMS via Jasmin** | Own SMPP infrastructure; country-code routing; GSM7/UCS-2 auto-detect |
| **Bulk SMS** | Daily tip broadcasts to all opted-in subscribers |
| **USSD pagination** | Long AI answers split into 160-char pages with 1.Next / 0.Stop |
| **Market prices** | Real Rwanda crop prices from DB (5 districts × 6 crops) |
| **Feedback rating** | Helpful / Not helpful stored per tip; admin aggregate view |
| **Emergency numbers** | Health menu option 7 — Rwanda police/ambulance/fire in EN + RW |
| **Kinyarwanda support** | Menus + AI + SMS in Kinyarwanda; UCS-2 encoding auto-detected |
| **Session resume** | Drop and redial within 10 min offers to resume where you left off |
| **Rate limiting** | 50 queries / phone / hour via Redis INCR |
| **Dedup protection** | AT retry callbacks return cached reply, not a second AI call |
| **Admin dashboard** | HTML dashboard with Chart.js + JSON API |
| **Alembic migrations** | Async-compatible, 4 migrations applied to Neon DB |
| **45-test suite** | Menu + admin routes, fully mocked, no external services needed |

---

## License

MIT — free to use, modify, and deploy.

---

*Built for African communities — making AI accessible to everyone, everywhere.*
