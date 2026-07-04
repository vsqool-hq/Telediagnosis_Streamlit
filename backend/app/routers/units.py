"""
Router JEDNOSTEK: lista jednostek z ostatniego rozliczenia + wyłączanie z rozliczenia.

Wyłączona jednostka znika ze statystyk (Pulpit/trend/Mapa) i z Porównania
(badania pomijane po OBU stronach, żeby marża się nie rozjechała). Rozliczenie
LEKARZY pozostaje bez zmian — od wyłączania lekarzy jest osobny mechanizm.
"""

from fastapi import APIRouter, HTTPException

from app import db

router = APIRouter(prefix="/api/units", tags=["units"])


@router.get("")
async def units_list(job_id: str | None = None):
    """Jednostki (kolumna „Klient") z danych zadania — domyślnie najnowszego pełnego
    rozliczenia — z flagą „wyłączona". Zestaw per zadanie z cache (participants)."""
    from app.routers.doctors import _latest_full_job_id, participants
    from app.engine.billing import get_excluded_units

    jid = job_id or _latest_full_job_id()
    if not jid:
        return {"job_id": None, "units": []}
    excluded = get_excluded_units()
    units = [{**u, "excluded": u["key"] in excluded} for u in participants(jid)["units"]]
    return {"job_id": jid, "units": units}


@router.put("/excluded")
async def set_units_excluded(payload: dict):
    """Zapisuje listę kluczy jednostek wyłączonych z rozliczenia (w ustawieniach)."""
    keys = payload.get("keys", [])
    if not isinstance(keys, list):
        raise HTTPException(400, "Pole 'keys' musi być listą.")
    cfg = db.get_settings()
    cfg["units_excluded"] = sorted({str(k).strip() for k in keys if str(k).strip()})
    db.save_settings(cfg)
    return {"ok": True, "units_excluded": cfg["units_excluded"]}
