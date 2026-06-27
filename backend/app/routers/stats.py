"""
Router statystyk do dashboardu.

Statystyki budujemy z plików rozliczeń zadania:
  * liczbę/ilość jednostek oraz przychód (zł) liczymy w Pythonie (engine.revenue),
    odtwarzając logikę wyceny silnika — bo Excel trzyma formuły, nie liczby.
"""

from collections import defaultdict

from fastapi import APIRouter, HTTPException

from app import db
from app.storage import job_paths

router = APIRouter(prefix="/api/stats", tags=["stats"])


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
    best: dict = {}
    for j in db.list_jobs(limit=100):
        if j["status"] != "done" or j["mode"] != "full":
            continue
        paths = job_paths(j["id"])
        s = cached_summary(paths["base"], paths["wynik"], paths["cennik"])
        if s.get("empty"):
            continue
        period = s.get("period") or (j.get("finished_at") or j.get("created_at") or "")[:7]
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
