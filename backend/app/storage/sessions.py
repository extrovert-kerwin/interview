"""User, auth, session, event, and report storage."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import pbkdf2_hmac
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "interview.db"
DATABASE_URL = os.getenv("DATABASE_URL", "")
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _placeholder() -> str:
    return "%s" if IS_POSTGRES else "?"


def _q(sql: str) -> str:
    return sql.replace("?", _placeholder())


@contextmanager
def _connect() -> Iterator[Any]:
    if IS_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
            yield conn
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_get(row: Any, key: str) -> Any:
    return row[key]


def _ensure_column(conn: Any, table: str, column: str, column_type: str) -> None:
    if IS_POSTGRES:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}")
        return
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if column not in {_row_get(row, "name") for row in rows}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def _verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, salt, _digest = stored.split("$", 2)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    return secrets.compare_digest(_hash_password(password, salt), stored)


def init_db() -> None:
    with _LOCK, _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT,
                password_hash TEXT,
                display_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        _ensure_column(conn, "users", "email", "TEXT")
        _ensure_column(conn, "users", "password_hash", "TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        if IS_POSTGRES:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_events (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def ensure_user(user_id: str | None = None, display_name: str | None = None) -> dict[str, str]:
    init_db()
    uid = user_id or uuid.uuid4().hex[:12]
    now = _now()
    with _LOCK, _connect() as conn:
        row = conn.execute(_q("SELECT id, display_name FROM users WHERE id = ?"), (uid,)).fetchone()
        if not row:
            name = display_name or "访客"
            conn.execute(
                _q("INSERT INTO users (id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)"),
                (uid, name, now, now),
            )
            return {"id": uid, "display_name": name}
        if display_name and display_name != _row_get(row, "display_name"):
            conn.execute(
                _q("UPDATE users SET display_name = ?, updated_at = ? WHERE id = ?"),
                (display_name, now, uid),
            )
            return {"id": uid, "display_name": display_name}
        return {"id": _row_get(row, "id"), "display_name": _row_get(row, "display_name") or "访客"}


def create_user(email: str, password: str, display_name: str | None = None) -> dict[str, str]:
    init_db()
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("邮箱不能为空")
    if len(password) < 6:
        raise ValueError("密码至少需要 6 位")
    now = _now()
    uid = uuid.uuid4().hex[:12]
    name = display_name or normalized.split("@")[0]
    with _LOCK, _connect() as conn:
        exists = conn.execute(_q("SELECT 1 FROM users WHERE email = ?"), (normalized,)).fetchone()
        if exists:
            raise ValueError("邮箱已注册")
        conn.execute(
            _q("INSERT INTO users (id, email, password_hash, display_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)"),
            (uid, normalized, _hash_password(password), name, now, now),
        )
    return {"id": uid, "email": normalized, "display_name": name}


def authenticate_user(email: str, password: str) -> dict[str, str] | None:
    init_db()
    normalized = email.strip().lower()
    with _LOCK, _connect() as conn:
        row = conn.execute(
            _q("SELECT id, email, password_hash, display_name FROM users WHERE email = ?"),
            (normalized,),
        ).fetchone()
        if not row or not _verify_password(password, _row_get(row, "password_hash")):
            return None
        return {
            "id": _row_get(row, "id"),
            "email": _row_get(row, "email"),
            "display_name": _row_get(row, "display_name") or "用户",
        }


def create_token(user_id: str) -> str:
    init_db()
    token = secrets.token_urlsafe(32)
    with _LOCK, _connect() as conn:
        conn.execute(
            _q("INSERT INTO auth_tokens (token, user_id, created_at) VALUES (?, ?, ?)"),
            (token, user_id, _now()),
        )
    return token


def get_user_by_token(token: str) -> dict[str, str] | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(
            _q("""
                SELECT u.id, u.email, u.display_name
                FROM auth_tokens t
                JOIN users u ON u.id = t.user_id
                WHERE t.token = ?
            """),
            (token,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": _row_get(row, "id"),
            "email": _row_get(row, "email"),
            "display_name": _row_get(row, "display_name") or "用户",
        }


def delete_token(token: str) -> None:
    init_db()
    with _LOCK, _connect() as conn:
        conn.execute(_q("DELETE FROM auth_tokens WHERE token = ?"), (token,))


def save(session_id: str, state: dict[str, Any], event_type: str = "state_saved") -> None:
    init_db()
    now = _now()
    state = dict(state)
    state.setdefault("session_id", session_id)
    user_id = state.get("user_id")
    payload = json.dumps(state, ensure_ascii=False)
    with _LOCK, _connect() as conn:
        exists = conn.execute(_q("SELECT 1 FROM sessions WHERE id = ?"), (session_id,)).fetchone()
        if exists:
            conn.execute(
                _q("UPDATE sessions SET user_id = ?, state_json = ?, updated_at = ? WHERE id = ?"),
                (user_id, payload, now, session_id),
            )
        else:
            conn.execute(
                _q("INSERT INTO sessions (id, user_id, state_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"),
                (session_id, user_id, payload, now, now),
            )
        conn.execute(
            _q("INSERT INTO session_events (session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)"),
            (session_id, event_type, payload, now),
        )


def get(session_id: str) -> dict[str, Any] | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(_q("SELECT state_json FROM sessions WHERE id = ?"), (session_id,)).fetchone()
        if not row:
            return None
        return json.loads(_row_get(row, "state_json"))


def update(session_id: str, patch: dict[str, Any], event_type: str = "state_updated") -> dict[str, Any]:
    existing = get(session_id) or {"session_id": session_id}
    existing.update(patch)
    save(session_id, existing, event_type=event_type)
    return existing


def record_event(session_id: str, event_type: str, payload: dict[str, Any]) -> None:
    init_db()
    with _LOCK, _connect() as conn:
        conn.execute(
            _q("INSERT INTO session_events (session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)"),
            (session_id, event_type, json.dumps(payload, ensure_ascii=False), _now()),
        )


def save_report(session_id: str, user_id: str | None, report: dict[str, Any]) -> None:
    init_db()
    now = _now()
    payload = json.dumps(report, ensure_ascii=False)
    with _LOCK, _connect() as conn:
        exists = conn.execute(_q("SELECT 1 FROM reports WHERE session_id = ?"), (session_id,)).fetchone()
        if exists:
            conn.execute(
                _q("UPDATE reports SET user_id = ?, report_json = ?, updated_at = ? WHERE session_id = ?"),
                (user_id, payload, now, session_id),
            )
        else:
            conn.execute(
                _q("INSERT INTO reports (session_id, user_id, report_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"),
                (session_id, user_id, payload, now, now),
            )
        conn.execute(
            _q("INSERT INTO session_events (session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)"),
            (session_id, "report_persisted", payload, now),
        )


def get_report(session_id: str) -> dict[str, Any] | None:
    init_db()
    with _LOCK, _connect() as conn:
        row = conn.execute(_q("SELECT report_json FROM reports WHERE session_id = ?"), (session_id,)).fetchone()
        if not row:
            return None
        return json.loads(_row_get(row, "report_json"))


def all_ids() -> list[str]:
    init_db()
    with _LOCK, _connect() as conn:
        rows = conn.execute("SELECT id FROM sessions ORDER BY updated_at DESC").fetchall()
        return [_row_get(row, "id") for row in rows]


def list_user_sessions(user_id: str) -> list[dict[str, Any]]:
    init_db()
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            _q("SELECT id, state_json, created_at, updated_at FROM sessions WHERE user_id = ? ORDER BY updated_at DESC"),
            (user_id,),
        ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        state = json.loads(_row_get(row, "state_json"))
        report = state.get("final_report") or {}
        profile = state.get("resume_profile") or {}
        records.append({
            "session_id": _row_get(row, "id"),
            "position": state.get("position", ""),
            "stage": state.get("stage", ""),
            "candidate": profile.get("name") or profile.get("current_title") or "候选人",
            "score": report.get("overall_score"),
            "recommendation": report.get("recommendation"),
            "created_at": _row_get(row, "created_at"),
            "updated_at": _row_get(row, "updated_at"),
            "report_ready": bool(report),
        })
    return records
