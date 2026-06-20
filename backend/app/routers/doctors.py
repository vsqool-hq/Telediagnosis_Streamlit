"""
Router modułu LEKARZY: diagnostyka gotowości, rozliczenie lekarzy i porównanie
(marża) — liczone dla istniejącego, ukończonego zadania jednostek (reużywamy
jego zweryfikowanych danych i snapshotu słownika). Moduł jednostek bez zmian.
"""

import os
import io
import json
import glob
import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import db
from app.storage import job_paths, version_dir

router = APIRouter(prefix="/api/doctors", tags=["doctors"])


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _lekarze_dir(paths: dict) -> str:
    d = os.path.join(paths["base"], "lekarze")
    os.makedirs(d, exist_ok=True)
    return d


def _cache_path(paths: dict, name: str) -> str:
    return os.path.join(_lekarze_dir(paths), name)


def _load_cache(paths: dict, name: str):
    p = _cache_path(paths, name)
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _save_cache(paths: dict, name: str, data: dict):
    try:
        with open(_cache_path(paths, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


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


def _excluded_keys() -> list:
    """Klucze lekarzy wyłączonych z rozliczenia (z ustawień)."""
    try:
        return sorted(set(db.get_settings().get("doctors_excluded", []) or []))
    except Exception:  # noqa: BLE001
        return []


@router.get("/billing/{job_id}")
async def doctor_billing(job_id: str, recompute: bool = False, peek: bool = False):
    """
    Rozliczenie lekarzy dla zadania. Wynik jest ZAPISYWANY na dysku (lekarze/billing.json),
    więc po zmianie zakładki / restarcie wczytuje się od razu, bez ponownego liczenia.
      • peek=true     → zwróć zapisany wynik albo {empty, reason:'not_computed'} BEZ liczenia,
      • recompute=true → policz od nowa i nadpisz zapis,
      • domyślnie      → zwróć zapis, a gdy go brak — policz i zapisz.
    Cache jest unieważniany, gdy zmieni się lista wyłączonych lekarzy.
    """
    paths = job_paths(job_id)
    excluded = _excluded_keys()
    cached = None if recompute else _load_cache(paths, "billing.json")
    if cached is not None and cached.get("_excluded_keys", []) == excluded:
        return cached
    if peek:
        return {"empty": True, "reason": "not_computed", "computed_at": None}

    _job, paths, slownik, cennik_lek = _resolve_job(job_id)
    from app.engine.doctors import build_doctor_billing
    result = build_doctor_billing(paths["sprawdzone"], slownik, cennik_lek, excluded_keys=excluded)
    if not result.get("empty"):
        result["computed_at"] = _now()
        result["_excluded_keys"] = excluded
        _save_cache(paths, "billing.json", result)
    return result


@router.get("/compare/{job_id}")
async def doctor_compare(job_id: str, recompute: bool = False, peek: bool = False):
    """Porównanie (marża) dla zadania — z takim samym zapisem/odczytem jak rozliczenie."""
    paths = job_paths(job_id)
    cached = None if recompute else _load_cache(paths, "compare.json")
    if cached is not None:
        return cached
    if peek:
        return {"empty": True, "reason": "not_computed", "computed_at": None}

    _job, paths, slownik, cennik_lek = _resolve_job(job_id)
    from app.engine.compare import build_comparison
    result = build_comparison(paths["sprawdzone"], slownik, paths["cennik"], cennik_lek)
    if not result.get("empty"):
        result["computed_at"] = _now()
        _save_cache(paths, "compare.json", result)
    return result


def _xlsx_response(sheets: dict, filename: str) -> StreamingResponse:
    import pandas as pd
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet, rows in sheets.items():
            pd.DataFrame(rows or []).to_excel(writer, sheet_name=sheet[:31], index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/billing/{job_id}/download")
async def doctor_billing_download(job_id: str):
    paths = job_paths(job_id)
    excluded = _excluded_keys()
    res = _load_cache(paths, "billing.json")
    if res is None or res.get("_excluded_keys", []) != excluded:
        _job, paths, slownik, cennik_lek = _resolve_job(job_id)
        from app.engine.doctors import build_doctor_billing
        res = build_doctor_billing(paths["sprawdzone"], slownik, cennik_lek, excluded_keys=excluded)
        if res.get("empty"):
            raise HTTPException(400, res.get("reason", "Brak danych do rozliczenia lekarzy."))
        res["computed_at"] = _now()
        res["_excluded_keys"] = excluded
        _save_cache(paths, "billing.json", res)
    return _xlsx_response(
        {"Per lekarz": res.get("by_doctor", []), "Lekarz i kategoria": res.get("rows", [])},
        "Rozliczenie_lekarzy.xlsx",
    )


@router.get("/compare/{job_id}/download")
async def doctor_compare_download(job_id: str):
    paths = job_paths(job_id)
    res = _load_cache(paths, "compare.json")
    if res is None:
        _job, paths, slownik, cennik_lek = _resolve_job(job_id)
        from app.engine.compare import build_comparison
        res = build_comparison(paths["sprawdzone"], slownik, paths["cennik"], cennik_lek)
        if res.get("empty"):
            raise HTTPException(400, res.get("reason", "Brak danych do porównania."))
        res["computed_at"] = _now()
        _save_cache(paths, "compare.json", res)
    return _xlsx_response({"Marża per kategoria": res.get("rows", [])}, "Porownanie_lekarze_jednostki.xlsx")


def _latest_full_job_id() -> str | None:
    for j in db.list_jobs(limit=100):
        if j["status"] == "done" and j["mode"] == "full":
            return j["id"]
    return None


@router.get("/list")
async def doctors_list(job_id: str | None = None):
    """
    Lista lekarzy (kolumna „Opisujący") znalezionych w danych zadania — domyślnie
    z najnowszego pełnego rozliczenia. Każdy z kluczem dopasowania i flagą, czy jest
    aktualnie wyłączony z rozliczenia. Służy do sekcji „Ustawienia lekarzy".
    """
    from app.engine.doctors import read_verified_studies, doctor_key, _norm, OPISUJACY_COL

    jid = job_id or _latest_full_job_id()
    if not jid:
        return {"job_id": None, "doctors": []}
    paths = job_paths(jid)
    df = read_verified_studies(paths["sprawdzone"])
    excluded = set(_excluded_keys())
    seen, doctors = {}, []
    if df is not None and OPISUJACY_COL in df.columns:
        for val in df[OPISUJACY_COL].dropna().unique():
            disp = _norm(val)
            if not disp:
                continue
            k = doctor_key(disp)
            if k in seen:
                continue
            seen[k] = True
            doctors.append({"name": disp, "key": k, "excluded": k in excluded})
    doctors.sort(key=lambda d: d["name"].lower())
    return {"job_id": jid, "doctors": doctors}


@router.put("/excluded")
async def set_excluded(payload: dict):
    """Zapisuje listę kluczy lekarzy wyłączonych z rozliczenia (w ustawieniach)."""
    keys = payload.get("keys", [])
    if not isinstance(keys, list):
        raise HTTPException(400, "Pole 'keys' musi być listą.")
    cfg = db.get_settings()
    cfg["doctors_excluded"] = sorted({str(k) for k in keys if k})
    db.save_settings(cfg)
    return {"ok": True, "doctors_excluded": cfg["doctors_excluded"]}
