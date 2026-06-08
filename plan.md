# Account Enrichment Pipeline — Project Plan

## What we are building

A local Python backend that reads 100 accounts from Google Sheets, runs each account through a multi-agent enrichment pipeline, and writes qualified accounts to Pipedrive with a full dossier and LinkedIn search commands. A single-page HTML dashboard served by the backend shows live progress.

## Stack


| Layer           | Technology                          | Reason                                                     |
| --------------- | ----------------------------------- | ---------------------------------------------------------- |
| Backend         | Python 3.11 + FastAPI               | Async, easy local run, serves the HTML dashboard too       |
| LLM             | Google Gemini 1.5 Flash             | User already has key, fast and cheap for structured output |
| Web search      | Tavily API                          | Purpose-built for agents, returns clean summaries + URLs   |
| Scraping        | Firecrawl API                       | Scrapes full article text from URLs Tavily finds           |
| Persistence     | SQLite via `aiosqlite`              | Zero setup, survives tab crashes, full audit log           |
| Account source  | Google Sheets API v4                | Live sync via service account                              |
| CRM destination | Pipedrive REST API                  | Create/update orgs, attach enrichment notes                |
| Dashboard       | Vanilla HTML/JS (served by FastAPI) | Single command startup, no Node required                   |


## Agent pipeline per account

```
Hypothesiser (Gemini)
    ↓
News Scout (Tavily search → Firecrawl scrape) ──┐
                                                  ├─ run in parallel
LinkedIn Analyst (Tavily search)        ──────────┘
    ↓
Compile + Relevance Evaluator (Gemini)
    ↓
[score >= 7] → LinkedIn Search Command Generator (Gemini)
             → Pipedrive Writer
             → DONE

[score < 7]  → Re-Hypothesiser (Gemini, different angle)
             → Relevance Evaluator pass 2 (Gemini)
             → [score >= 7] → Pipedrive Writer → DONE
             → [score < 7]  → DROP → NEXT ACCOUNT

```

## Batch behaviour

- Accounts are processed in batches of 5 concurrently
- Each account is independent — one failure does not block others
- Failed accounts are retried up to 2 times before being marked `error`
- State is written to SQLite after every agent step, so a restart resumes cleanly

## Persistent state (SQLite)

Three tables:

- `runs` — one row per pipeline run (start time, value prop, status)
- `accounts` — one row per account (status, batch number, all agent outputs as JSON)
- `logs` — one row per agent step (account_id, step name, message, timestamp)

## API surface (FastAPI)


| Method | Path                      | Purpose                                 |
| ------ | ------------------------- | --------------------------------------- |
| GET    | `/`                       | Serves the HTML dashboard               |
| POST   | `/api/runs`               | Start a new pipeline run                |
| GET    | `/api/runs/{id}`          | Run status + summary counts             |
| GET    | `/api/runs/{id}/accounts` | All accounts + their current state      |
| GET    | `/api/accounts/{id}`      | Full detail for one account             |
| GET    | `/api/accounts/{id}/logs` | Step-by-step log for one account        |
| DELETE | `/api/runs/{id}`          | Cancel a running pipeline               |
| GET    | `/api/sheets/preview`     | Preview first 10 rows from Google Sheet |


## Dashboard (index.html)

Single HTML file with vanilla JS. No build step. Polls `/api/runs/{id}` every 3 seconds while a run is active. Shows:

- Run controls (sheet URL, value prop, batch size)
- Progress bar with counts (pending / running / enriched / dropped / error)
- Account list with live status icons
- Detail panel: agent log, hypothesis, scores, talking points, news signals, LinkedIn pain signals, LinkedIn search commands, Pipedrive note preview

## Configuration (.env)

```
GEMINI_API_KEY=
TAVILY_API_KEY=
FIRECRAWL_API_KEY=
PIPEDRIVE_API_KEY=
GOOGLE_SHEET_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service-account.json
VALUE_PROP=                        # default, overridable per run
BATCH_SIZE=5
RELEVANCE_THRESHOLD=7

```

## Running locally

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# open http://localhost:8000

```

## Deliverables checklist

- [ ] `backend/main.py` — FastAPI app + all routes
- [ ] `backend/db.py` — SQLite schema, init, helper functions
- [ ] `backend/config.py` — env loading + validation
- [ ] `backend/queue_manager.py` — batch orchestration, concurrency, retry
- [ ] `backend/agents/hypothesiser.py`
- [ ] `backend/agents/news_scout.py`
- [ ] `backend/agents/linkedin_analyst.py`
- [ ] `backend/agents/evaluator.py`
- [ ] `backend/agents/linkedin_search.py`
- [ ] `backend/agents/dossier_compiler.py`
- [ ] `backend/integrations/sheets.py`
- [ ] `backend/integrations/pipedrive.py`
- [ ] `backend/integrations/gemini.py` — thin wrapper, structured output helper
- [ ] `backend/integrations/tavily.py` — search wrapper
- [ ] `backend/integrations/firecrawl.py` — scrape wrapper
- [ ] `frontend/index.html` — full dashboard
- [ ] `requirements.txt`
- [ ] `.env.example`
- [ ] `README.md` — setup instructions

