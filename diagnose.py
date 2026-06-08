"""Run from project root: .venv/bin/python diagnose.py"""
import os
import sys
import traceback
from pathlib import Path

print("=== diagnose ===")
print("cwd:", os.getcwd())
print("python:", sys.executable)

p = Path("service-account.json")
print("\nstep 1: file exists?", p.exists(), "abs=", p.resolve())
print("       readable?", os.access(p, os.R_OK))

print("\nstep 2: raw open()")
try:
    with open(p) as f:
        data = f.read()
    print("       OK,", len(data), "bytes")
except Exception as e:
    print("       FAIL:", type(e).__name__, repr(e))
    traceback.print_exc()
    sys.exit(1)

print("\nstep 3: google-auth Credentials.from_service_account_file")
try:
    from google.oauth2.service_account import Credentials
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(str(p), scopes=SCOPES)
    print("       OK, service account email:", creds.service_account_email)
except Exception as e:
    print("       FAIL:", type(e).__name__, repr(e))
    traceback.print_exc()
    sys.exit(1)

print("\nstep 4: gspread.authorize + open_by_key")
SHEET_ID = "1M7yzznL6_kZTrlaV55htqReVYdkhS5QP5WOV1Feim9Q"
try:
    import gspread
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    print("       OK, sheet title:", sh.title)
    ws = sh.get_worksheet(0)
    print("       first worksheet:", ws.title, "rows:", ws.row_count)
    print("       header row:", ws.row_values(1))
except Exception as e:
    print("       FAIL:", type(e).__name__, repr(e))
    traceback.print_exc()
    sys.exit(1)

print("\nAll steps passed.")
