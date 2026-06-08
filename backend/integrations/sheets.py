from __future__ import annotations

from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from config import PROJECT_ROOT, settings

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _resolve_credentials_path() -> Path:
    path = Path(settings.google_service_account_json)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _client() -> gspread.Client:
    creds_path = _resolve_credentials_path()
    if not creds_path.exists():
        raise ValueError(
            f"Google service account JSON not found at {creds_path}. "
            "Set GOOGLE_SERVICE_ACCOUNT_JSON in .env."
        )
    creds = Credentials.from_service_account_file(str(creds_path), scopes=_SCOPES)
    return gspread.authorize(creds)


def get_accounts(sheet_id: str) -> list[dict]:
    """Read first worksheet, return [{name, domain, row_index}].

    Headers matched case-insensitively. Raises ValueError with a clear
    message if 'Name' is missing or the sheet cannot be opened.
    """
    try:
        sh = _client().open_by_key(sheet_id)
    except gspread.exceptions.SpreadsheetNotFound as e:
        raise ValueError(
            f"Sheet {sheet_id} not found or not shared with service account "
            "(agent-671@gen-lang-client-0926323904.iam.gserviceaccount.com). "
            "Open the sheet → Share → add that email as Viewer."
        ) from e
    except gspread.exceptions.APIError as e:
        raise ValueError(
            f"Google API error opening sheet {sheet_id}: "
            f"{getattr(e, 'response', None) and e.response.text or repr(e)}"
        ) from e
    except Exception as e:
        raise ValueError(
            f"Could not open Google Sheet {sheet_id}: {type(e).__name__}: {e!r}"
        ) from e
    ws = sh.get_worksheet(0)
    rows = ws.get_all_values()
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    try:
        name_idx = header.index("name")
    except ValueError as e:
        raise ValueError(
            "Sheet is missing required 'Name' column in the first row."
        ) from e
    domain_idx = header.index("domain") if "domain" in header else None

    accounts: list[dict] = []
    for offset, row in enumerate(rows[1:], start=2):
        name = row[name_idx].strip() if name_idx < len(row) else ""
        if not name:
            continue
        domain = ""
        if domain_idx is not None and domain_idx < len(row):
            domain = row[domain_idx].strip()
        accounts.append({"name": name, "domain": domain, "row_index": offset})
    return accounts
