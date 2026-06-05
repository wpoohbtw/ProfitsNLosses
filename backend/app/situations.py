from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


def load_local_env() -> None:
    for env_path in (PROJECT_DIR / ".env", BACKEND_DIR / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
SITUATIONS_SHEET_NAME = os.getenv("GOOGLE_SHEETS_SITUATIONS_SHEET", "Situations")
DEFAULT_GOOGLE_CREDENTIALS_PATH = BACKEND_DIR / "google-service-account.json"
GOOGLE_CREDENTIALS_PATH = Path(os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", str(DEFAULT_GOOGLE_CREDENTIALS_PATH)))
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SITUATION_COLUMNS = 4


class SituationsConfigError(RuntimeError):
    pass


def get_spreadsheet_id() -> str:
    if not SPREADSHEET_ID:
        raise SituationsConfigError("GOOGLE_SHEETS_SPREADSHEET_ID is not configured")
    return SPREADSHEET_ID


def get_sheets_service():
    credentials_path = resolve_credentials_path(GOOGLE_CREDENTIALS_PATH)
    if not credentials_path.exists():
        raise SituationsConfigError(f"Google credentials file not found: {credentials_path}")

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SHEETS_SCOPES,
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def resolve_credentials_path(path: Path) -> Path:
    if path.is_absolute():
        return path

    candidates = (
        Path.cwd() / path,
        BACKEND_DIR / path,
        PROJECT_DIR / path,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate

    return DEFAULT_GOOGLE_CREDENTIALS_PATH


def get_situations_range() -> str:
    return f"{SITUATIONS_SHEET_NAME}!A:D"


def normalize_situation_row(row_number: int, row: list[str]) -> dict[str, object]:
    padded_row = [*row, *[""] * SITUATION_COLUMNS][:SITUATION_COLUMNS]
    return {
        "rowNumber": row_number,
        "date": padded_row[0],
        "token": padded_row[1],
        "description": padded_row[2],
        "posts": padded_row[3],
    }


def list_situations() -> list[dict[str, object]]:
    result = (
        get_sheets_service()
        .spreadsheets()
        .values()
        .get(
            spreadsheetId=get_spreadsheet_id(),
            range=get_situations_range(),
            majorDimension="ROWS",
        )
        .execute()
    )
    rows = result.get("values", [])
    return [
        normalize_situation_row(index, row)
        for index, row in enumerate(rows[1:], start=2)
        if any(str(cell).strip() for cell in row)
    ]


def append_situation(date_value: str, token: str, description: str, posts: str) -> dict[str, object]:
    row = [date_value, token, description, posts]
    result = (
        get_sheets_service()
        .spreadsheets()
        .values()
        .append(
            spreadsheetId=get_spreadsheet_id(),
            range=get_situations_range(),
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        )
        .execute()
    )
    return {
        "status": "created",
        "updatedRange": result.get("updates", {}).get("updatedRange"),
    }


def update_situation(row_number: int, date_value: str, token: str, description: str, posts: str) -> dict[str, object]:
    if row_number < 2:
        raise SituationsConfigError("Situation row number must point to a data row")

    row = [date_value, token, description, posts]
    result = (
        get_sheets_service()
        .spreadsheets()
        .values()
        .update(
            spreadsheetId=get_spreadsheet_id(),
            range=f"{SITUATIONS_SHEET_NAME}!A{row_number}:D{row_number}",
            valueInputOption="USER_ENTERED",
            body={"values": [row]},
        )
        .execute()
    )
    return {
        "status": "saved",
        "updatedRange": result.get("updatedRange"),
    }


@lru_cache(maxsize=1)
def get_situations_sheet_id() -> int:
    result = (
        get_sheets_service()
        .spreadsheets()
        .get(
            spreadsheetId=get_spreadsheet_id(),
            fields="sheets(properties(sheetId,title))",
        )
        .execute()
    )
    for sheet in result.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == SITUATIONS_SHEET_NAME:
            return int(properties["sheetId"])
    raise SituationsConfigError(f"Google sheet not found: {SITUATIONS_SHEET_NAME}")


def delete_situation(row_number: int) -> dict[str, object]:
    if row_number < 2:
        raise SituationsConfigError("Situation row number must point to a data row")

    sheet_id = get_situations_sheet_id()
    get_sheets_service().spreadsheets().batchUpdate(
        spreadsheetId=get_spreadsheet_id(),
        body={
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row_number - 1,
                            "endIndex": row_number,
                        }
                    }
                }
            ]
        },
    ).execute()
    return {"status": "deleted"}
