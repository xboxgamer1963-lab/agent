# Account Enrichment Pipeline — Architecture Spec

> Hand this file to Claude Code alongside PLAN.md. Every file, every function signature, every data contract is defined here. Implement exactly what is specified. Do not add extra abstractions.

---

## Directory structure

```
enrichment-pipeline/
├── backend/
│   ├── main.py
│   ├── db.py
│   ├── config.py
│   ├── queue_manager.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── hypothesiser.py
│   │   ├── news_scout.py
│   │   ├── linkedin_analyst.py
│   │   ├── evaluator.py
│   │   ├── linkedin_search.py
│   │   └── dossier_compiler.py
│   └── integrations/
│       ├── __init__.py
│       ├── gemini.py
│       ├── tavily.py
│       ├── firecrawl.py
│       ├── sheets.py
│       └── pipedrive.py
├── frontend/
│   └── index.html
├── requirements.txt
├── .env.example
└── README.md

```

---

## requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
aiosqlite==0.20.0
httpx==0.27.0
google-generativeai==0.7.2
python-dotenv==1.0.1
gspread==6.1.2
google-auth==2.29.0
pydantic==2.7.1

```

---

## .env.example

```
GEMINI_API_KEY=
TAVILY_API_KEY=
FIRECRAWL_API_KEY=
PIPEDRIVE_API_KEY=
GOOGLE_SHEET_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=service-account.json
BATCH_SIZE=5
RELEVANCE_THRESHOLD=7

```

---

## backend/config.py

Load all env vars at startup. Raise a clear error if any required key is missing.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str
    tavily_api_key: str
    firecrawl_api_key: str
    pipedrive_api_key: str
    google_sheet_id: str
    google_service_account_json: str
    batch_size: int = 5
    relevance_threshold: int = 7

    class Config:
        env_file = ".env"

settings = Settings()

```

---

## backend/db.py

### Schema

```sql
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    value_prop  TEXT    NOT NULL,
    sheet_id    TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    -- status values: pending | running | completed | cancelled
    total       INTEGER DEFAULT 0,
    done        INTEGER DEFAULT 0,
    enriched    INTEGER DEFAULT 0,
    dropped     INTEGER DEFAULT 0,
    errors      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id),
    name            TEXT    NOT NULL,
    domain          TEXT,
    row_index       INTEGER,           -- original row in sheet
    status          TEXT    NOT NULL DEFAULT 'pending',
    -- status: pending | running | enriched | dropped | error
    batch_number    INTEGER,
    hypothesis_1    TEXT,              -- JSON
    hypothesis_2    TEXT,              -- JSON (retry angle)
    news            TEXT,              -- JSON
    linkedin        TEXT,              -- JSON
    eval_1          TEXT,              -- JSON
    eval_2          TEXT,              -- JSON
    search_commands TEXT,              -- JSON
    dossier         TEXT,              -- JSON
    pipedrive_org_id TEXT,
    pipedrive_note_id TEXT,
    error_message   TEXT,
    retry_count     INTEGER DEFAULT 0,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    step        TEXT    NOT NULL,
    -- step values: hypothesise | news | linkedin | evaluate |
    --              retry | save | search_cmd | drop | error
    message     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

```

### Functions to implement

```python
async def init_db() -> None
    # Creates all tables if they don't exist

async def create_run(value_prop: str, sheet_id: str) -> int
    # Inserts a run row, returns run_id

async def insert_accounts(run_id: int, accounts: list[dict]) -> list[int]
    # Bulk insert accounts for a run, returns list of account_ids

async def get_run(run_id: int) -> dict | None

async def get_run_accounts(run_id: int) -> list[dict]

async def get_account(account_id: int) -> dict | None

async def get_account_logs(account_id: int) -> list[dict]

async def update_account(account_id: int, **fields) -> None
    # Partial update — only update fields passed as kwargs
    # Always sets updated_at = now()

async def update_run_counts(run_id: int) -> None
    # Recount done/enriched/dropped/errors from accounts table
    # and update the run row

async def add_log(account_id: int, step: str, message: str) -> None
    # Insert a log row with created_at = now()

```

---

## backend/integrations/gemini.py

Thin wrapper around the Gemini API. All agents call this — never call the Gemini SDK directly from agent files.

```python
import google.generativeai as genai
import json

genai.configure(api_key=settings.gemini_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

async def call_gemini(system: str, user: str) -> dict:
    """
    Send a prompt to Gemini. Always request JSON output.
    Parse and return the dict.
    Raise ValueError with the raw text if JSON parsing fails.
    Retry once on failure before raising.
    """

```

---

## backend/integrations/tavily.py

```python
import httpx

async def search(query: str, max_results: int = 5) -> list[dict]:
    """
    POST to https://api.tavily.com/search
    Body: { "api_key": ..., "query": query, "max_results": max_results,
            "search_depth": "advanced", "include_raw_content": False }
    Returns list of { "title", "url", "content", "score" }
    Raises httpx.HTTPStatusError on non-200.
    """

```

---

## backend/integrations/firecrawl.py

```python
import httpx

async def scrape(url: str) -> str:
    """
    POST to https://api.firecrawl.dev/v1/scrape
    Headers: Authorization: Bearer {FIRECRAWL_API_KEY}
    Body: { "url": url, "formats": ["markdown"] }
    Returns the markdown string from response["data"]["markdown"].
    If scrape fails or times out (10s), return empty string — do not raise.
    """

```

---

## backend/integrations/sheets.py

```python
import gspread
from google.oauth2.service_account import Credentials

def get_accounts(sheet_id: str) -> list[dict]:
    """
    Authenticate using service account JSON file at path from config.
    Open sheet by ID. Read the first worksheet.
    Expect columns: Name, Domain (case-insensitive header match).
    Return list of { "name": str, "domain": str, "row_index": int }
    Skip rows where Name is empty.
    Raise ValueError with a clear message if required columns are missing.
    """

```

---

## backend/integrations/pipedrive.py

Base URL: `https://api.pipedrive.com/v1` All requests include `?api_token={PIPEDRIVE_API_KEY}` as query param.

```python
import httpx

async def find_or_create_org(name: str) -> str:
    """
    1. GET /organizations/search?term={name}&exact_match=false&limit=1
    2. If found, return the org id as string.
    3. If not found, POST /organizations with { "name": name }
    4. Return new org id as string.
    """

async def add_note(org_id: str, content: str) -> str:
    """
    POST /notes with { "content": content, "org_id": org_id }
    Returns note id as string.
    """

async def add_label(org_id: str, label: str) -> None:
    """
    PATCH /organizations/{org_id} with { "label": label }
    Silently ignore errors — labels are best-effort.
    """

```

---

## backend/agents/hypothesiser.py

```python
async def run(
    account: dict,          # { name, domain }
    value_prop: str,
    previous_angle: str | None = None   # set on retry
) -> dict:
    """
    Calls Gemini with a system prompt explaining the task.
    If previous_angle is set, instruct Gemini to try a completely
    different angle and explain why the previous one failed.

    Returns:
    {
        "hypothesis": str,      # 1-2 sentences: why this company needs us NOW
        "angle": str,           # short label for this angle, e.g. "scaling pain"
        "reasoning": str        # what signals suggest this angle
    }
    """

```

**System prompt template:**

```
You are a B2B sales strategist. Given a company and a product value proposition,
generate a sharp hypothesis about why this company might urgently need this product
right now. Be specific — reference the type of company, its growth stage, and
likely operational pain points.
{IF RETRY: The previous angle "{previous_angle}" did not score high enough.
Try a completely different angle — different pain point, different trigger, different urgency.}
Return ONLY valid JSON with keys: hypothesis, angle, reasoning.

```

---

## backend/agents/news_scout.py

```python
async def run(account: dict) -> dict:
    """
    Step 1: Tavily search with query:
        "{name} {domain} news funding product launch 2024 2025"
    Step 2: Take top 2 results. For each, Firecrawl scrape the URL.
    Step 3: Send all scraped content to Gemini to extract structured signals.

    Returns:
    {
        "headline": str,            # most important signal in one sentence
        "funding": str | null,      # e.g. "Series B $40M, March 2025"
        "product_launch": str | null,
        "exec_change": str | null,
        "growth_signal": str | null,
        "sources": [str]            # URLs used
    }
    """

```

**Gemini extraction prompt:**

```
You are a news analyst. Extract structured signals from these articles about {name}.
Return ONLY valid JSON with keys: headline, funding, product_launch, exec_change,
growth_signal, sources.
Set fields to null if no relevant information found. Do not invent information.

```

---

## backend/agents/linkedin_analyst.py

```python
async def run(account: dict) -> dict:
    """
    Step 1: Tavily search with query:
        "{name} hiring jobs site:linkedin.com OR site:greenhouse.io OR site:lever.co"
    Step 2: Second Tavily search:
        "{name} {domain} team growth engineering sales 2024 2025"
    Step 3: Gemini analysis of results to extract pain signals.

    Returns:
    {
        "open_roles": [str],            # list of role titles found
        "pain_signals": [str],          # inferred operational pain points
        "team_growth": str,             # e.g. "Hiring aggressively in Sales"
        "likely_initiatives": [str]     # e.g. "Expanding into enterprise"
    }
    """

```

---

## backend/agents/evaluator.py

```python
async def run(
    account: dict,
    value_prop: str,
    hypothesis: dict,
    news: dict,
    linkedin: dict,
    is_retry: bool = False
) -> dict:
    """
    Calls Gemini to score relevance strictly.
    Score 7+ only if there is a genuine, specific, urgent fit signal.
    relevant = True only if score >= settings.relevance_threshold.

    Returns:
    {
        "score": int,               # 1-10
        "relevant": bool,
        "verdict": str,             # one sentence explanation
        "fit_reasons": [str],       # specific evidence for the score
        "talking_points": [str],    # 2-3 sharp lines for the cold call
        "suggested_angle": str      # the recommended opening angle
    }
    """

```

**System prompt:**

```
You are a strict B2B sales relevance evaluator. Score this account 1-10.
Score 7 or above ONLY if ALL of these are true:
  1. There is a specific, recent signal (news or hiring) that creates urgency
  2. The value proposition directly addresses a pain point you can evidence
  3. The timing is right — the company is in a state of change or growth
Be harsh. A generic fit is a 5. A strong fit with evidence is a 7+.
Return ONLY valid JSON: score, relevant (bool, true only if score >= {threshold}),
verdict, fit_reasons (array), talking_points (array), suggested_angle.

```

---

## backend/agents/linkedin_search.py

```python
async def run(
    account: dict,
    evaluation: dict,
    linkedin: dict
) -> dict:
    """
    Generates LinkedIn Sales Navigator Boolean search strings.
    Infers the best decision-maker titles from the account type and pain signals.

    Returns:
    {
        "target_titles": [str],     # e.g. ["VP of Sales", "Head of Revenue"]
        "primary_search": str,      # Boolean string for Sales Navigator
        "backup_search": str,       # Broader fallback search
        "why_these_titles": str     # Reasoning
    }
    """

```

**Primary search string format:**

```
("VP of Sales" OR "Head of Sales" OR "Director of Sales") AND "{company name}"

```

---

## backend/agents/dossier_compiler.py

```python
async def run(
    account: dict,
    hypothesis: dict,
    news: dict,
    linkedin: dict,
    evaluation: dict,
    search_commands: dict
) -> dict:
    """
    Compiles all agent outputs into a final dossier.
    Calls Gemini to write the Pipedrive note.

    Returns:
    {
        "summary": str,             # 2-3 sentences, what we know about this account
        "key_insight": str,         # the single sharpest signal
        "pipedrive_note": str,      # formatted note for Pipedrive (plain text, ~150 words)
        "tags": [str]               # 2-3 short tags e.g. ["series-b", "hiring-sales"]
    }
    """

```

**Pipedrive note format (instruct Gemini to follow this):**

```
[AI Enrichment — Score: {score}/10]

WHY NOW: {key_insight}

NEWS: {headline}

HIRING SIGNALS: {top pain signal}

TALKING POINTS:
• {point 1}
• {point 2}

LINKEDIN TARGETS: {titles}
Primary: {primary_search}

```

---

## backend/queue_manager.py

This is the core orchestration loop. Called by the FastAPI route that starts a run.

```python
import asyncio

async def run_pipeline(run_id: int, accounts: list[dict], value_prop: str) -> None:
    """
    Main entry point. Runs in the background via asyncio.create_task().

    Algorithm:
    1. Mark run as 'running' in DB
    2. Split accounts into batches of settings.BATCH_SIZE
    3. For each batch: asyncio.gather(*[process_account(run_id, acc, value_prop)
                                        for acc in batch])
    4. After each batch: await update_run_counts(run_id)
    5. After all batches: mark run as 'completed'
    6. Handle CancelledError: mark run as 'cancelled'
    """

async def process_account(run_id: int, account: dict, value_prop: str) -> None:
    """
    Full pipeline for one account. All state is written to DB as it happens.
    Never raises — catches all exceptions and marks account as 'error'.

    Flow:
    1. Mark account 'running', log start
    2. Run hypothesiser → save to account.hypothesis_1
    3. Run news_scout + linkedin_analyst concurrently (asyncio.gather)
       → save to account.news, account.linkedin
    4. Run evaluator (pass 1) → save to account.eval_1
    5. If eval_1.relevant:
         → run linkedin_search_agent + dossier_compiler
         → run pipedrive_writer
         → mark account 'enriched'
         → return
    6. Log retry, run hypothesiser with previous_angle → save to account.hypothesis_2
    7. Run evaluator (pass 2) → save to account.eval_2
    8. If eval_2.relevant:
         → run linkedin_search_agent + dossier_compiler
         → run pipedrive_writer
         → mark account 'enriched'
         → return
    9. Log drop, mark account 'dropped'
    """

async def pipedrive_writer(account_id: int, account: dict,
                           dossier: dict, evaluation: dict,
                           search_commands: dict) -> None:
    """
    1. pipedrive.find_or_create_org(account['name'])
    2. pipedrive.add_note(org_id, dossier['pipedrive_note'])
    3. pipedrive.add_label(org_id, f"enriched-score-{evaluation['score']}")
    4. Save org_id and note_id to DB
    5. Log success
    """

```

---

## backend/main.py

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio

app = FastAPI()

# On startup: init_db()

# Background task registry: { run_id: asyncio.Task }
# Used to cancel runs

@app.get("/")
async def dashboard():
    return FileResponse("../frontend/index.html")

@app.post("/api/runs")
async def start_run(body: { "sheet_id": str, "value_prop": str }):
    """
    1. sheets.get_accounts(sheet_id)
    2. db.create_run(value_prop, sheet_id)
    3. db.insert_accounts(run_id, accounts)
    4. asyncio.create_task(queue_manager.run_pipeline(...))
    5. Return { run_id, total }
    """

@app.get("/api/runs/{run_id}")
async def get_run(run_id: int):
    # Returns run row + counts

@app.get("/api/runs/{run_id}/accounts")
async def get_run_accounts(run_id: int):
    # Returns all accounts with status + top-level fields
    # Does NOT return full JSON blobs — just: id, name, domain, status,
    # batch_number, score (from eval_1 or eval_2), updated_at

@app.get("/api/accounts/{account_id}")
async def get_account(account_id: int):
    # Returns full account row, all JSON fields parsed

@app.get("/api/accounts/{account_id}/logs")
async def get_account_logs(account_id: int):
    # Returns all log rows for this account ordered by created_at

@app.delete("/api/runs/{run_id}")
async def cancel_run(run_id: int):
    # Cancels the asyncio task, marks run 'cancelled'

@app.get("/api/sheets/preview")
async def preview_sheet(sheet_id: str):
    # Returns first 10 accounts from the sheet

```

---

## frontend/index.html

Single HTML file. No build step. No external JS frameworks. Use `fetch()` to poll the backend. Tailwind CDN for styling is allowed.

### Sections

**Header bar**

- App name
- Run status pill (idle / running / completed / cancelled)
- Batch progress: "Batch 2/20"
- Cancel button (visible when running)

**Setup panel** (shown when no run is active)

- Text input: Google Sheet ID
- Textarea: Value proposition
- Button: "Start pipeline"
- Button: "Preview sheet" → calls `/api/sheets/preview`, shows first 10 rows

**Progress bar**

- Shows percentage complete
- Below it: 5 count pills — Pending / Running / Enriched / Dropped / Error with appropriate colors (gray / blue / green / red / orange)

**Two-column layout**

Left column — account list:

- Each row: status icon (animated spinner if running) + company name + domain
  - score badge if available
- Click to select and show detail in right column
- Color-coded left border by status

Right column — account detail:

- Company name + status badge
- Tabs (JS-driven, not hidden at load): Log | Research | Evaluation | Pipedrive
- **Log tab**: chronological list of agent steps with icons and timestamps
- **Research tab**: hypothesis (with retry if applicable), news signals, LinkedIn signals
- **Evaluation tab**: score cards for pass 1 and pass 2, talking points, suggested angle
- **Pipedrive tab**: LinkedIn search commands (copyable code blocks), Pipedrive note preview, org ID if saved, tags

### Polling logic

```javascript
let pollInterval = null;

function startPolling(runId) {
    pollInterval = setInterval(async () => {
        const run = await fetch(`/api/runs/${runId}`).then(r => r.json());
        updateHeader(run);
        updateProgressBar(run);
        const accounts = await fetch(`/api/runs/${runId}/accounts`).then(r => r.json());
        updateAccountList(accounts);
        if (selectedAccountId) {
            const detail = await fetch(`/api/accounts/${selectedAccountId}`).then(r => r.json());
            const logs = await fetch(`/api/accounts/${selectedAccountId}/logs`).then(r => r.json());
            updateDetailPanel(detail, logs);
        }
        if (run.status === 'completed' || run.status === 'cancelled') {
            clearInterval(pollInterval);
        }
    }, 3000);
}

```

---

## Error handling rules

Apply these consistently across all files:

1. **Agent failures**: catch exception, log to DB with step='error', mark account status='error', increment run error count. Do not re-raise.
2. **Tavily failures**: if search returns non-200 or times out, return empty results list. Log a warning. Do not mark account as error — downstream agents handle missing data gracefully.
3. **Firecrawl failures**: return empty string on any failure. News scout handles empty scrape by working only from Tavily summaries.
4. **Gemini failures**: retry once after 2 seconds. If second attempt fails, raise so the caller (queue_manager) can catch and mark the account as error.
5. **Pipedrive failures**: log the error, mark pipedrive fields as null, but still mark account as 'enriched'. The enrichment data is saved in SQLite regardless of whether the Pipedrive write succeeded.
6. **Sheets read failure**: raise immediately with a clear message. Surface to the API caller so the user sees it before the run starts.

---

## Implementation order for Claude Code

Build in this exact order so each step is testable before the next:

1. `config.py` + `.env.example`
2. `db.py` — schema + all helper functions
3. `integrations/gemini.py` — test with a simple prompt
4. `integrations/tavily.py` — test with one search
5. `integrations/firecrawl.py` — test with one URL
6. `integrations/sheets.py` — test reading the sheet
7. `integrations/pipedrive.py` — test find_or_create_org
8. All 6 agent files — test each independently with mock data
9. `queue_manager.py` — wire agents together, test with 2 accounts
10. `main.py` — all routes
11. `frontend/index.html` — full dashboard
12. End-to-end test with 5 real accounts before running full 100

