"""
Warstwa bazodanowa — SQLite (stdlib, bez dodatkowych zależności).
Pojedynczy użytkownik, więc prosty model połączenia-na-operację wystarcza.
"""

import sqlite3
import json
import hashlib
import secrets
import datetime
from contextlib import contextmanager

from app.storage import DB_PATH, ensure_dirs
from app.engine.config import DEFAULT_CONFIG


SCHEMA = """
CREATE TABLE IF NOT EXISTS versions (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,            -- 'wzorcowe' | 'cennik'
    filename     TEXT NOT NULL,            -- nazwa pliku na dysku
    original_name TEXT NOT NULL,
    label        TEXT,                     -- opis nadany przez użytkownika
    size         INTEGER,
    is_active    INTEGER NOT NULL DEFAULT 0,
    uploaded_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    mode          TEXT NOT NULL,           -- 'full' | 'unmatched'
    status        TEXT NOT NULL,           -- 'queued'|'running'|'done'|'error'
    input_name    TEXT,
    wzorcowe_version TEXT,
    cennik_version   TEXT,
    pid           INTEGER,
    error         TEXT,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    id   INTEGER PRIMARY KEY CHECK (id = 1),
    json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',   -- 'admin' | 'user'
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    username TEXT,
    action   TEXT NOT NULL,   -- czytelny opis akcji
    detail   TEXT             -- ścieżka / dodatkowe info
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _add_column(conn, table: str, column: str, decl: str):
    """Dokłada kolumnę, jeśli jej nie ma (migracja istniejącej bazy na produkcji)."""
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db():
    ensure_dirs()
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Migracje kolumn „kto dodał" (istniejące bazy sprzed audytu).
        _add_column(conn, "versions", "uploaded_by", "TEXT")
        _add_column(conn, "jobs", "created_by", "TEXT")
        row = conn.execute("SELECT json FROM settings WHERE id = 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO settings (id, json) VALUES (1, ?)",
                         (json.dumps(DEFAULT_CONFIG, ensure_ascii=False),))


# ---- Ustawienia -------------------------------------------------------------

def get_settings() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT json FROM settings WHERE id = 1").fetchone()
        return json.loads(row["json"]) if row else dict(DEFAULT_CONFIG)


def save_settings(cfg: dict):
    with get_conn() as conn:
        conn.execute("UPDATE settings SET json = ? WHERE id = 1",
                     (json.dumps(cfg, ensure_ascii=False),))


# ---- Wersje plików ----------------------------------------------------------

def list_versions(kind: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM versions WHERE kind = ? ORDER BY uploaded_at DESC", (kind,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_active_version(kind: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM versions WHERE kind = ? AND is_active = 1", (kind,)
        ).fetchone()
        return dict(row) if row else None


def add_version(rec: dict):
    rec.setdefault("uploaded_by", None)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO versions (id, kind, filename, original_name, label, size, is_active, uploaded_at, uploaded_by)
               VALUES (:id, :kind, :filename, :original_name, :label, :size, :is_active, :uploaded_at, :uploaded_by)""",
            rec,
        )


def set_active_version(kind: str, version_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE versions SET is_active = 0 WHERE kind = ?", (kind,))
        conn.execute("UPDATE versions SET is_active = 1 WHERE id = ? AND kind = ?",
                     (version_id, kind))


def get_version(version_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM versions WHERE id = ?", (version_id,)).fetchone()
        return dict(row) if row else None


def delete_version(version_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM versions WHERE id = ?", (version_id,))


# ---- Zadania ----------------------------------------------------------------

def create_job(rec: dict):
    rec.setdefault("created_by", None)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO jobs (id, mode, status, input_name, wzorcowe_version, cennik_version, created_at, created_by)
               VALUES (:id, :mode, :status, :input_name, :wzorcowe_version, :cennik_version, :created_at, :created_by)""",
            rec,
        )


def update_job(job_id: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))


def get_job(job_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def delete_job(job_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def list_jobs(limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---- Użytkownicy i sesje (role: admin / user) -------------------------------

def _hash_password(password: str, salt: str | None = None, iters: int = 200_000) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iters).hex()
    return f"pbkdf2${iters}${salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, h = str(stored).split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iters)).hex()
        return secrets.compare_digest(calc, h)
    except Exception:  # noqa: BLE001
        return False


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def has_users() -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def list_users() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY username"
        ).fetchall()
        return [dict(r) for r in rows]


def get_user_by_username(username: str):
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(r) if r else None


def create_user(username: str, password: str, role: str = "user") -> dict:
    username = str(username).strip()
    role = "admin" if role == "admin" else "user"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?,?,?,?)",
            (username, _hash_password(password), role, _now()),
        )
        r = conn.execute("SELECT id, username, role, created_at FROM users WHERE username = ?",
                         (username,)).fetchone()
        return dict(r)


def update_user(user_id: int, password: str | None = None, role: str | None = None):
    with get_conn() as conn:
        if password:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (_hash_password(password), user_id))
        if role in ("admin", "user"):
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def delete_user(user_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def count_admins() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) c FROM users WHERE role = 'admin'").fetchone()["c"]


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_conn() as conn:
        conn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)",
                     (token, user_id, _now()))
    return token


def get_session_user(token: str):
    if not token:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT u.id, u.username, u.role FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ?", (token,)
        ).fetchone()
        return dict(r) if r else None


def delete_session(token: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# ---- Dziennik zdarzeń (audyt akcji administratorów) -------------------------

def add_audit(username: str | None, action: str, detail: str | None = None):
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, username, action, detail) VALUES (?,?,?,?)",
                (_now(), username, action, detail),
            )
    except Exception:  # noqa: BLE001
        pass   # audyt nie może wywrócić żądania


def list_audit(limit: int = 300) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, ts, username, action, detail FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
