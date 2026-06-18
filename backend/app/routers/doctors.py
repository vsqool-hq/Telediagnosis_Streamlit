"""
Router modułu LEKARZY: diagnostyka gotowości, rozliczenie lekarzy i porównanie
(marża) — liczone dla istniejącego, ukończonego zadania jednostek (reużywamy
jego zweryfikowanych danych i snapshotu słownika). Moduł jednostek bez zmian.
"""

import os
import glob

from fastapi import APIRouter, HTTPException

from app import db
from app.storage import job_paths, version_dir

router = APIRouter(prefix="/api/doctors", tags=["doctors"])


def _active_doctor_cennik_csv() -> str | None:
    v = db.get_active_version("cennik_lekarzy")
    if not v:
        return None
    path = os.path.join(version_dir("cennik_lekarzy", v["id"]), v["filename"])
    return path if os.path.isfile(path) else None


def _slownik_path(wzorcowe_dir: str) -> str | None:
    files = [f for f in glob.glob(os.path.join(wzorcowe_dir, "*.xls*"))
             if not os.path.basename(f).startswith("~$")]
    return files[0] if files else None


def _active_slownik_path() -> str | None:
    """Ścieżka do AKTYWNEJ wersji słownika (a nie kopii sprzed uruchomienia zadania).
    Kolumnę „Rodzaj procedury lekarz" wypełnia się na bieżąco, więc kategorie
    bierzemy z aktualnego słownika, nie ze starego snapshotu zadania."""
    wz = db.get_active_version("wzorcowe")
    if not wz:
        return None
    p = os.path.join(version_dir("wzorcowe", wz["id"]), wz["filename"])
    return p if os.path.isfile(p) else None


@router.get("/coverage")
async def coverage():
    """Czy moduł jest gotowy: cennik lekarzy + wypełniona kolumna w słowniku."""
    from openpyxl import load_workbook

    out = {
        "doctor_cennik": None,
        "slownik_lekarz_filled": 0,
        "slownik_total": 0,
        "ready": False,
    }

    csv_path = _active_doctor_cennik_csv()
    if csv_path:
        n_rows = n_docs = 0
        docs = set()
        with open(csv_path, encoding="utf-8-sig") as f:
            next(f, None)
            for line in f:
                parts = line.rstrip("\n").split(";")
                if len(parts) >= 3 and parts[0]:
                    n_rows += 1
                    docs.add(parts[0])
        out["doctor_cennik"] = {"rows": n_rows, "doctors": len(docs)}

    wz = db.get_active_version("wzorcowe")
    if wz:
        spath = os.path.join(version_dir("wzorcowe", wz["id"]), wz["filename"])
        if os.path.isfile(spath):
            try:
                wb = load_workbook(spath, read_only=True, data_only=True)
                ws = wb["Szczegółowe"] if "Szczegółowe" in wb.sheetnames else wb[wb.sheetnames[0]]
                rows = ws.iter_rows(values_only=True)
                header = list(next(rows))
                idx = header.index("Rodzaj procedury lekarz") if "Rodzaj procedury lekarz" in header else None
                total = filled = 0
                for r in rows:
                    total += 1
                    if idx is not None and idx < len(r):
                        v = r[idx]
                        if v not in (None, "", "None"):
                            filled += 1
                out["slownik_total"] = total
                out["slownik_lekarz_filled"] = filled
            except Exception:  # noqa: BLE001
                pass

    out["ready"] = bool(out["doctor_cennik"] and out["slownik_lekarz_filled"] > 0)
    return out


def _resolve_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    if job["mode"] != "full":
        raise HTTPException(400, "Moduł lekarzy działa na pełnym rozliczeniu jednostek.")
    paths = job_paths(job_id)
    # Słownik bierzemy z AKTYWNEJ wersji (świeże kategorie „Rodzaj procedury lekarz"),
    # a tylko awaryjnie z kopii zapisanej przy zadaniu.
    slownik = _active_slownik_path() or _slownik_path(paths["wzorcowe"])
    cennik_lek = _active_doctor_cennik_csv()
    if not slownik:
        raise HTTPException(400, "Brak słownika w danych zadania.")
    if not cennik_lek:
        raise HTTPException(400, "Brak aktywnego cennika lekarzy. Wgraj go w zakładce 'Cennik lekarzy'.")
    return job, paths, slownik, cennik_lek


@router.get("/billing/{job_id}")
async def doctor_billing(job_id: str):
    _job, paths, slownik, cennik_lek = _resolve_job(job_id)
    from app.engine.doctors import build_doctor_billing
    return build_doctor_billing(paths["sprawdzone"], slownik, cennik_lek)


@router.get("/compare/{job_id}")
async def doctor_compare(job_id: str):
    _job, paths, slownik, cennik_lek = _resolve_job(job_id)
    from app.engine.compare import build_comparison
    return build_comparison(paths["sprawdzone"], slownik, paths["cennik"], cennik_lek)
