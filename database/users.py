"""SQLite-backed user accounts for the trading terminal."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.security import hash_password, verify_password

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)


def create_user(email: str, name: str, password: str) -> Dict[str, Any]:
    init_db()
    clean_email = email.strip().lower()
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email=?", (clean_email,)).fetchone():
            raise ValueError("An account with this email already exists")
        cur = conn.execute(
            "INSERT INTO users (email,name,password_hash,created_at) VALUES (?,?,?,?)",
            (clean_email, name.strip() or clean_email.split("@")[0], hash_password(password),
             datetime.now().isoformat(timespec="seconds")),
        )
        row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


def authenticate(email: str, password: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if not row or not row["is_active"] or not verify_password(password, row["password_hash"]):
        return None
    return dict(row)


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def user_count() -> int:
    init_db()
    with _connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
