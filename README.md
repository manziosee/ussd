# SmartAssist USSD

> **AI for everyone — including the 3 billion people with no internet.**

SmartAssist is an AI-powered USSD assistant that lets any mobile phone user
(feature phone or smartphone, zero internet required) access AI by dialling
a shortcode like `*123#`. Works with any USSD aggregator, any country,
any mobile operator.

---

## Technology Stack

| | Technology | Role |
|---|---|---|
| ![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=flat&logo=python&logoColor=white) | **Python 3.12** | Core language |
| ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white) | **FastAPI** | Async web framework (USSD app + SMS gateway) |
| ![Groq](https://img.shields.io/badge/Groq_Llama-FF6B35?style=flat&logoColor=white) | **Groq — Llama 3.1 8B** | Ultra-fast AI inference (~50 ms) |
| ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white) | **PostgreSQL** | User data, interactions, market prices |
| ![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white) | **Redis** | Sessions, AI cache, rate limiting |
| ![Jasmin](https://img.shields.io/badge/Jasmin_SMPP-2C3E50?style=flat&logoColor=white) | **Jasmin SMS Gateway** | Open-source SMPP gateway — own SMS infrastructure, zero per-SMS cost |
| ![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=flat&logo=rabbitmq&logoColor=white) | **RabbitMQ** | Jasmin internal message queue |
| ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white) | **Docker Compose** | Full-stack deployment |
| ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy_2.0-D71F00?style=flat&logoColor=white) | **SQLAlchemy 2.0** | Async ORM |
| ![Alembic](https://img.shields.io/badge/Alembic-grey?style=flat) | **Alembic** | Database migrations |
| ![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=flat&logo=pytest&logoColor=white) | **pytest-asyncio** | 45-test async suite |

---

## Architecture

```
Any mobile phone dials a shortcode  (no internet — any feature phone)
          │
          ▼
┌──────────────────────────────────────┐
│         USSD Aggregator              │
│  (your regional USSD network         │
│   partner — AT, Comviva, Ericsson,   │
│   NTTDATA, local operator, etc.)     │
└──────────────┬───────────────────────┘
               │  POST /ussd  (form-encoded)
               │  sessionId · phoneNumber · text
               ▼
┌──────────────────────────────────────────────────────────────────┐
│              SmartAssist USSD App  (port 8000)                   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                USSD State Machine                        │   │
│  │  Parses *-separated input → routes to correct handler   │   │
│  └─────────────────────┬────────────────────────────────────┘   │
│         ┌──────────────┼──────────────┐                         │
│         ▼              ▼              ▼                         │
│  ┌────────────┐  ┌──────────┐  ┌───────────────┐              │
│  │   Redis    │  │  Groq    │  │  PostgreSQL   │              │
│  │  Sessions  │  │  Llama   │  │  Users        │              │
│  │  AI cache  │  │  3.1 8B  │  │  Interactions │              │
│  │  Rate limit│  │  ~50 ms  │  │  Market prices│              │
│  └────────────┘  └──────────┘  └───────────────┘              │
│                                                                   │
│  Long answer → POST /sms/send                                    │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│             SMS Gateway API  (port 8001)                         │
│                                                                   │
│  • Validates E.164 phone number                                   │
│  • Extracts country dialing prefix                                │
│  • Looks up Jasmin connector (or lets Jasmin route globally)      │
│  • Detects GSM-7 vs UCS-2 encoding automatically                 │
│  • Bulk send for daily tip broadcasts                             │
└──────────────────────┬───────────────────────────────────────────┘
                       │  POST to Jasmin HTTP API (port 1401)
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                Jasmin SMPP Gateway  (port 1401/2775)             │
│                                                                   │
│  Connectors are named by ISO country code and point to           │
│  whatever SMPP provider the operator chooses.                    │
│  Add/remove via:  telnet localhost 8990  (Jasmin CLI)            │
│                                                                   │
│  Default mode: empty connector map → Jasmin's MT routing rules   │
│  decide automatically — works globally with any provider.        │
└──────────────────────┬───────────────────────────────────────────┘
                       │  SMPP v3.4
                       ▼
           Telecom Operator  (any country, any network)
                       │
                       ▼
                 User's Phone
```

---

## Why Jasmin Instead of Twilio / Third-Party SMS APIs?

| | Third-party SMS API | Jasmin SMPP |
|---|---|---|
| **Cost per SMS** | $0.0075 – $0.05 | ~$0 (direct operator rate) |
| **Infrastructure** | Vendor cloud | Your own server |
| **Latency** | 1–5 s (cloud relay) | < 500 ms (direct SMPP) |
| **Multi-country** | Different API per provider | One gateway, all operators |
| **Carrier lock-in** | Yes | None — swap providers without code changes |
| **Data sovereignty** | Vendor servers | Your servers |

---

## Menu Structure

```
Dial shortcode → Onboarding (new users: language + role) → Main Menu
└── SmartAssist AI
    ├── 1. Business
    │   ├── 1–4. Pricing / Bookkeeping / Marketing / Get customers  (AI tip → CON)
    │   │         └── 1.More tips · 2.More detail · 3.Send SMS · 4.Helpful · 5.Not helpful
    │   ├── 5. My question  (free AI question — paginated for long answers)
    │   └── 6. Calculator   (profit check · loan payment — zero AI cost)
    │
    ├── 2. Farming
    │   ├── 1–3. Soil / Pest control / Best crops  (AI tip)
    │   ├── 4. Market prices  (DB-backed, configurable per deployment)
    │   ├── 5. My question
    │   └── 6. Nearby offices  (configurable services directory)
    │
    ├── 3. Health
    │   ├── 1–4. Nutrition / Hygiene / Maternal / Child  (AI tip)
    │   ├── 5. My question
    │   ├── 6. Nearby clinics  (configurable services directory)
    │   └── 7. Emergency numbers  (configurable per country)
    │
    ├── 4. Education
    │   ├── 1–4. Study / Career / Math / English  (AI tip)
    │   ├── 5. My question
    │   └── 6. Nearby schools  (configurable services directory)
    │
    ├── 5. Ask AI  (free-form question, paginated for long answers)
    │
    └── 6. Account
        ├── 1. My stats  · 2. Set name  · 3. Set profession
        ├── 4. Language  · 5. SMS alerts · 6. Daily tips
        └── 0. Main menu
```

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/manziosee/ussd.git
cd ussd
```

Edit `.env` (key settings):

```env
# AI — get a free key at console.groq.com
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant

# Your USSD shortcode (assigned by your USSD aggregator)
USSD_SHORTCODE=*123#

# Database — Neon free tier at neon.tech, or local Docker
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname

# SMS gateway (Docker service name; use http://localhost:8001 locally)
SMS_GATEWAY_URL=http://sms-gateway:8001

# Jasmin — leave empty to use Jasmin's global routing rules (recommended)
SMS_GW_CONNECTOR_MAP_JSON={}

# USSD webhook security (leave empty for local dev / sandbox)
AT_API_KEY=
AT_WEBHOOK_TOKEN=
```

### 2. Start with Docker Compose

```bash
docker-compose up -d
```

| Service | URL |
|---|---|
| USSD app | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Admin dashboard | http://localhost:8000/admin/dashboard?key=`<ADMIN_API_KEY>` |
| SMS Gateway | http://localhost:8001 |
| Jasmin CLI | `telnet localhost 8990` (admin / admin) |
| RabbitMQ UI | http://localhost:15672 (jasmin / jasmin) |

### 3. Connect an SMPP provider in Jasmin

Jasmin connects to telecom operators via SMPP. Use the Jasmin CLI to add connectors:

```bash
telnet localhost 8990
# Username: admin   Password: admin
```

```
# Add a connector — name it with the ISO country code
smppccm -a
> cid ke
> host smpp.your-provider.com
> port 2775
> username your_smpp_user
> password your_smpp_pass
> ok

# Add a catch-all MT route (sends all numbers through this connector)
mtrouter -a
> order 100
> type DefaultRoute
> connector smppc(ke)
> ok

# Save and start
persist
smppccm -1 ke
quit
```

> **Multiple countries:** add one connector per country (`ke`, `ng`, `gh`, `in`, `pk` …),
> then add MT route filters so Jasmin routes each prefix to the right connector.
> The SMS gateway will honour Jasmin's routing automatically.

> **Test SMPP server:** `smpp.ozekisms.com:9500` (free public test endpoint — no real SMS sent).

### 4. Run without Docker (development)

```bash
# Install main app dependencies
pip install -r requirements.txt

# Start USSD app (auto-uses fakeredis if Redis is unavailable)
uvicorn app.main:app --reload --port 8000

# In a second terminal — start SMS gateway
cd sms_gateway
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

### 5. Test with the simulator

```bash
python simulator/cli_sim.py
```

```
══════════════════════════════════════════
   SmartAssist USSD Simulator
══════════════════════════════════════════

┌────────────────────────────────────────┐
│  Welcome to SmartAssist!               │
│  Choose language:                      │
│  1.English                             │
│  2.Kinyarwanda                         │
└────────────────────────────────────────┘
  Your input: _
```

### 6. Run tests

```bash
pytest
```

All 45 tests pass with no external services required.

---

## SMS Gateway API

The gateway runs as an independent microservice on port 8001.

### Send a single SMS

```bash
curl -X POST http://localhost:8001/sms/send \
  -H "Content-Type: application/json" \
  -d '{"to": "+254700000001", "message": "Hello from SmartAssist!"}'
```

```json
{
  "success": true,
  "message_id": "01234-5678-uuid",
  "connector": null,
  "country_code": "254",
  "error": null
}
```

`connector: null` means Jasmin's own routing rules dispatched the message — the correct global default.

### Bulk send (daily tips broadcast)

```bash
curl -X POST http://localhost:8001/sms/send-bulk \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": ["+254700000001", "+234800000001", "+91900000001"],
    "message": "Daily tip: Price = cost + 30% profit minimum.",
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

## SMS Gateway — Country Routing

The connector map is **empty by default**. Jasmin handles routing globally through its own MT route rules — you configure those once in the Jasmin CLI, and the gateway never needs to know about carriers.

To override routing for specific prefixes, set `SMS_GW_CONNECTOR_MAP_JSON`:

```env
# Route by country code prefix → your named Jasmin connector
SMS_GW_CONNECTOR_MAP_JSON={"254":"ke","234":"ng","91":"in","44":"uk"}
```

Connector names are ISO 3166-1 alpha-2 country codes. They map to SMPP connections you configure in Jasmin — entirely carrier-agnostic.

---

## Admin API

All admin routes require `X-Admin-Key: <ADMIN_API_KEY>`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/dashboard` | HTML dashboard with charts |
| `GET` | `/admin/stats` | Aggregated analytics |
| `GET` | `/admin/interactions` | Query history (paginated) |
| `GET` | `/admin/users` | User list |
| `GET` | `/admin/market-prices` | Crop price list |
| `PUT` | `/admin/market-prices` | Upsert a single price |
| `POST` | `/admin/market-prices/bulk` | Bulk upsert prices |
| `DELETE` | `/admin/market-prices/{id}` | Delete a price |
| `GET` | `/admin/feedback` | Helpful / not-helpful counts |
| `POST` | `/ussd` | USSD webhook (form-encoded) |
| `POST` | `/simulate` | Local USSD simulator (JSON) |
| `GET` | `/health` | Health check |

---

## Localisation

The system ships with English and Kinyarwanda menus. To add a language:

1. Add entries to `_STRINGS` in `app/services/menu_service.py`
2. Add category labels to `_LABELS` in `app/services/broadcast_service.py`
3. Add the AI language hint in `app/services/ai_service.py`

## Local Services Directory

`app/data/services.py` and `app/data/emergency.py` contain sample data for
one deployment region. Replace these files with your own districts, clinics,
schools, and emergency numbers. The menu system reads them dynamically —
no code changes needed, only data.

---

## Project Structure

```
ussd/
├── app/                          # USSD Application (port 8000)
│   ├── main.py                   # FastAPI app, lifespan, startup
│   ├── config.py                 # All settings via .env (incl. USSD_SHORTCODE)
│   ├── auth.py                   # USSD webhook HMAC + token guard
│   ├── models/                   # User · Interaction · MarketPrice · Feedback
│   ├── services/
│   │   ├── menu_service.py       # USSD state machine
│   │   ├── ai_service.py         # Groq Llama 3.1 8B + Redis cache + retry
│   │   ├── session_service.py    # Redis sessions, cache, rate limit, pagination
│   │   ├── knowledge_service.py  # 15 pre-seeded offline responses
│   │   ├── sms_service.py        # HTTP client → SMS Gateway
│   │   └── broadcast_service.py  # Daily tip broadcast (uses USSD_SHORTCODE)
│   ├── routes/
│   │   ├── ussd.py               # POST /ussd + POST /simulate
│   │   ├── admin.py              # /admin/* + HTML dashboard
│   │   └── cron.py               # POST /cron/daily-tips
│   └── data/
│       ├── emergency.py          # Emergency numbers (replace for your country)
│       └── services.py           # Local services directory (replace for your region)
│
├── sms_gateway/                  # SMS Gateway microservice (port 8001)
│   ├── main.py                   # FastAPI app
│   ├── config.py                 # SMS_GW_ prefixed settings
│   ├── schemas.py                # SMSRequest · SMSResponse · BulkSMS*
│   ├── routes/sms.py             # POST /sms/send · /sms/send-bulk · GET /health
│   └── services/
│       ├── jasmin_client.py      # Jasmin HTTP API + GSM-7/UCS-2 auto-detect
│       └── routing.py            # Dialing prefix → connector (100+ countries)
│
├── simulator/cli_sim.py          # Terminal USSD simulator
├── tests/
│   ├── conftest.py               # Shared fixtures
│   ├── test_ussd_menu.py         # 30 menu tests
│   └── test_admin_routes.py      # 15 admin route tests
├── alembic/versions/             # 4 DB migrations
├── docker-compose.yml            # db · redis · rabbitmq · jasmin · sms-gateway · app
├── Dockerfile
└── requirements.txt
```

---

## Cost Model

| Scenario | Cost |
|---|---|
| Pre-defined topic (any category) | **$0** — knowledge cache |
| Same free question within 24 h | **$0** — Redis response cache |
| New free-form question (Groq) | **< $0.0001** |
| SMS via Jasmin (direct SMPP) | **~$0** — direct operator rate |
| **Blended average per interaction** | **< $0.00005** |

---

## License

MIT — free to use, modify, and deploy.

---

*Built to make AI accessible to everyone, everywhere.*
