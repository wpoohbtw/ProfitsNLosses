from __future__ import annotations

import os
import json
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

DEFAULT_GOOGLE_CREDENTIALS_PATH = BACKEND_DIR / "google-service-account.json"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SITUATION_COLUMNS = 4
SETTINGS_ENV_KEYS = {
    "credentialsPath": "GOOGLE_SHEETS_CREDENTIALS_PATH",
    "spreadsheetId": "GOOGLE_SHEETS_SPREADSHEET_ID",
    "sheetName": "GOOGLE_SHEETS_SITUATIONS_SHEET",
}


class SituationsConfigError(RuntimeError):
    pass


def get_spreadsheet_id() -> str:
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    if not spreadsheet_id:
        raise SituationsConfigError("GOOGLE_SHEETS_SPREADSHEET_ID is not configured")
    return spreadsheet_id


def get_situations_sheet_name() -> str:
    return os.getenv("GOOGLE_SHEETS_SITUATIONS_SHEET", "Situations")


def get_google_credentials_path() -> Path:
    return Path(os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", str(DEFAULT_GOOGLE_CREDENTIALS_PATH)))


def get_sheets_service():
    credentials_path = resolve_credentials_path(get_google_credentials_path())
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
    return f"{get_situations_sheet_name()}!A:D"


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
            range=f"{get_situations_sheet_name()}!A{row_number}:D{row_number}",
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
        if properties.get("title") == get_situations_sheet_name():
            return int(properties["sheetId"])
    raise SituationsConfigError(f"Google sheet not found: {get_situations_sheet_name()}")


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


def read_service_account_email(credentials_path: Path) -> str:
    if not credentials_path.exists():
        return ""
    try:
        payload = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    email = payload.get("client_email", "")
    return str(email) if email else ""


def get_situations_settings() -> dict[str, object]:
    credentials_path = resolve_credentials_path(get_google_credentials_path())
    return {
        "credentialsPath": str(get_google_credentials_path()),
        "resolvedCredentialsPath": str(credentials_path),
        "credentialsExists": credentials_path.exists(),
        "serviceAccountEmail": read_service_account_email(credentials_path),
        "spreadsheetId": os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", ""),
        "sheetName": get_situations_sheet_name(),
    }


def update_situations_settings(credentials_path: str, spreadsheet_id: str, sheet_name: str) -> dict[str, object]:
    next_values = {
        "GOOGLE_SHEETS_CREDENTIALS_PATH": credentials_path.strip() or str(DEFAULT_GOOGLE_CREDENTIALS_PATH.relative_to(PROJECT_DIR)),
        "GOOGLE_SHEETS_SPREADSHEET_ID": spreadsheet_id.strip(),
        "GOOGLE_SHEETS_SITUATIONS_SHEET": sheet_name.strip() or "Situations",
    }
    write_env_values(PROJECT_DIR / ".env", next_values)
    os.environ.update(next_values)
    get_situations_sheet_id.cache_clear()
    return get_situations_settings()


def write_env_values(env_path: Path, values: dict[str, str]) -> None:
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen_keys: set[str] = set()
    next_lines: list[str] = []

    for raw_line in existing_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            next_lines.append(raw_line)
            continue

        key = stripped.split("=", 1)[0].strip()
        if key in values:
            next_lines.append(f"{key}={values[key]}")
            seen_keys.add(key)
        else:
            next_lines.append(raw_line)

    for key, value in values.items():
        if key not in seen_keys:
            next_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def test_situations_connection() -> dict[str, object]:
    settings = get_situations_settings()
    checks = []

    checks.append({"key": "credentials", "label": "JSON файл", "ok": bool(settings["credentialsExists"])})
    checks.append({"key": "spreadsheet", "label": "Google Sheet ID", "ok": bool(settings["spreadsheetId"])})
    checks.append({"key": "sheet", "label": "Вкладка", "ok": False})
    checks.append({"key": "write", "label": "Доступ Google Sheets", "ok": False})

    if not settings["credentialsExists"] or not settings["spreadsheetId"]:
        return {"status": "error", "settings": settings, "checks": checks}

    try:
        result = (
            get_sheets_service()
            .spreadsheets()
            .get(
                spreadsheetId=get_spreadsheet_id(),
                fields="sheets(properties(title))",
            )
            .execute()
        )
        sheet_titles = [sheet.get("properties", {}).get("title") for sheet in result.get("sheets", [])]
        sheet_ok = get_situations_sheet_name() in sheet_titles
        checks[2] = {"key": "sheet", "label": "Вкладка", "ok": sheet_ok}
        checks[3] = {"key": "write", "label": "Доступ Google Sheets", "ok": True}
        return {"status": "ok" if sheet_ok else "error", "settings": get_situations_settings(), "checks": checks}
    except Exception as caught_error:
        return {
            "status": "error",
            "settings": get_situations_settings(),
            "checks": checks,
            "message": str(caught_error),
        }
