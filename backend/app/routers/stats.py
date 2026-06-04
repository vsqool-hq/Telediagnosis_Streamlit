"""
Router statystyk do dashboardu.

Statystyki ilościowe budujemy z plików rozliczeń zadania przy pomocy tej samej
logiki, co eksport importowy (engine.summary.build_import_data). Dzięki temu
liczby zgadzają się z resztą systemu.
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


def _modality_from_badanie(badanie: str) -> str:
    token = str(badanie).split(" ", 1)[0].upper()
    return token if token in {"RTG", "TK", "MR", "MMG"} else "INNE"


@router.get("/job/{job_id}")
async def job_stats(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    if job["mode"] != "full":
        raise HTTPException(400, "Statystyki dostępne tylko dla pełnego rozliczenia.")

    # Import wewnątrz funkcji — pandas ciągnięty tylko gdy faktycznie liczymy.
    from app.engine.summary import build_import_data

    paths = job_paths(job_id)
    df = build_import_data(paths["wynik"])
    if df.empty:
        return {"empty": True}

    df["Modalność"] = df["Badanie"].apply(_modality_from_badanie)

    total_studies = int(df["Ilość"].sum())

    by_modality = defaultdict(int)
    for _, r in df.iterrows():
        by_modality[r["Modalność"]] += int(r["Ilość"])

    by_client = (
        df.groupby("Klient")["Ilość"].sum().sort_values(ascending=False).head(15)
    )

    return {
        "empty": False,
        "total_studies": total_studies,
        "clients_count": int(df["Klient"].nunique()),
        "by_modality": [{"modality": k, "count": int(v)} for k, v in sorted(by_modality.items())],
        "top_clients": [{"client": k, "count": int(v)} for k, v in by_client.items()],
    }
