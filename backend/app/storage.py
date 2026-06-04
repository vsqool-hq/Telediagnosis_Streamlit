"""
Układ katalogów na wolumenie danych (domyślnie /data).

Struktura:
  /data/app.db                              – baza SQLite
  /data/config.json                         – aktywna konfiguracja silnika
  /data/versions/wzorcowe/<vid>/<plik>      – wersje plików wzorcowych
  /data/versions/cennik/<vid>/<plik>        – wersje cennika
  /data/jobs/<job_id>/...                   – katalog roboczy pojedynczego zadania
"""

import os

DATA_DIR = os.environ.get("TELEDIAG_DATA_DIR", "/data")

DB_PATH = os.path.join(DATA_DIR, "app.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
VERSIONS_DIR = os.path.join(DATA_DIR, "versions")
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
TMP_DIR = os.path.join(DATA_DIR, "tmp")


def ensure_dirs():
    for d in [DATA_DIR, VERSIONS_DIR, os.path.join(VERSIONS_DIR, "wzorcowe"),
              os.path.join(VERSIONS_DIR, "cennik"), JOBS_DIR, TMP_DIR]:
        os.makedirs(d, exist_ok=True)


def version_dir(kind: str, version_id: str) -> str:
    return os.path.join(VERSIONS_DIR, kind, version_id)


def job_dir(job_id: str) -> str:
    return os.path.join(JOBS_DIR, job_id)


def job_paths(job_id: str) -> dict:
    base = job_dir(job_id)
    return {
        "base": base,
        "jednostki": os.path.join(base, "Jednostki"),
        "wzorcowe": os.path.join(base, "pliki_wzorcowe"),
        "cennik": os.path.join(base, "Cennik"),
        "sprawdzone": os.path.join(base, "pliki_sprawdzone"),
        "wynik": os.path.join(base, "Wynik"),
        "log": os.path.join(base, "log.txt"),
        "status": os.path.join(base, "status.json"),
        "config": os.path.join(base, "config.json"),
    }
