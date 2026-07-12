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

-- Windykacja: należności per jednostka per miesiąc rozliczeniowy. Rekordy
-- z source_run_id='auto' są zarządzane automatyczną synchronizacją z rozliczeń;
-- source_run_id=NULL to wpisy ręczne (np. zaległości historyczne) — synchronizacja
-- ich nigdy nie rusza.
CREATE TABLE IF NOT EXISTS wind_receivables (
    id            TEXT PRIMARY KEY,
    unit_key      TEXT NOT NULL,           -- znormalizowany klucz jednostki (jak "Klient")
    unit_name     TEXT NOT NULL,           -- nazwa do wyświetlenia
    period        TEXT,                    -- 'YYYY-MM' albo NULL dla wpisów ręcznych bez okresu
    source_amount REAL NOT NULL DEFAULT 0,  -- kwota z ostatniej synchronizacji (referencja)
    amount_due    REAL NOT NULL DEFAULT 0,  -- kwota bieżąca (edytowalna)
    paid_amount   REAL NOT NULL DEFAULT 0,  -- wpłaty odnotowane BEZ podziału na transze
    status        TEXT NOT NULL DEFAULT 'wystawiona',
                                            -- 'wystawiona'|'czesciowo_oplacona'|'oplacona'|'sporna'|'odpisana'
    due_date      TEXT,                     -- 'YYYY-MM-DD'
    note          TEXT,
    source_run_id TEXT,                     -- id zadania (job) źródłowego, NULL = ręczny wpis
    source_changed INTEGER NOT NULL DEFAULT 0,  -- 1 = kwota z rozliczenia zmieniła się od edycji ręcznej
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wind_receivables_unit_period
    ON wind_receivables (unit_key, period);

CREATE TABLE IF NOT EXISTS wind_installments (
    id             TEXT PRIMARY KEY,
    receivable_id  TEXT NOT NULL REFERENCES wind_receivables(id) ON DELETE CASCADE,
    label          TEXT,
    amount         REAL NOT NULL,
    due_date       TEXT,
    status         TEXT NOT NULL DEFAULT 'oczekuje',   -- 'oczekuje'|'czesciowo_oplacona'|'oplacona'
    paid_amount    REAL NOT NULL DEFAULT 0,
    paid_at        TEXT,
    note           TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wind_installments_receivable
    ON wind_installments (receivable_id);

CREATE TABLE IF NOT EXISTS wind_receivable_history (
    id            TEXT PRIMARY KEY,
    receivable_id TEXT NOT NULL REFERENCES wind_receivables(id) ON DELETE CASCADE,
    field         TEXT NOT NULL,       -- 'amount_due' | 'due_date' | 'status' | 'note' | 'installment' | ...
    old_value     TEXT,
    new_value     TEXT,
    reason        TEXT,
    changed_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wind_history_receivable
    ON wind_receivable_history (receivable_id);

-- Trwałe usunięcie należności zsynchronizowanej z rozliczenia: bez tego wpisu
-- leniwa synchronizacja (przy każdym odczycie) odtworzyłaby usunięty rekord,
-- bo z jej punktu widzenia "brak rekordu" = "jeszcze nie utworzony".
CREATE TABLE IF NOT EXISTS wind_sync_skip (
    unit_key   TEXT NOT NULL,
    period     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (unit_key, period)
);

-- Podpozycje doliczane do faktury (kary umowne, korekty, inne) — każda zmienia
-- amount_due o swoją kwotę (dodatnią lub ujemną); patrz add_receivable_item.
CREATE TABLE IF NOT EXISTS wind_receivable_items (
    id            TEXT PRIMARY KEY,
    receivable_id TEXT NOT NULL REFERENCES wind_receivables(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL DEFAULT 'inne',   -- 'kara' | 'korekta' | 'inne'
    label         TEXT,
    amount        REAL NOT NULL,                  -- może być ujemna (korekta zmniejszająca)
    item_date     TEXT,                           -- data naliczenia 'YYYY-MM-DD', opcjonalna
    note          TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wind_items_receivable
    ON wind_receivable_items (receivable_id);

-- Zapis KAŻDEJ wpłaty osobno (kwota + faktyczna data) — nie tylko zbiorczy licznik
-- paid_amount. Pozwala pokazać pełną listę wpłat z ich prawdziwymi datami.
CREATE TABLE IF NOT EXISTS wind_payments (
    id             TEXT PRIMARY KEY,
    receivable_id  TEXT NOT NULL REFERENCES wind_receivables(id) ON DELETE CASCADE,
    installment_id TEXT REFERENCES wind_installments(id) ON DELETE SET NULL,
    amount         REAL NOT NULL,
    paid_at        TEXT NOT NULL,   -- 'YYYY-MM-DD'
    note           TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wind_payments_receivable
    ON wind_payments (receivable_id);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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


# ---- Windykacja: należności ---------------------------------------------------

def create_receivable(rec: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO wind_receivables
               (id, unit_key, unit_name, period, source_amount, amount_due, paid_amount, status,
                due_date, note, source_run_id, source_changed, created_at, updated_at)
               VALUES (:id, :unit_key, :unit_name, :period, :source_amount, :amount_due, :paid_amount, :status,
                       :due_date, :note, :source_run_id, :source_changed, :created_at, :updated_at)""",
            rec,
        )


def get_receivable(receivable_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wind_receivables WHERE id = ?", (receivable_id,)).fetchone()
        return dict(row) if row else None


def find_receivable_by_unit_period(unit_key: str, period: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM wind_receivables WHERE unit_key = ? AND period = ?", (unit_key, period)
        ).fetchone()
        return dict(row) if row else None


def list_receivables(period: str | None = None, status: str | None = None, unit_key: str | None = None):
    q = "SELECT * FROM wind_receivables WHERE 1=1"
    args = []
    if period:
        q += " AND period = ?"
        args.append(period)
    if status:
        q += " AND status = ?"
        args.append(status)
    if unit_key:
        q += " AND unit_key = ?"
        args.append(unit_key)
    q += " ORDER BY due_date IS NULL, due_date ASC"
    with get_conn() as conn:
        rows = conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]


def update_receivable(receivable_id: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE wind_receivables SET {cols} WHERE id = ?", (*fields.values(), receivable_id))


def delete_receivable(receivable_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM wind_receivables WHERE id = ?", (receivable_id,))


def add_sync_skip(unit_key: str, period: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO wind_sync_skip (unit_key, period, created_at) VALUES (?, ?, ?)",
            (unit_key, period, datetime.datetime.now().isoformat(timespec="seconds")),
        )


def list_sync_skip_keys() -> set:
    with get_conn() as conn:
        rows = conn.execute("SELECT unit_key, period FROM wind_sync_skip").fetchall()
        return {(r["unit_key"], r["period"]) for r in rows}


def add_history(entry: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO wind_receivable_history
               (id, receivable_id, field, old_value, new_value, reason, changed_at)
               VALUES (:id, :receivable_id, :field, :old_value, :new_value, :reason, :changed_at)""",
            entry,
        )


def list_history(receivable_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM wind_receivable_history WHERE receivable_id = ? ORDER BY changed_at DESC",
            (receivable_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---- Windykacja: transze -----------------------------------------------------

def add_installment(rec: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO wind_installments
               (id, receivable_id, label, amount, due_date, status, paid_amount, paid_at, note, created_at)
               VALUES (:id, :receivable_id, :label, :amount, :due_date, :status, :paid_amount, :paid_at,
                       :note, :created_at)""",
            rec,
        )


def list_installments(receivable_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM wind_installments WHERE receivable_id = ? ORDER BY due_date IS NULL, due_date ASC",
            (receivable_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_installment(installment_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wind_installments WHERE id = ?", (installment_id,)).fetchone()
        return dict(row) if row else None


def update_installment(installment_id: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE wind_installments SET {cols} WHERE id = ?", (*fields.values(), installment_id))


def delete_installment(installment_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM wind_installments WHERE id = ?", (installment_id,))


# ---- Windykacja: podpozycje (kary, korekty) -----------------------------------

def add_receivable_item(entry: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO wind_receivable_items
               (id, receivable_id, kind, label, amount, item_date, note, created_at)
               VALUES (:id, :receivable_id, :kind, :label, :amount, :item_date, :note, :created_at)""",
            entry,
        )


def list_receivable_items(receivable_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM wind_receivable_items WHERE receivable_id = ? ORDER BY created_at",
            (receivable_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_receivable_item(item_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wind_receivable_items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None


def delete_receivable_item(item_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM wind_receivable_items WHERE id = ?", (item_id,))


# ---- Windykacja: wpłaty (lista, z datami) -------------------------------------

def add_payment(entry: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO wind_payments
               (id, receivable_id, installment_id, amount, paid_at, note, created_at)
               VALUES (:id, :receivable_id, :installment_id, :amount, :paid_at, :note, :created_at)""",
            entry,
        )


def list_payments(receivable_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM wind_payments WHERE receivable_id = ? ORDER BY paid_at DESC, created_at DESC",
            (receivable_id,),
        ).fetchall()
        return [dict(r) for r in rows]
