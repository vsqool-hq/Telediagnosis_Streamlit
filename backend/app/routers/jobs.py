"""Router zadań: tworzenie, status, streaming logów (SSE), pobieranie wyników."""

import os
import io
import json
import asyncio
import zipfile

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, Response

from app import db
from app.services import runner
from app.storage import (job_paths, ensure_dirs, heal_job_dirs, BUNDLE_DIR_FIX,
                         safe_id, safe_filename)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ALLOWED_MODES = {"full", "unmatched", "doctors"}


@router.post("")
async def create_job(request: Request, file: UploadFile = File(...), mode: str = Form("full")):
    if mode not in ALLOWED_MODES:
        raise HTTPException(400, f"Nieprawidłowy tryb: {mode}")
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Wgraj plik Excel (.xlsx lub .xls).")
    content = await file.read()
    job = runner.create_and_start_job(mode, file.filename, content,
                                      created_by=getattr(request.state, "username", None))
    return job


def _with_period(job: dict) -> dict:
    """Dokłada miesiąc rozliczenia (z nazwy pliku − 1 mies.) — spójnie w całym UI."""
    from app.engine.periods import period_from_filename
    job["period"] = period_from_filename(job.get("input_name"))
    return job


@router.get("")
async def list_jobs():
    return [_with_period(j) for j in db.list_jobs()]


@router.get("/files")
async def list_files():
    """UNIKALNE wgrane pliki dla zakładki Rozliczenie (bez mnożenia przez kolejne
    przeliczenia). Dwa rodzaje:
      • miesięczny — plik z datą 1. dnia miesiąca w nazwie; jeden wpis na miesiąc,
        z OSTATNIEGO przeliczenia (latest_jobs_by_month). To on jest używany na
        Pulpicie/Historii/lekarzach/porównaniu.
      • jednorazowy — pozostałe pliki; jeden wpis na nazwę pliku (najnowsze przeliczenie),
        nigdzie indziej nieużywany.
    Każdy wpis niesie `job_ids` (wszystkie przeliczenia tej pozycji) — do czystego
    usunięcia całej pozycji za jednym razem."""
    from app.engine.periods import period_from_filename
    from app.routers.stats import latest_jobs_by_month

    all_jobs = db.list_jobs(limit=500)  # malejąco wg daty
    by_period_ids: dict = {}
    oneoff, oneoff_ids = {}, {}
    for j in all_jobs:
        per = period_from_filename(j.get("input_name"))
        if per:
            by_period_ids.setdefault(per, []).append(j["id"])
        else:
            key = (j.get("input_name") or j["id"]).strip()
            oneoff_ids.setdefault(key, []).append(j["id"])
            oneoff.setdefault(key, j)  # lista malejąco → pierwszy = najnowszy

    files = []
    best = latest_jobs_by_month()
    for period in sorted(best.keys(), reverse=True):
        b = best[period]
        files.append({
            "kind": "monthly", "period": period, "input_name": b.get("input_name"),
            "job_id": b["job_id"], "revenue": b.get("revenue"),
            "studies": b.get("studies"), "computed_at": b.get("computed_at"),
            "job_ids": by_period_ids.get(period, [b["job_id"]]),
        })
    for key, j in oneoff.items():
        files.append({
            "kind": "oneoff", "period": None, "input_name": key,
            "job_id": j["id"], "revenue": None, "studies": None,
            "computed_at": j.get("finished_at") or j.get("created_at"),
            "status": j.get("status"), "job_ids": oneoff_ids.get(key, [j["id"]]),
        })
    return {"files": files}


def import_job_bundle(raw: bytes) -> dict:
    """
    Rozpakowuje paczkę ZIP zadania (meta.json + jednostki/wynik/sprawdzone/lekarze/
    log/status) do katalogu zadania i zapisuje rekord w bazie. Idempotentne.
    Wspólne dla importu z innego backendu (push) i pobierania najnowszego
    zadania z chmury (sync). Zwraca {"ok", "job_id"}.
    """
    if not raw:
        raise HTTPException(400, "Puste żądanie.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        meta = json.loads(zf.read("meta.json"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Nieprawidłowa paczka zadania: {e}")

    # job_id z paczki staje się nazwą katalogu — walidujemy (blokuje „../").
    try:
        job_id = safe_id(meta.get("job_id"))
    except ValueError:
        raise HTTPException(400, "Niedozwolone job_id w paczce.")

    ensure_dirs()
    paths = job_paths(job_id)
    base = paths["base"]
    os.makedirs(base, exist_ok=True)
    # Katalogi, do których wolno rozpakować paczkę — nic poza tą listą nie powstanie.
    allowed_dirs = {"Jednostki", "Wynik", "pliki_sprawdzone", "lekarze"}
    for name in zf.namelist():
        if name == "meta.json" or name.endswith("/"):
            continue
        # Stare paczki miały katalogi o złych nazwach (jednostki/wynik/sprawdzone) —
        # mapujemy je na właściwe (Jednostki/Wynik/pliki_sprawdzone), żeby rozliczenie
        # lekarzy/porównanie/przychód znalazły dane. Nowe paczki mają już poprawne.
        parts = name.split("/")
        entry = safe_filename(parts[-1])          # ochrona przed zip-slip
        if not entry:
            continue
        if len(parts) == 1:
            target = os.path.join(base, entry)    # log.txt / status.json
        else:
            sub = BUNDLE_DIR_FIX.get(parts[-2], parts[-2])
            if sub not in allowed_dirs:
                continue
            os.makedirs(os.path.join(base, sub), exist_ok=True)
            target = os.path.join(base, sub, entry)
        with open(target, "wb") as f:
            f.write(zf.read(name))

    heal_job_dirs(job_id)  # domknięcie: przenieś ewentualne pozostałe błędne katalogi

    rec = {
        "id": job_id,
        "mode": meta.get("mode", "full"),
        "status": "done",
        "input_name": meta.get("input_name", ""),
        "wzorcowe_version": meta.get("wzorcowe_version"),
        "cennik_version": meta.get("cennik_version"),
        "created_at": meta.get("created_at") or _now_iso(),
    }
    if not db.get_job(job_id):
        db.create_job(rec)
    db.update_job(job_id, status="done",
                  started_at=meta.get("started_at"),
                  finished_at=meta.get("finished_at") or _now_iso(),
                  error=None)
    return {"ok": True, "job_id": job_id}


@router.post("/import")
async def import_job(request: Request):
    """
    Odbiera zadanie policzone na innym backendzie (np. lokalnym „Ten komputer")
    i zapisuje je tutaj, żeby było widoczne online. Body = ZIP z katalogiem
    zadania (jednostki/, wynik/, sprawdzone/, lekarze/, log.txt, status.json)
    oraz meta.json. Idempotentne: ponowny import odświeża pliki tego samego zadania.
    """
    return import_job_bundle(await request.body())


@router.get("/{job_id}/bundle")
async def download_bundle(job_id: str):
    """Paczka ZIP zadania (wgrany plik + wyniki) do pobrania — używane przez
    lokalny backend przy synchronizacji z chmury (pobranie ostatniego zadania)."""
    from app.routers.sync import _build_job_bundle
    data = _build_job_bundle(job_id)
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="job_{job_id}.zip"'})


def _now_iso():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _elapsed_seconds(job: dict):
    """Czas trwania zadania liczony od JEGO UTWORZENIA (created_at) — niezależnie od
    automatycznych wznowień (wznowienie to to samo zadanie, więc created_at się nie
    zmienia). Dla trwających: teraz − created_at; dla zakończonych: finished − created.
    created_at i 'teraz' są w tym samym (serwerowym) zegarze, więc różnica jest poprawna."""
    import datetime
    try:
        start = datetime.datetime.fromisoformat(job["created_at"])
    except (ValueError, TypeError, KeyError):
        return None
    end_s = job.get("finished_at") if job.get("status") in ("done", "error", "cancelled") else None
    try:
        end = datetime.datetime.fromisoformat(end_s) if end_s else datetime.datetime.now()
    except (ValueError, TypeError):
        end = datetime.datetime.now()
    return max(0, int((end - start).total_seconds()))


@router.get("/active")
async def active_job():
    """Najnowsze zadanie w toku (queued/running) wraz z aktualnym statusem, albo null.
    Pozwala dowolnemu urządzeniu wznowić podgląd trwającego rozliczenia."""
    for job in db.list_jobs(limit=20):
        status = runner.read_status(job["id"]).get("status", job["status"])
        if status in ("queued", "running"):
            job["live_status"] = status
            job["elapsed_seconds"] = _elapsed_seconds(job)
            return job
    return None


@router.get("/{job_id}")
async def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    status = runner.read_status(job_id)
    job["live_status"] = status.get("status", job["status"])
    job["elapsed_seconds"] = _elapsed_seconds(job)
    job["files"] = [os.path.basename(p) for p in runner.result_files(job_id, job["mode"])]
    return _with_period(job)


_DAILY_ANOMALY_PCT = 15.0   # próg odchylenia dziennej liczby badań (±%)


def _daily_counts(sprawdzone_dir: str, y: int, m: int) -> dict:
    """Liczba badań (wierszy) per dzień w miesiącu (y, m) — z arkuszy „Szczegółowe".
    Dzień z „Data badania (UTC)" (zapas: data zatwierdzenia/opisu)."""
    from app.engine.doctors import read_verified_studies
    import pandas as pd
    df = read_verified_studies(sprawdzone_dir)
    if df is None or getattr(df, "empty", True):
        return {}
    col = next((c for c in ("Data badania (UTC)", "Data 1. zatwierdzenia",
                            "Data pierwszego opisu (UTC)") if c in df.columns), None)
    if not col:
        return {}
    d = pd.to_datetime(df[col], errors="coerce")
    mask = d.notna() & (d.dt.year == y) & (d.dt.month == m)
    return {k: int(v) for k, v in d[mask].dt.strftime("%Y-%m-%d").value_counts().items()}


def _is_workday(datestr: str, holidays: set) -> bool:
    import datetime as _dt
    d = _dt.date.fromisoformat(datestr)
    return d.weekday() < 5 and d not in holidays


@router.get("/{job_id}/daily-check")
async def daily_check(job_id: str):
    """Kontrola dziennej liczby badań: porównuje każdy dzień rozliczanego miesiąca ze
    ŚREDNIĄ DZIENNĄ z POPRZEDNIEGO miesiąca — OSOBNO dla dni roboczych i dla
    weekendów/świąt (kalendarz PL), bo mają różny wolumen. Dzień odchylony o >±15%
    od średniej SWOJEGO typu = podejrzany (możliwy błąd danych: dublet/braki).
    Zwraca listę podejrzanych dni albo „ok"."""
    from app.engine.periods import period_from_filename
    from app.routers.stats import latest_jobs_by_month
    from app.engine.teamup import polish_holidays

    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    period = period_from_filename(job.get("input_name"))
    if not period:
        return {"available": False, "reason": "no_period"}
    try:
        y, m = int(period[:4]), int(period[5:7])
    except (ValueError, IndexError):
        return {"available": False, "reason": "no_period"}
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    prev_period = f"{py:04d}-{pm:02d}"

    prev = latest_jobs_by_month().get(prev_period)
    if not prev:
        return {"available": False, "reason": "no_prev_data", "period": period,
                "prev_period": prev_period}

    prev_counts = _daily_counts(job_paths(prev["job_id"])["sprawdzone"], py, pm)
    if not prev_counts:
        return {"available": False, "reason": "no_prev_data", "period": period,
                "prev_period": prev_period}

    holidays = polish_holidays(py) | polish_holidays(y)
    # średnia z poprzedniego miesiąca OSOBNO: dni robocze vs weekend/święto
    w = [v for d, v in prev_counts.items() if _is_workday(d, holidays)]
    nw = [v for d, v in prev_counts.items() if not _is_workday(d, holidays)]
    avg_work = (sum(w) / len(w)) if w else 0.0
    avg_free = (sum(nw) / len(nw)) if nw else 0.0

    cur_counts = _daily_counts(job_paths(job_id)["sprawdzone"], y, m)
    thr = _DAILY_ANOMALY_PCT / 100.0
    flagged = []
    for day in sorted(cur_counts):
        cnt = cur_counts[day]
        workday = _is_workday(day, holidays)
        base = avg_work if workday else avg_free
        if not base:
            continue
        dev = (cnt - base) / base
        if abs(dev) > thr:
            flagged.append({"date": day, "count": cnt, "baseline": round(base, 1),
                            "day_type": "roboczy" if workday else "weekend/święto",
                            "deviation_pct": round(dev * 100, 1),
                            "direction": "high" if dev > 0 else "low"})
    return {
        "available": True,
        "ok": not flagged,
        "period": period,
        "prev_period": prev_period,
        "avg_workday": round(avg_work, 1),
        "avg_free": round(avg_free, 1),
        "threshold_pct": _DAILY_ANOMALY_PCT,
        "days_checked": len(cur_counts),
        "flagged": flagged,
    }


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Zatrzymuje trwające rozliczenie (przycisk STOP)."""
    job = runner.cancel_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    return job


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """Usuwa rozliczenie: katalog zadania (wgrany plik, wyniki, lekarze) + wpis w bazie.
    Nie pozwala usunąć zadania w trakcie liczenia — najpierw je zatrzymaj."""
    import shutil
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    live = runner.read_status(job_id).get("status", job.get("status"))
    if live in ("running", "queued"):
        raise HTTPException(400, "Zadanie jest w trakcie liczenia — najpierw je zatrzymaj (STOP).")
    shutil.rmtree(job_paths(job_id)["base"], ignore_errors=True)
    db.delete_job(job_id)
    return {"ok": True}


@router.post("/{job_id}/rerun")
async def rerun_job(job_id: str, mode: str | None = None):
    """Przelicza ponownie na TYM SAMYM, wcześniej wgranym pliku (zapisanym przy
    zadaniu) — bez wgrywania od nowa. Tworzy nowe zadanie z aktualnym silnikiem
    oraz aktualnymi (aktywnymi) plikami wzorcowymi i cennikiem.

    `mode` (opcjonalny) pozwala przeliczyć w INNYM trybie niż pierwotny — dzięki
    temu z tego samego pliku można zrobić zarówno pełny proces, jak i same braki
    wzorca, niezależnie od tego, co wybrano wcześniej. Domyślnie tryb pierwotny."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    run_mode = mode or job["mode"]
    if run_mode not in ALLOWED_MODES:
        raise HTTPException(400, f"Nieprawidłowy tryb: {run_mode}")
    path = os.path.join(job_paths(job_id)["jednostki"], job["input_name"])
    if not os.path.isfile(path):
        raise HTTPException(400, "Brak zapisanego pliku źródłowego tego zadania — wgraj plik ponownie.")
    with open(path, "rb") as f:
        content = f.read()
    return runner.create_and_start_job(run_mode, job["input_name"], content)


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
