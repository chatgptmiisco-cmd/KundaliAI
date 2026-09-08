# KundaliAI Backend

Bilingual (Hindi/English) Vedic astrology backend — Lahiri ayanamsa, sidereal
zodiac, whole-sign houses. FastAPI + SQLAlchemy (async) + Swiss Ephemeris.

## Quick start

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

cp .env.example .env            # then edit .env if you have real API keys

alembic upgrade head             # creates kundaliai.db (SQLite) with the full schema
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API reference (Swagger UI).

Run the test suite (257 tests, no network/API keys required):

```bash
pytest
```

## Why Python 3.11, not 3.12

`pyswisseph` (the Swiss Ephemeris binding used for planetary positions) has
no published wheel for Python 3.12 on Windows, and there's no C++ compiler
in this environment to build it from source. If your `.venv` was created
with 3.12, recreate it with 3.11:
```bash
py -3.11 -m venv .venv
```

## What's real vs. stubbed in this pass

Everything astrology-related is **real**: Lahiri ayanamsa, sidereal
positions (Swiss Ephemeris, Moshier semi-analytic mode — no ephemeris data
files needed), whole-sign houses, D1/D9/D10 divisional charts, and the full
Vimshottari Mahadasha/Antardasha/Pratyantardasha calculation with correct
balance-of-dasha at birth. See `tests/test_astro_*.py` — every chart/dasha
formula is verified against the classical rule stated in plain words, not
just "it runs".

**Real and wired up:**
- Email+password auth (JWT, bcrypt)
- Birth profile CRUD, encrypted at rest (Fernet), cache invalidation on edit
- D1/D9/D10 charts, dasha timeline, daily horoscope, period analysis — all
  DB-cached (chart/dasha cache keyed by birth-profile version; horoscope
  cache keyed by date; period analysis cache keyed by date range)
- Free-tier monthly quota on period analyses (`FREE_MONTHLY_PERIOD_ANALYSES`)
- Subscription tiers (free/insight/strategy) gating premium endpoints
- LLM interpretation layer — **real Claude calls if `ANTHROPIC_API_KEY` is
  set**, otherwise a deterministic template fallback (same interface, so
  nothing else changes when you add a key)
- Rate limiting on calculation/LLM/voice endpoints (slowapi)
- Structured JSON logging, request-id tracing
- Account deletion (hard delete, cascades everywhere)
- Admin endpoints (masked user list, subscription status, cache invalidation)
- Alembic migrations

**Stubbed behind a clean interface, documented in-code where to plug in a
real provider:**
- Phone+OTP — fully working *flow*, but the code is returned in the API
  response instead of sent via SMS (`app/services/auth_service.py`)
- OAuth (Google/Apple) — raises a clear `501 Not Implemented`; needs their
  SDKs + your client credentials (`app/services/auth_service.py`)
- STT/TTS — return an honest "not configured" response rather than faking
  audio (`app/services/voice/stt.py`, `tts.py`). The frontend should fall
  back to on-device TTS with the returned text.
- Razorpay — checkout simulates an instant successful subscription with no
  real payment when no keys are set; webhook signature verification and the
  real Orders-API call are implemented and activate for real the moment you
  set `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/`RAZORPAY_WEBHOOK_SECRET`
  (`app/services/payments/razorpay_client.py`)

## Architecture

```
app/
  astro/          Pure calculation engine — no DB, no I/O, fully unit-tested.
                   ephemeris.py (Swiss Ephemeris wrapper) → charts.py (D1/D9/D10)
                   → dasha.py (Vimshottari) → transits.py
  core/            Settings, JWT/password/PII-encryption, logging, rate limiting
  db/              SQLAlchemy models + async engine/session
  schemas/         Pydantic request/response models (one file per API area)
  services/        Business logic — orchestrates astro/ + DB caching + LLM
    interpretation/  The LLM layer: base.py (interface) + claude_interpreter.py
                     (real) + templates.py (deterministic fallback) + factory.py
    voice/           STT/TTS provider interfaces + stubs
    payments/        Razorpay client + subscription state machine
    i18n/            Static server-side string localization (not dynamic content)
  api/v1/          Routers — thin: parse request, call a service, return it
  middleware/      Request logging
tests/
  test_astro_*.py  Unit tests for the calculation engine (no DB, no network)
  test_api_e2e.py  Full API flow against an isolated SQLite file
```

**Caching model:** every expensive computation (chart, dasha, horoscope,
period analysis) is cached as a DB row, not an in-memory/Redis cache — this
survives restarts and needs no extra infrastructure at this scale. A birth
profile edit doesn't delete old cache rows; it bumps `BirthProfile.version`,
which makes every existing row for that user simply stop matching (never
selected again). A periodic job to prune stale-version rows would be a
sensible addition once this is under real load, but isn't needed yet.

**Subscription tiers:** `free < insight < strategy`. See
`app/api/deps.py::require_tier` for the gating dependency and each router
for which endpoints use which minimum tier — D1/dasha/daily horoscope are
free; D9/D10/voice explanation are Insight; text/voice chat (`/chat/astro`)
is Strategy.

## Generating a new migration after changing a model

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## Frontend integration

Not wired up yet in this pass — the React Native app (`../src/api/client.ts`)
still talks to its own mock layer. Swapping that for real HTTP calls against
this backend is a follow-up; the API shapes here were designed to map onto
the same data the frontend already expects (see `app/schemas/`).
