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


@router.get("/trends")
async def trends():
    """Trend liczby jednostek i przychodu w czasie — po ukończonych pełnych rozliczeniach.
    Korzysta z cache podsumowań (stats.json), więc nie przelicza plików przy każdym wejściu."""
    from app.engine.revenue import cached_summary

    jobs = [j for j in db.list_jobs(limit=100) if j["status"] == "done" and j["mode"] == "full"]
    jobs.sort(key=lambda j: j["created_at"])

    points = []
    for j in jobs:
        paths = job_paths(j["id"])
        s = cached_summary(paths["base"], paths["wynik"], paths["cennik"])
        if s.get("empty"):
            continue
        points.append({
            "job_id": j["id"],
            "date": (j["finished_at"] or j["created_at"])[:10],
            "label": j["input_name"],
            "studies": s["total_studies"],
            "revenue": s["total_revenue"],
        })
    return {"points": points}
