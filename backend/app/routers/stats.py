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

# Memoizacja best_jobs_by_month (patrz funkcja) — współdzielona w procesie.
_BJM_CACHE: dict = {"sig": None, "val": None}

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
    from app.engine.config import load_config
    from app.engine import ENGINE_VERSION
    from app.engine.billing import get_excluded_units

    jobs = db.list_jobs(limit=200)
    cfg = load_config()
    # Memoizacja: wynik zależy tylko od zestawu zadań (id/status/finished_at/nazwa)
    # oraz ustawień wpływających na przychód (grupy, wersja silnika, wyłączone
    # jednostki). Gdy sygnatura bez zmian — zwracamy zapamiętany wynik, pomijając
    # pętlę i N odczytów stats.json (best_jobs_by_month jest wołane na prawie każdej
    # karcie, na Pulpicie 2×). Tania sygnatura — bez czytania plików wyników.
    sig = json.dumps({
        "jobs": [(j["id"], j.get("status"), j.get("finished_at"), j.get("input_name"))
                 for j in jobs if j.get("mode") == "full"],
        "groups": cfg.get("unit_groups", []),
        "engine": ENGINE_VERSION,
        "units_excluded": sorted(get_excluded_units()),
    }, ensure_ascii=False, sort_keys=True, default=str)
    if _BJM_CACHE.get("sig") == sig:
        return _BJM_CACHE["val"]

    best: dict = {}
    for j in jobs:
        if j["status"] != "done" or j["mode"] != "full":
            continue
        # Tylko pliki MIESIĘCZNE (data z 1. dniem miesiąca w nazwie). Pliki jednorazowe
        # (bez takiej daty) nie wchodzą na Pulpit/Historię/lekarzy/porównanie.
        period = period_from_filename(j.get("input_name"))
        if not period:
            continue
        paths = job_paths(j["id"])
        s = cached_summary(paths["base"], paths["wynik"], paths["cennik"])
        if s.get("empty"):
            continue
        rev = float(s.get("total_revenue") or 0)
        cur = best.get(period)
        if cur is None or rev > cur["revenue"]:
            best[period] = {
                "job_id": j["id"], "revenue": rev,
                "studies": int(s.get("total_studies") or 0),
                "period": period, "date": f"{period}-01",
                "input_name": j.get("input_name"),
                "computed_at": j.get("finished_at") or j.get("created_at"),
            }
    _BJM_CACHE["sig"] = sig
    _BJM_CACHE["val"] = best
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


@router.get("/dashboard")
async def dashboard():
    """Pulpit w JEDNYM żądaniu: overview + bieżące statystyki + trend.
    best_jobs_by_month liczone RAZ (zamiast 2× jak przy osobnych /current i /trends),
    mniej round-tripów i mniej pracy na jednym workerze."""
    from app.engine.revenue import cached_summary
    best = best_jobs_by_month()

    points = [
        {"job_id": b["job_id"], "date": b["date"], "label": p,
         "studies": b["studies"], "revenue": b["revenue"]}
        for p, b in sorted(best.items())
    ]

    current = {"empty": True}
    if best:
        latest = max(best.values(), key=lambda b: b["period"])
        paths = job_paths(latest["job_id"])
        s = cached_summary(paths["base"], paths["wynik"], paths["cennik"])
        current = {**s, "job_id": latest["job_id"], "period": latest["period"]}

    jobs = db.list_jobs(limit=100)
    done = [j for j in jobs if j["status"] == "done"]
    overview = {
        "jobs_total": len(jobs),
        "jobs_done": len(done),
        "active_cennik": db.get_active_version("cennik"),
        "active_wzorcowe": db.get_active_version("wzorcowe"),
    }
    return {"overview": overview, "current": current, "trends": {"points": points}}


def _job_revenue_by_client(job_id: str) -> dict:
    """Przychód per jednostka danego zadania — z CACHE (map.json w katalogu zadania).
    Liczone RAZ (wyniki zadania są niezmienne); dzięki temu Mapa wczytuje się od razu,
    zamiast czytać ~120 plików Excel przy każdym wejściu. Cache unieważnia zmiana
    wersji silnika (spójność z Pulpitem/Porównaniem)."""
    from app.engine import ENGINE_VERSION
    paths = job_paths(job_id)
    cache = os.path.join(paths["base"], "map.json")
    if os.path.isfile(cache):
        try:
            with open(cache, "r", encoding="utf-8") as f:
                d = json.load(f)
            if d.get("_engine") == ENGINE_VERSION:
                return d.get("by_client", {})
        except (OSError, ValueError):
            pass
    from app.engine.revenue import build_revenue
    df = build_revenue(paths["wynik"], paths["cennik"])
    by = {} if df.empty else {str(k): float(v) for k, v in df.groupby("Klient")["Wartość"].sum().items()}
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump({"_engine": ENGINE_VERSION, "by_client": by}, f, ensure_ascii=False)
    except OSError:
        pass
    return by


@router.get("/map")
async def map_data(months: int = 1):
    """Dane do zakładki „Mapa": przychód per jednostka za OSTATNI miesiąc (domyślnie;
    months=N dla dłuższej historii) z najlepszego przeliczenia miesiąca + współrzędne.
    Przychody per zadanie są cache'owane (map.json) — bez przeliczania przy wejściu."""
    geo = _load_geo()
    best = best_jobs_by_month()
    recent = sorted(best.keys())[-max(1, months):]

    rev_by_month: dict = {}
    for p in recent:
        try:
            rev_by_month[p] = _job_revenue_by_client(best[p]["job_id"])
        except Exception:  # noqa: BLE001
            rev_by_month[p] = {}

    keys = set()
    for p in recent:
        keys |= set(rev_by_month[p].keys())

    # Jednostki wyłączone w ustawieniach — nie pokazujemy ich na mapie.
    from app.engine.billing import get_excluded_units, _norm_unit
    excl = get_excluded_units()

    units, missing_geo = [], []
    for raw in sorted(keys):
        if _norm_unit(raw) in excl:
            continue
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


@router.get("/revenue-history/units")
async def units_revenue_history():
    """Historia przychodu per jednostka za WSZYSTKIE rozliczone miesiące (zawsze z
    najlepszego przeliczenia danego miesiąca — patrz best_jobs_by_month), do dymków
    „najedź i zobacz historię" na Pulpicie/Porównaniu. Klucz = etykieta grupy jednostek
    (jak w top_clients/by_unit), żeby dymek trafiał też w wiersze będące grupą kilku
    jednostek."""
    from app.engine.billing import get_excluded_units, _norm_unit
    from app.engine.config import load_config, build_unit_group_map, group_label

    gmap = build_unit_group_map(load_config().get("unit_groups", []))
    excl = get_excluded_units()
    best = best_jobs_by_month()

    history: dict[str, dict[str, float]] = {}
    for period, info in sorted(best.items()):
        try:
            by_client = _job_revenue_by_client(info["job_id"])
        except Exception:  # noqa: BLE001
            continue
        for raw_key, amount in by_client.items():
            if _norm_unit(raw_key) in excl:
                continue
            label = group_label(raw_key, gmap)
            history.setdefault(label, {})[period] = round(
                history.get(label, {}).get(period, 0.0) + float(amount or 0), 2
            )
    return {"units": history}
