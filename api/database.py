import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


DATABASE_PATH = Path(
    os.environ.get("INTRO_API_DATABASE", Path(__file__).with_name("introductions.sqlite3"))
)


def get_base_site_url(json_url: str, username: str) -> str:
    parsed_url = urlsplit(json_url)
    path_parts = [part for part in parsed_url.path.split("/") if part]
    base_path = "/" if parsed_url.hostname == "127.0.0.1" and len(path_parts) == 1 else f"/{username}/"
    return urlunsplit((parsed_url.scheme, parsed_url.netloc, base_path, "", ""))


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def initialize_database() -> None:
    connection = get_connection()
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS introductions (
                username TEXT PRIMARY KEY,
                json_url TEXT NOT NULL,
                content_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def upsert_introduction(username: str, json_url: str, data: dict) -> tuple[str, bool]:
    updated_at = datetime.now(timezone.utc).isoformat()
    content_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    connection = get_connection()
    try:
        exists = connection.execute(
            "SELECT 1 FROM introductions WHERE username = ?", (username,)
        ).fetchone() is not None
        connection.execute(
            """
            INSERT INTO introductions (username, json_url, content_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                json_url = excluded.json_url,
                content_json = excluded.content_json,
                updated_at = excluded.updated_at
            """,
            (username, json_url, content_json, updated_at),
        )
        connection.commit()
        return updated_at, not exists
    finally:
        connection.close()


def get_all_introductions() -> dict:
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT username, json_url, content_json, updated_at FROM introductions ORDER BY username"
        ).fetchall()
        introductions = {}
        for row in rows:
            introductions[row["username"]] = {
                "lastUpdated": row["updated_at"],
                "jsonUrl": row["json_url"],
                "baseSiteUrl": get_base_site_url(row["json_url"], row["username"]),
                "introductionData": json.loads(row["content_json"]),
            }
        return introductions
    finally:
        connection.close()
