"""Router panelu Ustawienia — edycja konfiguracji silnika."""

from fastapi import APIRouter, HTTPException

from app import db
from app.engine.config import DEFAULT_CONFIG

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings():
    return {"settings": db.get_settings(), "defaults": DEFAULT_CONFIG}


@router.put("")
async def update_settings(payload: dict):
    cfg = payload.get("settings", payload)
    if not isinstance(cfg, dict):
        raise HTTPException(400, "Nieprawidłowy format konfiguracji.")
    # Walidacja kluczowych pól liczbowych (num_processes: 0 = Auto)
    if "num_processes" in cfg:
        try:
            cfg["num_processes"] = max(0, int(cfg["num_processes"]))
        except (ValueError, TypeError):
            raise HTTPException(400, "Pole num_processes musi być liczbą całkowitą (0 = Auto).")
        # Zgodność wstecz: utrzymuj jedno źródło prawdy dla obu etapów.
        cfg["num_processes_verify"] = cfg["num_processes"] or 1
        cfg["num_processes_billing"] = cfg["num_processes"] or 1
    for key in ("num_processes_verify", "num_processes_billing"):
        if key in cfg:
            try:
                cfg[key] = max(1, int(cfg[key]))
            except (ValueError, TypeError):
                raise HTTPException(400, f"Pole {key} musi być liczbą całkowitą.")
    db.save_settings(cfg)
    return {"ok": True, "settings": cfg}


@router.post("/reset")
async def reset_settings():
    db.save_settings(dict(DEFAULT_CONFIG))
    return {"ok": True, "settings": DEFAULT_CONFIG}
