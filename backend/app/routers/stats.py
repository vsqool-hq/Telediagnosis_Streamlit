"""
Router statystyk do dashboardu.

Statystyki budujemy z plików rozliczeń zadania:
  * liczbę/ilość jednostek oraz przychód (zł) liczymy w Pythonie (engine.revenue),
    odtwarzając logikę wyceny silnika — bo Excel trzyma formuły, nie liczby.
"""

import os
import json

from fastapi import APIRouter, HTTPException

from app import db
from app.storage import job_paths

router = APIRouter(prefix="/api/stats", tags=["stats"])

# Współrzędne jednostek (geokodowane raz ze słownika adresów) — do zakładki „Mapa".
_GEO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "unit_geo.json")
_geo_cache = None


def _load_geo() -> dict:
    global _geo_cache
    if _geo_cache is None:
        try:
            with open(_GEO_PATH, "r", encoding="utf-8") as f:
                _geo_cache = json.load(f)
        except (OSError, ValueError):
            _geo_cache = {}
    return _geo_cache


@router.get("/overview")
async def overview():
    jobs = db.list_jobs(limit=100)
    done = [j for j in jobs if j["status"] == "done"]
    return {
        "jobs_total": len(jobs),
        "jobs_done": len(done),
        "last_job": jobs[0] if jobs else None,
        "active_wzorcowe": db.get_active_version("wzorcowe"),
        "active_cennik": db.get_active_version("cennik"),
        "versions_wzorcowe": len(db.list_versions("wzorcowe")),
        "versions_cennik": len(db.list_versions("cennik")),
    }


def _modality_norm(m: str) -> str:
    m = str(m).strip().upper()
    return m if m in {"RTG", "TK", "MR", "MMG"} else "INNE"


@router.get("/job/{job_id}")
async def job_stats(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    if job["mode"] != "full":
        raise HTTPException(400, "Statystyki dostępne tylko dla pełnego rozliczenia.")

    from app.engine.revenue import cached_summary  # pandas dopiero tutaj

    paths = job_paths(job_id)
    return cached_summary(paths["base"], paths["wynik"], paths["cennik"])


def best_jobs_by_month() -> dict:
    """Dla każdego miesiąca rozliczeniowego zwraca zadanie o NAJWYŻSZYM przychodzie.

    Chroni przed pomyłkami: jeśli to samo rozliczenie policzono kilka razy i jeden
    przebieg był błędny (np. niepełny plik → 4 mln zamiast 6 mln), do Pulpitu i
    Porównania bierzemy ten z najwyższą kwotą. Miesiąc bierzemy z dat w pliku
    (pole „period"); dla starszych zadań bez tego pola — z daty policzenia.
    Zwraca: { "YYYY-MM": {job_id, revenue, studies, period, date} }.
    """
    from app.engine.revenue import cached_summary
    from app.engine.periods import period_from_filename
    best: dict = {}
    for j in db.list_jobs(limit=100):
        if j["status"] != "done" or j["mode"] != "full":
            continue
        paths = job_paths(j["id"])
        s = cached_summary(paths["base"], paths["wynik"], paths["cennik"])
        if s.get("empty"):
            continue
        # Miesiąc rozliczenia: z NAZWY pliku (data wygenerowania − 1 miesiąc).
        # Zapas: miesiąc z dat w pliku, a na końcu z daty policzenia.
        period = (period_from_filename(j.get("input_name"))
                  or s.get("period")
                  or (j.get("finished_at") or j.get("created_at") or "")[:7])
        rev = float(s.get("total_revenue") or 0)
        cur = best.get(period)
        if cur is None or rev > cur["revenue"]:
            best[period] = {
                "job_id": j["id"], "revenue": rev,
                "studies": int(s.get("total_studies") or 0),
                "period": period, "date": f"{period}-01",
            }
    return best


@router.get("/trends")
async def trends():
    """Trend przychodu/ilości — JEDEN punkt na miesiąc, z przeliczenia o najwyższej
    kwocie (patrz best_jobs_by_month). Korzysta z cache podsumowań."""
    best = best_jobs_by_month()
    points = [
        {"job_id": b["job_id"], "date": b["date"], "label": p,
         "studies": b["studies"], "revenue": b["revenue"]}
        for p, b in sorted(best.items())
    ]
    return {"points": points}


@router.get("/current")
async def current_stats():
    """Statystyki „bieżące" do Pulpitu: najlepsze (najwyższy przychód) przeliczenie
    NAJNOWSZEGO miesiąca rozliczeniowego."""
    best = best_jobs_by_month()
    if not best:
        return {"empty": True}
    latest = max(best.values(), key=lambda b: b["period"])
    from app.engine.revenue import cached_summary
    paths = job_paths(latest["job_id"])
    s = cached_summary(paths["base"], paths["wynik"], paths["cennik"])
    return {**s, "job_id": latest["job_id"], "period": latest["period"]}


@router.get("/map")
async def map_data(months: int = 3):
    """Dane do zakładki „Mapa": przychód per jednostka za ostatnie N miesięcy
    (z najlepszego przeliczenia każdego miesiąca) + współrzędne ze słownika adresów."""
    from app.engine.revenue import build_revenue
    geo = _load_geo()
    best = best_jobs_by_month()
    recent = sorted(best.keys())[-max(1, months):]

    rev_by_month: dict = {}
    for p in recent:
        paths = job_paths(best[p]["job_id"])
        try:
            df = build_revenue(paths["wynik"], paths["cennik"])
            rev_by_month[p] = {} if df.empty else df.groupby("Klient")["Wartość"].sum().to_dict()
        except Exception:  # noqa: BLE001
            rev_by_month[p] = {}

    keys = set()
    for p in recent:
        keys |= set(rev_by_month[p].keys())

    units, missing_geo = [], []
    for raw in sorted(keys):
        k = str(raw).strip().lower()
        g = geo.get(k)
        months_rev = {p: round(float(rev_by_month[p].get(raw, 0) or 0), 2) for p in recent}
        if g is None:
            if any(v > 0 for v in months_rev.values()):
                missing_geo.append(k)
            continue
        units.append({
            "key": k, "miasto": g.get("miasto") or k,
            "lat": g["lat"], "lng": g["lng"],
            "months": months_rev,
            "latest": months_rev.get(recent[-1], 0.0),
        })
    return {"months": recent, "units": units,
            "missing_geo": sorted(set(missing_geo))[:50], "geocoded": len(geo)}
