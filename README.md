# Account Enrichment Pipeline

A local Python backend that reads accounts from Google Sheets, runs each
through a multi-agent enrichment pipeline (Gemini + Tavily + Firecrawl),
and writes qualified accounts to Pipedrive with a full dossier and
LinkedIn Sales Navigator search commands. A single-page HTML dashboard
served by the same backend shows live progress.

See `plan.md` and `architecture.md` for the full design.

## Setup

```bash
cd BDRAGENT
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in the keys in .env
# Drop your Google service account JSON next to .env (or set its path)
```

Required env vars:

- `GEMINI_API_KEY`
- `TAVILY_API_KEY`
- `FIRECRAWL_API_KEY`
- `PIPEDRIVE_API_KEY`
- `GOOGLE_SHEET_ID` — the spreadsheet ID (the long string between `/d/` and `/edit` in the URL)
- `GOOGLE_SERVICE_ACCOUNT_JSON` — path to the service-account JSON file (relative to the project root, or absolute)
- `BATCH_SIZE` — accounts processed concurrently per batch (default 5)
- `RELEVANCE_THRESHOLD` — minimum score (1-10) to ship to Pipedrive (default 7)

The Google Sheet must have `Name` and `Domain` columns in the first row (case-insensitive). The service-account email must be shared as a viewer on the sheet.

## Run

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Then open <http://localhost:8000>.

In the dashboard:

1. (Optional) override the Google Sheet ID
2. Paste your value proposition
3. Click **Preview sheet** to sanity-check the first 10 rows
4. Click **Start pipeline**
5. Watch accounts move through `pending → running → enriched / dropped / error`

Clicking an account in the left panel opens the **Log**, **Research**, **Evaluation**, and **Pipedrive** tabs.

## How the pipeline works

For each account:

1. **Hypothesiser** — Gemini generates a hypothesis about why this company needs your product right now
2. **News Scout** + **LinkedIn Analyst** — run in parallel: Tavily search, Firecrawl scrape (news only), Gemini structured extraction
3. **Evaluator** — Gemini scores 1-10 strictly. Score ≥ `RELEVANCE_THRESHOLD` → ship to Pipedrive
4. If score is below threshold, the Hypothesiser is re-run with a *different angle*, then re-evaluated. Still below? **Drop**.
5. **LinkedIn Search Generator** builds Sales Navigator Boolean strings; the **Dossier Compiler** writes the Pipedrive note; the **Pipedrive Writer** creates the org + note + label.

All state is written to a local SQLite file (`enrichment.db`) after every step, so a restart resumes cleanly.

## File layout

```
BDRAGENT/
├── backend/
│   ├── main.py              FastAPI app + routes
│   ├── db.py                SQLite schema + helpers
│   ├── config.py            env loading
│   ├── queue_manager.py     batch orchestration
│   ├── agents/              six agents
│   └── integrations/        gemini, tavily, firecrawl, sheets, pipedrive
├── frontend/index.html      single-page dashboard
├── requirements.txt
├── .env.example
└── README.md
```
