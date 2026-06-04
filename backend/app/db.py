"""
Warstwa bazodanowa — SQLite (stdlib, bez dodatkowych zależności).
Pojedynczy użytkownik, więc prosty model połączenia-na-operację wystarcza.
"""

import sqlite3
import json
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


def init_db():
    ensure_dirs()
    with get_conn() as conn:
        conn.executescript(SCHEMA)
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
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO versions (id, kind, filename, original_name, label, size, is_active, uploaded_at)
               VALUES (:id, :kind, :filename, :original_name, :label, :size, :is_active, :uploaded_at)""",
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
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO jobs (id, mode, status, input_name, wzorcowe_version, cennik_version, created_at)
               VALUES (:id, :mode, :status, :input_name, :wzorcowe_version, :cennik_version, :created_at)""",
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


def list_jobs(limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
