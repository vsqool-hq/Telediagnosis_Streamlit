"""
Router faktur — wystawianie zbiorczego pliku importowego (SaldeoSMART) z gotowego
rozliczenia jednostek oraz zarządzanie Słownikiem jednostek (dane do faktur).

Przepływ: użytkownik wybiera przeliczony miesiąc, ustawia wspólną datę wystawienia
(z opcjonalnymi wyjątkami per jednostka) i pobiera plik .xlsx z rozbiciem każdej
jednostki na pozycje badań + WSPARCIE.
"""

import io
import os
import glob

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import db
from app.storage import job_paths, version_dir

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --- Słownik jednostek (dane do faktur) ------------------------------------
_SLOWNIK_FIELDS = ("full_name", "address", "postal_code", "city", "payment_term_days", "alt_name")


def _get_slownik() -> dict:
    return db.get_settings().get("invoice_slownik") or {}


def _clean_unit_record(rec: dict) -> dict:
    out = {}
    for f in _SLOWNIK_FIELDS:
        v = rec.get(f, "")
        if f == "payment_term_days":
            try:
                out[f] = max(0, int(v))
            except (TypeError, ValueError):
                out[f] = 14
        else:
            out[f] = str(v or "").strip()
    # Podjednostki: inne nazwy skrócone, które mają trafić na TĘ SAMĄ fakturę
    # (wspólny pełny kontrahent). Lista nazw systemowych, bez pustych i bez self.
    name = str(rec.get("system_name", "")).strip()
    subs = rec.get("subunits")
    if isinstance(subs, list):
        out["subunits"] = sorted({str(s).strip() for s in subs if str(s).strip() and str(s).strip() != name})
    else:
        out["subunits"] = []
    return out


@router.get("/units")
async def list_units():
    """Zwraca Słownik jednostek jako posortowaną listę (do przeglądu/edycji)."""
    s = _get_slownik()
    rows = [{"system_name": k, **_clean_unit_record(v if isinstance(v, dict) else {})}
            for k, v in s.items()]
    rows.sort(key=lambda r: r["system_name"].lower())
    return {"units": rows}


@router.put("/units")
async def save_units(payload: dict):
    """
    Zapis całego Słownika (lista obiektów z 'system_name' + pola). Zastępuje
    dotychczasowy Słownik. Termin płatności jest dublowany do 'payment_terms_by_unit'
    (jedno źródło prawdy — używane też w Windykacji)."""
    units = payload.get("units")
    if not isinstance(units, list):
        raise HTTPException(400, "Pole 'units' musi być listą jednostek.")
    slownik = {}
    for u in units:
        if not isinstance(u, dict):
            continue
        name = str(u.get("system_name", "")).strip()
        if not name:
            continue
        slownik[name] = _clean_unit_record(u)

    # Podjednostka może należeć tylko do JEDNEGO rodzica (inaczej podwójna faktura).
    # Pierwszy rodzic wygrywa. Podjednostka nie musi mieć własnego wpisu w Słowniku
    # (typowo to jednostka rozliczana, dla której nie wypełniamy danych nabywcy).
    claimed = set()
    for pname, rec in slownik.items():
        keep = []
        for s in rec.get("subunits") or []:
            if s == pname or s in claimed:
                continue
            claimed.add(s)
            keep.append(s)
        rec["subunits"] = keep

    settings = db.get_settings()
    settings["invoice_slownik"] = slownik
    # Dubluj terminy płatności do wspólnego słownika (Windykacja).
    terms = dict(settings.get("payment_terms_by_unit") or {})
    for name, rec in slownik.items():
        terms[name] = rec["payment_term_days"]
    settings["payment_terms_by_unit"] = terms
    db.save_settings(settings)
    return {"ok": True, "count": len(slownik)}


# --- Dostępne miesiące (przeliczone rozliczenia) ----------------------------
@router.get("/months")
async def list_months():
    """Miesiące z gotowym pełnym rozliczeniem (jak Pulpit/Historia) — do wyboru."""
    from app.routers.stats import latest_jobs_by_month
    from app.engine.invoices import last_day_of_period

    best = latest_jobs_by_month()
    out = []
    for period, info in sorted(best.items(), reverse=True):
        out.append({
            "period": period,
            "job_id": info["job_id"],
            "delivery_date": last_day_of_period(period).strftime("%Y-%m-%d"),
            "revenue": info.get("revenue"),
            "studies": info.get("studies"),
        })
    return {"months": out}


# --- Wyliczenie cennika dla zadania ----------------------------------------
def _cennik_dir_for_job(job_id: str) -> str:
    """Katalog z cennikiem jednostek dla zadania: snapshot zadania, a gdy go brak
    (np. zadania zsynchronizowane z chmury) — aktywna wersja cennika."""
    snap = job_paths(job_id)["cennik"]
    if glob.glob(os.path.join(snap, "*.csv")):
        return snap
    active = db.get_active_version("cennik")
    if active:
        return version_dir("cennik", active["id"])
    return snap


def _resolve_job(job_id: str | None, period: str | None) -> str:
    """Zwraca job_id: bezpośrednio albo z ostatniego rozliczenia danego miesiąca."""
    if job_id:
        if not db.get_job(job_id):
            raise HTTPException(404, "Nie znaleziono zadania.")
        return job_id
    if period:
        from app.routers.stats import latest_jobs_by_month
        best = latest_jobs_by_month()
        info = best.get(period)
        if not info:
            raise HTTPException(404, f"Brak przeliczonego rozliczenia dla miesiąca {period}.")
        return info["job_id"]
    raise HTTPException(400, "Podaj 'job_id' albo 'period'.")


# --- Podgląd (co zostanie wystawione) --------------------------------------
@router.get("/preview")
async def preview(job_id: str | None = None, period: str | None = None):
    from app.engine.invoices import compute_invoice_lines, merge_subunits

    jid = _resolve_job(job_id, period)
    paths = job_paths(jid)
    lines_by_unit, wsparcie_by_unit = compute_invoice_lines(paths["wynik"], _cennik_dir_for_job(jid))
    slownik = _get_slownik()
    # Łączenie podjednostek: jedna faktura dla wspólnego kontrahenta.
    lines_by_unit, wsparcie_by_unit, merged_into = merge_subunits(lines_by_unit, wsparcie_by_unit, slownik)

    rows = []
    for unit in sorted(lines_by_unit.keys()):
        lines = lines_by_unit[unit]
        wsp = wsparcie_by_unit.get(unit, 0)
        total = sum(l["ilosc"] * l["cena"] for l in lines) + (wsp or 0)
        rows.append({
            "system_name": unit,
            "positions": len(lines) + (1 if wsp else 0),
            "wsparcie": wsp or None,
            "total": round(total, 2),
            "in_slownik": unit in slownik,
            "merged": merged_into.get(unit, []),
        })
    return {
        "units": rows,
        "count": len(rows),
        "missing_slownik": [r["system_name"] for r in rows if not r["in_slownik"]],
    }


# --- Wystawienie faktur (pobranie pliku) -----------------------------------
@router.post("/generate")
async def generate(payload: dict):
    from app.engine.invoices import (compute_invoice_lines, build_invoice_workbook,
                                      merge_subunits, last_day_of_period, DEFAULT_BANK_ACCOUNT)

    job_id = payload.get("job_id")
    period = payload.get("period")
    issue_date = str(payload.get("issue_date", "")).strip()
    if not issue_date:
        raise HTTPException(400, "Podaj datę wystawienia faktury.")
    overrides = payload.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise HTTPException(400, "Pole 'overrides' musi być mapą {jednostka: data}.")

    jid = _resolve_job(job_id, period)
    job = db.get_job(jid)
    paths = job_paths(jid)

    # okres (do daty dostawy + nazwy pliku)
    from app.engine.periods import period_from_filename
    per = period or period_from_filename(job.get("input_name", "")) or ""
    if not per:
        raise HTTPException(400, "Nie udało się ustalić miesiąca rozliczeniowego dla tego zadania.")
    delivery = last_day_of_period(per)

    lines_by_unit, wsparcie_by_unit = compute_invoice_lines(paths["wynik"], _cennik_dir_for_job(jid))
    if not lines_by_unit:
        raise HTTPException(404, "Brak danych do wystawienia faktur dla tego miesiąca.")

    settings = db.get_settings()
    slownik = settings.get("invoice_slownik") or {}
    # Łączenie podjednostek: jedna faktura dla wspólnego kontrahenta (przed budową pliku).
    lines_by_unit, wsparcie_by_unit, _merged = merge_subunits(lines_by_unit, wsparcie_by_unit, slownik)
    bank = str(settings.get("invoice_bank_account") or DEFAULT_BANK_ACCOUNT).strip() or DEFAULT_BANK_ACCOUNT

    wb, meta = build_invoice_workbook(
        lines_by_unit, wsparcie_by_unit, slownik,
        issue_date=issue_date, delivery_date=delivery,
        overrides=overrides, bank_account=bank,
    )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"Faktury_{per}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    # policz jednostki spoza słownika do nagłówka informacyjnego (opcjonalnie czytane przez front)
    if meta.get("units_missing_slownik"):
        headers["X-Missing-Slownik"] = str(len(meta["units_missing_slownik"]))
    return StreamingResponse(buf, media_type=_XLSX_MEDIA, headers=headers)
