from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite

from config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "enrichment.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    value_prop  TEXT    NOT NULL,
    sheet_id    TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
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
    row_index       INTEGER,
    status          TEXT    NOT NULL DEFAULT 'pending',
    batch_number    INTEGER,
    hypothesis_1    TEXT,
    hypothesis_2    TEXT,
    news            TEXT,
    linkedin        TEXT,
    eval_1          TEXT,
    eval_2          TEXT,
    search_commands TEXT,
    dossier         TEXT,
    homepage        TEXT,
    outreach_angles TEXT,
    pipedrive_org_id  TEXT,
    pipedrive_note_id TEXT,
    error_message   TEXT,
    retry_count     INTEGER DEFAULT 0,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    step        TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_accounts_run_id ON accounts(run_id);
CREATE INDEX IF NOT EXISTS idx_logs_account_id ON logs(account_id, created_at);
"""


JSON_FIELDS = {
    "hypothesis_1",
    "hypothesis_2",
    "news",
    "linkedin",
    "eval_1",
    "eval_2",
    "search_commands",
    "dossier",
    "outreach_angles",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: aiosqlite.Row | None) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def _parse_json_fields(row: dict | None) -> dict | None:
    if row is None:
        return None
    for field in JSON_FIELDS:
        if field in row and row[field]:
            try:
                row[field] = json.loads(row[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return row


@asynccontextmanager
async def _connect():
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
    finally:
        await conn.close()


async def init_db() -> None:
    async with _connect() as conn:
        await conn.executescript(SCHEMA)
        cur = await conn.execute("PRAGMA table_info(accounts)")
        cols = {row["name"] for row in await cur.fetchall()}
        if "homepage" not in cols:
            await conn.execute("ALTER TABLE accounts ADD COLUMN homepage TEXT")
        if "outreach_angles" not in cols:
            await conn.execute(
                "ALTER TABLE accounts ADD COLUMN outreach_angles TEXT"
            )
        await conn.commit()


async def create_run(value_prop: str, sheet_id: str) -> int:
    async with _connect() as conn:
        cur = await conn.execute(
            "INSERT INTO runs (created_at, value_prop, sheet_id, status) "
            "VALUES (?, ?, ?, 'pending')",
            (_now(), value_prop, sheet_id),
        )
        await conn.commit()
        return cur.lastrowid


async def insert_accounts(run_id: int, accounts: list[dict]) -> list[int]:
    if not accounts:
        return []
    batch_size_default = 5
    ids: list[int] = []
    async with _connect() as conn:
        for idx, acc in enumerate(accounts):
            batch_number = (idx // batch_size_default) + 1
            cur = await conn.execute(
                "INSERT INTO accounts (run_id, name, domain, row_index, status, "
                "batch_number, updated_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (
                    run_id,
                    acc.get("name"),
                    acc.get("domain"),
                    acc.get("row_index"),
                    batch_number,
                    _now(),
                ),
            )
            ids.append(cur.lastrowid)
        await conn.execute(
            "UPDATE runs SET total = ? WHERE id = ?", (len(accounts), run_id)
        )
        await conn.commit()
    return ids


async def get_run(run_id: int) -> dict | None:
    async with _connect() as conn:
        cur = await conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = await cur.fetchone()
        return _row_to_dict(row)


async def get_run_accounts(run_id: int) -> list[dict]:
    async with _connect() as conn:
        cur = await conn.execute(
            "SELECT * FROM accounts WHERE run_id = ? ORDER BY id", (run_id,)
        )
        rows = await cur.fetchall()
        return [_parse_json_fields(_row_to_dict(r)) for r in rows]


async def get_account(account_id: int) -> dict | None:
    async with _connect() as conn:
        cur = await conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        )
        row = await cur.fetchone()
        return _parse_json_fields(_row_to_dict(row))


async def get_account_logs(account_id: int) -> list[dict]:
    async with _connect() as conn:
        cur = await conn.execute(
            "SELECT * FROM logs WHERE account_id = ? ORDER BY created_at, id",
            (account_id,),
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]


async def update_account(account_id: int, **fields) -> None:
    if not fields:
        return
    serialised: dict = {}
    for k, v in fields.items():
        if k in JSON_FIELDS and v is not None and not isinstance(v, str):
            serialised[k] = json.dumps(v)
        else:
            serialised[k] = v
    serialised["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in serialised)
    values = list(serialised.values()) + [account_id]
    async with _connect() as conn:
        await conn.execute(
            f"UPDATE accounts SET {cols} WHERE id = ?", values
        )
        await conn.commit()


async def update_run_counts(run_id: int) -> None:
    async with _connect() as conn:
        cur = await conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN status IN ('enriched','dropped','error') THEN 1 ELSE 0 END) AS done, "
            "  SUM(CASE WHEN status = 'enriched' THEN 1 ELSE 0 END) AS enriched, "
            "  SUM(CASE WHEN status = 'dropped' THEN 1 ELSE 0 END) AS dropped, "
            "  SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors "
            "FROM accounts WHERE run_id = ?",
            (run_id,),
        )
        row = await cur.fetchone()
        await conn.execute(
            "UPDATE runs SET done = ?, enriched = ?, dropped = ?, errors = ? "
            "WHERE id = ?",
            (
                row["done"] or 0,
                row["enriched"] or 0,
                row["dropped"] or 0,
                row["errors"] or 0,
                run_id,
            ),
        )
        await conn.commit()


async def update_run_status(run_id: int, status: str) -> None:
    async with _connect() as conn:
        await conn.execute(
            "UPDATE runs SET status = ? WHERE id = ?", (status, run_id)
        )
        await conn.commit()


async def add_log(account_id: int, step: str, message: str) -> None:
    async with _connect() as conn:
        await conn.execute(
            "INSERT INTO logs (account_id, step, message, created_at) "
            "VALUES (?, ?, ?, ?)",
            (account_id, step, message, _now()),
        )
        await conn.commit()
