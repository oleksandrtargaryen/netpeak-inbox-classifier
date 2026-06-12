"""Optional: write the results into a Google Sheet.

Only runs if GOOGLE_SHEETS_CREDENTIALS (path to a service-account json) and
GOOGLE_SHEET_ID are set. Imports gspread lazily so the core pipeline works even
when these libs aren't installed.
"""

import os

from ..models import ClassifiedRequest

HEADER = [
    "id",
    "channel",
    "timestamp",
    "category",
    "target_department",
    "priority",
    "short_summary",
    "requested_actions",
    "needs_clarification",
    "clarification_questions",
    "confidence",
    "parse_error",
]


def _row(r: ClassifiedRequest) -> list:
    return [
        r.id,
        r.channel,
        r.timestamp,
        r.category.value,
        r.target_department or "",
        r.priority.value,
        r.short_summary,
        "; ".join(r.requested_actions),
        r.needs_clarification,
        "; ".join(r.clarification_questions),
        r.confidence,
        r.parse_error,
    ]


def write_results(results: list[ClassifiedRequest]) -> bool:
    creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not creds_path or not sheet_id:
        print("[sheets] skipped: GOOGLE_SHEETS_CREDENTIALS / GOOGLE_SHEET_ID not set")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("[sheets] skipped: gspread / google-auth not installed")
        return False

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(creds)

    sheet = client.open_by_key(sheet_id).sheet1
    sheet.clear()
    sheet.update([HEADER] + [_row(r) for r in results])
    print(f"[sheets] wrote {len(results)} rows")
    return True
