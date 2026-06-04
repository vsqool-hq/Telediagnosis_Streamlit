"""
Serwis uruchamiania zadań liczących.

Przygotowuje katalog roboczy zadania (kopiuje aktywne wersje plików wzorcowych
i cennika, zapisuje wgrany plik wejściowy oraz snapshot konfiguracji), a następnie
odpala proces `python -m app.run_job <job_id> <mode>` w tle.

Strumieniowanie logów odbywa się przez czytanie pliku log.txt (SSE w routerze).
"""

import os
import sys
import json
import glob
import uuid
import shutil
import datetime
import subprocess

from app import db
from app.storage import job_paths, version_dir, ensure_dirs


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _copy_active_version(kind: str, dest_dir: str) -> str | None:
    """Kopiuje aktywną wersję danego rodzaju do dest_dir. Zwraca id wersji lub None."""
    active = db.get_active_version(kind)
    if not active:
        return None
    src = os.path.join(version_dir(kind, active["id"]), active["filename"])
    os.makedirs(dest_dir, exist_ok=True)
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(dest_dir, active["filename"]))
    return active["id"]


def create_and_start_job(mode: str, upload_filename: str, upload_bytes: bytes) -> dict:
    """Tworzy zadanie, przygotowuje katalog i startuje proces liczący."""
    ensure_dirs()
    job_id = uuid.uuid4().hex[:12]
    paths = job_paths(job_id)

    for key in ("jednostki", "wzorcowe", "cennik", "sprawdzone", "wynik"):
        os.makedirs(paths[key], exist_ok=True)

    # Plik wejściowy (Jednostki)
    input_path = os.path.join(paths["jednostki"], upload_filename)
    with open(input_path, "wb") as f:
        f.write(upload_bytes)

    # Aktywne wersje plików wzorcowych i cennika
    wzorcowe_v = _copy_active_version("wzorcowe", paths["wzorcowe"])
    cennik_v = _copy_active_version("cennik", paths["cennik"]) if mode == "full" else None

    # Snapshot konfiguracji dla tego zadania
    with open(paths["config"], "w", encoding="utf-8") as f:
        json.dump(db.get_settings(), f, ensure_ascii=False)

    # Pusty log + status
    open(paths["log"], "w", encoding="utf-8").close()
    with open(paths["status"], "w", encoding="utf-8") as f:
        json.dump({"status": "queued", "started_at": None, "finished_at": None, "error": None}, f)

    db.create_job({
        "id": job_id,
        "mode": mode,
        "status": "queued",
        "input_name": upload_filename,
        "wzorcowe_version": wzorcowe_v,
        "cennik_version": cennik_v,
        "created_at": _now(),
    })

    # Walidacje wstępne — zanim odpalimy proces
    if wzorcowe_v is None:
        _fail(job_id, paths, "Brak aktywnej wersji plików wzorcowych. Wgraj i ustaw aktywną w zakładce 'Pliki wzorcowe'.")
        return db.get_job(job_id)
    if mode == "full" and cennik_v is None:
        _fail(job_id, paths, "Brak aktywnej wersji cennika. Wgraj i ustaw aktywną w zakładce 'Cennik'.")
        return db.get_job(job_id)

    # Start procesu liczącego w tle
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../backend
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.run_job", job_id, mode],
        cwd=backend_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    db.update_job(job_id, status="running", started_at=_now(), pid=proc.pid)
    return db.get_job(job_id)


def _fail(job_id: str, paths: dict, message: str):
    with open(paths["log"], "a", encoding="utf-8") as f:
        f.write(f"BŁĄD: {message}\n")
    with open(paths["status"], "w", encoding="utf-8") as f:
        json.dump({"status": "error", "error": message, "finished_at": _now()}, f, ensure_ascii=False)
    db.update_job(job_id, status="error", error=message, finished_at=_now())


def read_status(job_id: str) -> dict:
    """Czyta status.json zadania i synchronizuje go z bazą (bo proces jest osobny)."""
    paths = job_paths(job_id)
    if not os.path.isfile(paths["status"]):
        return {"status": "unknown"}
    with open(paths["status"], "r", encoding="utf-8") as f:
        status = json.load(f)

    db_job = db.get_job(job_id)
    if db_job and db_job["status"] != status.get("status"):
        db.update_job(
            job_id,
            status=status.get("status", db_job["status"]),
            finished_at=status.get("finished_at"),
            error=status.get("error"),
        )
    return status


def result_files(job_id: str, mode: str) -> list[str]:
    paths = job_paths(job_id)
    result_dir = paths["wynik"] if mode == "full" else paths["sprawdzone"]
    if not os.path.isdir(result_dir):
        return []
    return sorted(
        f for f in glob.glob(os.path.join(result_dir, "*"))
        if os.path.isfile(f) and not os.path.basename(f).startswith("~$")
    )
