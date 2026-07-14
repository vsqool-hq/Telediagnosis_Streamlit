"""Router integracji TeamUp: konfiguracja klucza/kalendarzy + test połączenia."""

import datetime as dt

from fastapi import APIRouter, HTTPException

from app.engine import teamup

router = APIRouter(prefix="/api/teamup", tags=["teamup"])


@router.get("/config")
async def get_config():
    cfg = teamup.load_config()
    return {
        "has_key": bool(cfg["api_key"]),
        "key_from_env": cfg["key_from_env"],
        "key_source": cfg["key_source"],
        "env_names": cfg["env_names"],
        "cal_gotowosc": cfg["cal_gotowosc"],
        "cal_triaz": cfg["cal_triaz"],
    }


@router.put("/config")
async def put_config(payload: dict):
    cfg = teamup.save_config(
        api_key=payload.get("api_key"),
        cal_gotowosc=payload.get("cal_gotowosc"),
        cal_triaz=payload.get("cal_triaz"),
    )
    return {"ok": True, "has_key": bool(cfg["api_key"])}


@router.get("/test")
async def test_connection():
    """Próbne pobranie wydarzeń z ostatnich 7 dni z obu kalendarzy."""
    cfg = teamup.load_config()
    if not cfg["api_key"]:
        raise HTTPException(400, "Brak klucza API — wpisz go poniżej albo ustaw sekret TEAMUP_API_KEY.")
    end = dt.date.today()
    start = end - dt.timedelta(days=14)
    out = {}
    for label, cal in (("gotowosc", cfg["cal_gotowosc"]), ("triaz", cfg["cal_triaz"])):
        try:
            evs = teamup.fetch_events(cal, start, end, cfg["api_key"])
            titles = [str(e.get("title") or "") for e in evs if not e.get("all_day")][:5]
            # Zbiorczo: WSZYSTKIE nazwy pól własnych + ich RÓŻNE wartości (do 12),
            # żeby znaleźć, w którym polu siedzą tagi W/Ś (jeśli w ogóle).
            fields: dict = {}
            for e in evs:
                if e.get("all_day"):
                    continue
                for k, v in (e.get("custom") or {}).items():
                    fields.setdefault(str(k), set()).add(teamup._first_str(v).strip())
            pola = {k: sorted(x for x in vals if x)[:12] for k, vals in sorted(fields.items())}
            # Kilka przykładów z wykrytym typem dnia.
            samples = []
            for e in evs:
                if e.get("all_day") or not (e.get("custom")):
                    continue
                samples.append({
                    "title": str(e.get("title") or ""),
                    "wykryty_tryb": teamup._tryb_dyzuru(e),
                })
                if len(samples) >= 4:
                    break
            out[label] = {"ok": True, "events": len(evs), "sample": titles,
                          "pola_wszystkie": pola, "pola_wlasne": samples}
        except RuntimeError as e:
            out[label] = {"ok": False, "error": str(e)}
    return out
