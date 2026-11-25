"""Profile, preferences, sessions, notifications, and account activity storage."""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.users import DB_PATH, _connect, init_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def init_profile_db() -> None:
    init_db()
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                mobile TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
                bio TEXT NOT NULL DEFAULT '',
                email_verified INTEGER NOT NULL DEFAULT 0,
                membership_plan TEXT NOT NULL DEFAULT 'Free',
                membership_status TEXT NOT NULL DEFAULT 'Active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                trading_json TEXT NOT NULL DEFAULT '{}',
                ai_json TEXT NOT NULL DEFAULT '{}',
                app_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_notifications (
                user_id INTEGER PRIMARY KEY,
                prefs_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT NOT NULL UNIQUE,
                device TEXT NOT NULL DEFAULT '',
                ip_address TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                revoked_at TEXT,
                is_current INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                label TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                ip_address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connected_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                service_type TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'disconnected',
                config_json TEXT NOT NULL DEFAULT '{}',
                secret_hint TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        # lightweight migrations for existing DBs
        for stmt in [
            "ALTER TABLE users ADD COLUMN updated_at TEXT",
            "ALTER TABLE users ADD COLUMN deactivated_at TEXT",
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass


def _default_trading() -> Dict[str, Any]:
    return {
        "preferred_exchange": "NSE",
        "preferred_segments": ["Equity"],
        "default_watchlist": ["RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY"],
        "favorite_stocks": [],
        "default_chart_timeframe": "5m",
        "preferred_indicators": ["EMA", "RSI", "MACD"],
        "dashboard_layout": "comfortable",
        "default_landing_page": "overview",
    }


def _default_ai() -> Dict[str, Any]:
    return {
        "analysis_style": "balanced",
        "preferred_indicators": ["EMA", "RSI", "MACD"],
        "ema_fast": 20,
        "ema_slow": 50,
        "rsi_period": 14,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "candlestick_patterns": ["Engulfing", "Doji", "Hammer"],
        "insight_depth": "standard",
        "signal_notifications": True,
        "show_model_info": True,
    }


def _default_app() -> Dict[str, Any]:
    return {
        "theme": "dark",
        "language": "en",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "date_format": "DD MMM YYYY",
        "dashboard_density": "comfortable",
        "accessibility": {"reduced_motion": False, "high_contrast": False, "large_text": False},
    }


def _default_notifications() -> Dict[str, Any]:
    return {
        "email_notifications": True,
        "browser_push": False,
        "price_alerts": True,
        "ai_signal_notifications": True,
        "market_news_notifications": False,
        "watchlist_notifications": True,
        "security_alerts": True,
        "risk_notifications": True,
    }


def ensure_profile(user_id: int, email: str = "", name: str = "") -> Dict[str, Any]:
    init_profile_db()
    now = _now()
    username_base = (email.split("@")[0] if email else f"user{user_id}").lower().replace(".", "_")
    with _connect() as conn:
        row = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            conn.execute(
                """INSERT INTO user_profiles
                   (user_id, username, created_at, updated_at) VALUES (?,?,?,?)""",
                (user_id, username_base, now, now),
            )
        conn.execute(
            "INSERT OR IGNORE INTO user_preferences (user_id, trading_json, ai_json, app_json, updated_at) VALUES (?,?,?,?,?)",
            (user_id, json.dumps(_default_trading()), json.dumps(_default_ai()), json.dumps(_default_app()), now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO user_notifications (user_id, prefs_json, updated_at) VALUES (?,?,?)",
            (user_id, json.dumps(_default_notifications()), now),
        )
    return get_profile(user_id)


def get_profile(user_id: int) -> Dict[str, Any]:
    init_profile_db()
    with _connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            return {}
        ensure_profile_row = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
        if not ensure_profile_row:
            ensure_profile(user_id, user["email"], user["name"])
            ensure_profile_row = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
        prefs = conn.execute("SELECT * FROM user_preferences WHERE user_id=?", (user_id,)).fetchone()
        notifs = conn.execute("SELECT * FROM user_notifications WHERE user_id=?", (user_id,)).fetchone()
    user_d = dict(user)
    prof = dict(ensure_profile_row) if ensure_profile_row else {}
    return {
        "id": user_d["id"],
        "email": user_d["email"],
        "name": user_d["name"],
        "username": prof.get("username") or user_d["email"].split("@")[0],
        "avatar_url": prof.get("avatar_url", ""),
        "mobile": prof.get("mobile", ""),
        "country": prof.get("country", ""),
        "timezone": prof.get("timezone") or "Asia/Kolkata",
        "bio": prof.get("bio", ""),
        "email_verified": bool(prof.get("email_verified", 0)),
        "membership_plan": prof.get("membership_plan") or "Free",
        "membership_status": prof.get("membership_status") or "Active",
        "created_at": user_d.get("created_at"),
        "updated_at": prof.get("updated_at") or user_d.get("updated_at") or user_d.get("created_at"),
        "is_active": bool(user_d.get("is_active", 1)),
        "deactivated_at": user_d.get("deactivated_at"),
        "preferences": {
            "trading": _json(prefs["trading_json"] if prefs else None, _default_trading()),
            "ai": _json(prefs["ai_json"] if prefs else None, _default_ai()),
            "app": _json(prefs["app_json"] if prefs else None, _default_app()),
        },
        "notifications": _json(notifs["prefs_json"] if notifs else None, _default_notifications()),
    }


def update_profile(user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    init_profile_db()
    now = _now()
    allowed_profile = {"username", "avatar_url", "mobile", "country", "timezone", "bio"}
    allowed_user = {"name", "email"}
    with _connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise ValueError("Account not found")
        if "email" in payload:
            email = str(payload["email"]).strip().lower()
            if not email or "@" not in email:
                raise ValueError("Valid email is required")
            exists = conn.execute("SELECT 1 FROM users WHERE email=? AND id!=?", (email, user_id)).fetchone()
            if exists:
                raise ValueError("Email is already in use")
            conn.execute("UPDATE users SET email=?, updated_at=? WHERE id=?", (email, now, user_id))
        if "name" in payload:
            name = str(payload["name"]).strip()
            if not name:
                raise ValueError("Name is required")
            conn.execute("UPDATE users SET name=?, updated_at=? WHERE id=?", (name[:80], now, user_id))
        ensure_profile(user_id, dict(user)["email"], dict(user)["name"])
        updates = {k: str(payload.get(k, "")).strip() for k in allowed_profile if k in payload}
        if "username" in updates:
            uname = updates["username"].lower().replace(" ", "_")
            if len(uname) < 3:
                raise ValueError("Username must be at least 3 characters")
            updates["username"] = uname[:40]
        if "avatar_url" in updates:
            updates["avatar_url"] = updates["avatar_url"][:500000]  # data URL or URL
        if updates:
            sets = ", ".join([f"{k}=?" for k in updates.keys()] + ["updated_at=?"])
            vals = list(updates.values()) + [now, user_id]
            conn.execute(f"UPDATE user_profiles SET {sets} WHERE user_id=?", vals)
    return get_profile(user_id)


def update_preferences(user_id: int, section: str, prefs: Dict[str, Any]) -> Dict[str, Any]:
    init_profile_db()
    ensure_profile(user_id)
    section_map = {"trading": "trading_json", "ai": "ai_json", "app": "app_json"}
    if section not in section_map:
        raise ValueError("Invalid preferences section")
    col = section_map[section]
    with _connect() as conn:
        conn.execute(f"UPDATE user_preferences SET {col}=?, updated_at=? WHERE user_id=?", (json.dumps(prefs), _now(), user_id))
    return get_profile(user_id)["preferences"][section]


def update_notifications(user_id: int, prefs: Dict[str, Any]) -> Dict[str, Any]:
    init_profile_db()
    ensure_profile(user_id)
    allowed = {
        "email_notifications", "browser_push", "price_alerts", "ai_signal_notifications",
        "market_news_notifications", "watchlist_notifications", "security_alerts", "risk_notifications",
    }
    clean = {k: bool(prefs.get(k, False)) for k in allowed}
    with _connect() as conn:
        conn.execute("UPDATE user_notifications SET prefs_json=?, updated_at=? WHERE user_id=?", (json.dumps(clean), _now(), user_id))
    return clean


def add_activity(user_id: int, event_type: str, label: str, detail: str = "", ip_address: str = "") -> None:
    init_profile_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO user_activity (user_id,event_type,label,detail,ip_address,created_at) VALUES (?,?,?,?,?,?)",
            (user_id, event_type, label, detail[:500], ip_address[:80], _now()),
        )


def list_activity(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    init_profile_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id,event_type,label,detail,ip_address,created_at FROM user_activity WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, max(1, min(limit, 200))),
        ).fetchall()
    return [dict(r) for r in rows]


def create_session(user_id: int, token: str, device: str = "", ip_address: str = "", user_agent: str = "") -> Dict[str, Any]:
    init_profile_db()
    sid = secrets.token_hex(16)
    now = _now()
    with _connect() as conn:
        conn.execute("UPDATE user_sessions SET is_current=0 WHERE user_id=?", (user_id,))
        conn.execute(
            """INSERT INTO user_sessions (user_id,session_token,device,ip_address,user_agent,created_at,last_seen_at,is_current)
               VALUES (?,?,?,?,?,?,?,1)""",
            (user_id, sid, device[:120], ip_address[:80], user_agent[:300], now, now),
        )
    return {"session_id": sid, "created_at": now}


def touch_session(user_id: int, session_id: str) -> None:
    init_profile_db()
    with _connect() as conn:
        conn.execute("UPDATE user_sessions SET last_seen_at=? WHERE user_id=? AND session_token=? AND revoked_at IS NULL", (_now(), user_id, session_id))


def list_sessions(user_id: int) -> List[Dict[str, Any]]:
    init_profile_db()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id,session_token,device,ip_address,user_agent,created_at,last_seen_at,revoked_at,is_current
               FROM user_sessions WHERE user_id=? ORDER BY id DESC LIMIT 50""",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["session_id"] = d.pop("session_token")
        d["is_current"] = bool(d["is_current"])
        out.append(d)
    return out


def revoke_session(user_id: int, session_id: str) -> bool:
    init_profile_db()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE user_sessions SET revoked_at=?, is_current=0 WHERE user_id=? AND session_token=? AND revoked_at IS NULL",
            (_now(), user_id, session_id),
        )
    return cur.rowcount > 0


def revoke_all_sessions(user_id: int, except_session_id: str = "") -> int:
    init_profile_db()
    with _connect() as conn:
        if except_session_id:
            cur = conn.execute(
                "UPDATE user_sessions SET revoked_at=?, is_current=0 WHERE user_id=? AND revoked_at IS NULL AND session_token!=?",
                (_now(), user_id, except_session_id),
            )
        else:
            cur = conn.execute(
                "UPDATE user_sessions SET revoked_at=?, is_current=0 WHERE user_id=? AND revoked_at IS NULL",
                (_now(), user_id),
            )
    return cur.rowcount


def list_connected_services(user_id: int) -> List[Dict[str, Any]]:
    init_profile_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id,service_type,name,status,config_json,secret_hint,created_at,updated_at FROM connected_services WHERE user_id=? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["config"] = _json(d.pop("config_json"), {})
        out.append(d)
    return out


def upsert_connected_service(user_id: int, service_type: str, name: str, config: Dict[str, Any], secret_hint: str = "") -> Dict[str, Any]:
    init_profile_db()
    now = _now()
    clean_config = {k: v for k, v in (config or {}).items() if k not in {"api_key", "secret", "password", "token"}}
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM connected_services WHERE user_id=? AND service_type=? AND name=?",
            (user_id, service_type, name),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE connected_services SET status=?, config_json=?, secret_hint=?, updated_at=? WHERE id=?",
                ("connected", json.dumps(clean_config), secret_hint[:40], now, row["id"]),
            )
            sid = row["id"]
        else:
            cur = conn.execute(
                "INSERT INTO connected_services (user_id,service_type,name,status,config_json,secret_hint,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (user_id, service_type, name[:80], "connected", json.dumps(clean_config), secret_hint[:40], now, now),
            )
            sid = cur.lastrowid
        saved = conn.execute("SELECT id,service_type,name,status,config_json,secret_hint,created_at,updated_at FROM connected_services WHERE id=?", (sid,)).fetchone()
    d = dict(saved)
    d["config"] = _json(d.pop("config_json"), {})
    return d


def revoke_connected_service(user_id: int, service_id: int) -> bool:
    init_profile_db()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM connected_services WHERE user_id=? AND id=?", (user_id, service_id))
    return cur.rowcount > 0


def set_account_active(user_id: int, active: bool) -> None:
    init_profile_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_active=?, deactivated_at=?, updated_at=? WHERE id=?",
            (1 if active else 0, None if active else _now(), _now(), user_id),
        )


def delete_account(user_id: int) -> None:
    init_profile_db()
    with _connect() as conn:
        for table in ["user_activity", "user_sessions", "user_notifications", "user_preferences", "user_profiles", "connected_services"]:
            conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
