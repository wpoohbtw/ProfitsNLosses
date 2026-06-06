from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import Header, HTTPException, status

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_PORTAL_DB_PATH = PROJECT_DIR.parent / "SoftPortal" / "backend" / "data" / "portal.db"
DEFAULT_PORTAL_USERNAME = "wpoohbtw"


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


def get_portal_db_path() -> Path:
    raw_path = os.getenv("PNL_PORTAL_DB_PATH", str(DEFAULT_PORTAL_DB_PATH))
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


def get_default_portal_username() -> str:
    username = os.getenv("PNL_DEV_USERNAME") or os.getenv("PNL_DEFAULT_USERNAME") or DEFAULT_PORTAL_USERNAME
    return username.strip() or DEFAULT_PORTAL_USERNAME


def find_portal_user_id(username: str | None = None) -> int:
    target_username = username or get_default_portal_username()
    portal_db_path = get_portal_db_path()
    if not portal_db_path.exists():
        raise RuntimeError(f"Portal database not found: {portal_db_path}")

    with sqlite3.connect(portal_db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id FROM users WHERE username = ? AND is_active = 1",
            (target_username,),
        ).fetchone()

    if row is None:
        raise RuntimeError(f"Portal user not found: {target_username}")
    return int(row["id"])


def get_default_portal_user_id() -> int:
    raw_user_id = os.getenv("PNL_DEV_USER_ID", "").strip()
    if raw_user_id:
        return int(raw_user_id)
    return find_portal_user_id()


def get_current_portal_user(
    x_portal_user_id: str | None = Header(default=None, alias="X-Portal-User-Id"),
    x_portal_username: str | None = Header(default=None, alias="X-Portal-Username"),
) -> dict[str, object]:
    if x_portal_user_id:
        try:
            user_id = int(x_portal_user_id)
        except ValueError as caught_error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal user") from caught_error
        return {"userId": user_id, "username": x_portal_username or ""}

    try:
        return {
            "userId": get_default_portal_user_id(),
            "username": get_default_portal_username(),
        }
    except RuntimeError as caught_error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(caught_error)) from caught_error
