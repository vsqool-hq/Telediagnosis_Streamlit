"""Router zadań: tworzenie, status, streaming logów (SSE), pobieranie wyników."""

import os
import io
import json
import asyncio
import zipfile

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, FileResponse

from app import db
from app.services import runner
from app.storage import job_paths

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ALLOWED_MODES = {"full", "unmatched"}


@router.post("")
async def create_job(file: UploadFile = File(...), mode: str = Form("full")):
    if mode not in ALLOWED_MODES:
        raise HTTPException(400, f"Nieprawidłowy tryb: {mode}")
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Wgraj plik Excel (.xlsx lub .xls).")
    content = await file.read()
    job = runner.create_and_start_job(mode, file.filename, content)
    return job


@router.get("")
async def list_jobs():
    return db.list_jobs()


@router.get("/active")
async def active_job():
    """Najnowsze zadanie w toku (queued/running) wraz z aktualnym statusem, albo null.
    Pozwala dowolnemu urządzeniu wznowić podgląd trwającego rozliczenia."""
    for job in db.list_jobs(limit=20):
        status = runner.read_status(job["id"]).get("status", job["status"])
        if status in ("queued", "running"):
            job["live_status"] = status
            return job
    return None


@router.get("/{job_id}")
async def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    status = runner.read_status(job_id)
    job["live_status"] = status.get("status", job["status"])
    job["files"] = [os.path.basename(p) for p in runner.result_files(job_id, job["mode"])]
    return job


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Zatrzymuje trwające rozliczenie (przycisk STOP)."""
    job = runner.cancel_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    return job


@router.post("/{job_id}/rerun")
async def rerun_job(job_id: str):
    """Przelicza ponownie na TYM SAMYM, wcześniej wgranym pliku (zapisanym przy
    zadaniu) — bez wgrywania od nowa. Tworzy nowe zadanie z aktualnym silnikiem
    oraz aktualnymi (aktywnymi) plikami wzorcowymi i cennikiem."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    path = os.path.join(job_paths(job_id)["jednostki"], job["input_name"])
    if not os.path.isfile(path):
        raise HTTPException(400, "Brak zapisanego pliku źródłowego tego zadania — wgraj plik ponownie.")
    with open(path, "rb") as f:
        content = f.read()
    return runner.create_and_start_job(job["mode"], job["input_name"], content)


@router.get("/{job_id}/logs")
async def stream_logs(job_id: str):
    """Streamuje log zadania jako Server-Sent Events aż do zakończenia."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    paths = job_paths(job_id)

    async def event_generator():
        last_pos = 0
        while True:
            # Wyślij nowe fragmenty logu
            if os.path.isfile(paths["log"]):
                with open(paths["log"], "r", encoding="utf-8", errors="replace") as f:
                    f.seek(last_pos)
                    chunk = f.read()
                    last_pos = f.tell()
                if chunk:
                    for line in chunk.splitlines():
                        yield f"data: {json.dumps(line, ensure_ascii=False)}\n\n"

            # Sprawdź status
            status = "running"
            if os.path.isfile(paths["status"]):
                try:
                    with open(paths["status"], "r", encoding="utf-8") as f:
                        status = json.load(f).get("status", "running")
                except (json.JSONDecodeError, OSError):
                    pass

            if status in ("done", "error", "cancelled"):
                runner.read_status(job_id)  # synchronizacja z bazą
                yield f"event: end\ndata: {json.dumps({'status': status})}\n\n"
                break

            await asyncio.sleep(0.7)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{job_id}/result")
async def download_result(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    files = runner.result_files(job_id, job["mode"])
    if not files:
        raise HTTPException(404, "Brak plików wynikowych.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, os.path.basename(path))
    buffer.seek(0)

    zip_name = "Wynik.zip" if job["mode"] == "full" else "pliki_sprawdzone.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@router.get("/{job_id}/result/{filename}")
async def download_single(job_id: str, filename: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    for path in runner.result_files(job_id, job["mode"]):
        if os.path.basename(path) == filename:
            return FileResponse(path, filename=filename)
    raise HTTPException(404, "Nie znaleziono pliku.")


@router.get("/{job_id}/input")
async def download_input(job_id: str):
    """Pobranie oryginalnego, wgranego pliku wejściowego (Jednostki) danego zadania."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    path = os.path.join(job_paths(job_id)["jednostki"], job["input_name"])
    if not os.path.isfile(path):
        raise HTTPException(404, "Brak pliku źródłowego.")
    return FileResponse(path, filename=job["input_name"])


@router.get("/{job_id}/import-export")
async def import_export(job_id: str, fmt: str = "csv"):
    """Zbiorczy plik importowy (Data/Klient/Badanie/Ilość) z pełnego rozliczenia."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    if job["mode"] != "full":
        raise HTTPException(400, "Eksport dostępny tylko dla pełnego rozliczenia.")

    from app.engine.summary import build_import_data  # pandas dopiero tutaj

    df = build_import_data(job_paths(job_id)["wynik"])
    if df.empty:
        raise HTTPException(404, "Brak danych do eksportu.")

    buffer = io.BytesIO()
    if fmt == "xlsx":
        df.to_excel(buffer, index=False)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        name = "Import.xlsx"
    else:
        buffer.write(df.to_csv(index=False, sep=";", encoding="utf-8").encode("utf-8"))
        media = "text/csv"
        name = "Import.csv"
    buffer.seek(0)
    return StreamingResponse(
        buffer, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
