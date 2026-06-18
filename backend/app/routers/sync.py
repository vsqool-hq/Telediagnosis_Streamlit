"""
Synchronizacja aktywnych plików z chmury do lokalnej instancji.

Gdy liczysz „na tym komputerze", lokalny backend pobiera aktywne wersje
(słownik, cennik, cennik lekarzy) z backendu w chmurze i ustawia je jako aktywne
lokalnie — dzięki temu liczysz na NAJNOWSZYCH plikach ze strony internetowej.

Pobieranie idzie serwer→serwer (urllib), więc nie dotyczą go ograniczenia
przeglądarki (CORS/mixed-content). Token przekazywany jest do chmury w nagłówku.
"""

import os
import json
import uuid
import datetime
import urllib.request

from fastapi import APIRouter, HTTPException

from app import db
from app.storage import version_dir, ensure_dirs

router = APIRouter(prefix="/api/sync", tags=["sync"])

KINDS = ["wzorcowe", "cennik", "cennik_lekarzy"]


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _fetch(url: str, token: str) -> bytes:
    headers = {"X-API-Token": token} if token else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def pull_active_from_cloud(cloud: str, token: str) -> dict:
    """
    Pobiera aktywne wersje plików z chmury i ustawia je jako aktywne lokalnie.

    Reguły:
      * jeśli lokalna aktywna wersja jest NOWSZA lub równa (po dacie) — nie ruszamy,
      * deduplikacja: wersję z chmury zapisujemy pod stałym id ("cloud_<id>") z jej
        oryginalną datą; przy kolejnej synchronizacji nie pobieramy jej ponownie,
        tylko aktywujemy. Dzięki temu wersje się nie mnożą przy każdym starcie.
    """
    cloud = cloud.rstrip("/")
    ensure_dirs()
    synced: dict = {}
    errors: dict = {}

    for kind in KINDS:
        try:
            versions = json.loads(_fetch(f"{cloud}/api/versions/{kind}", token))
            active = next((v for v in versions if v.get("is_active")), None)
            if active is None and versions:
                active = max(versions, key=lambda v: v.get("uploaded_at", ""))
            if not active:
                synced[kind] = None
                continue

            # Lokalne nowsze/równe → zostawiamy lokalne.
            local_active = db.get_active_version(kind)
            if local_active and str(local_active.get("uploaded_at", "")) >= str(active.get("uploaded_at", "")):
                synced[kind] = None
                continue

            cloud_id = "cloud_" + str(active["id"])
            name = active.get("original_name") or active.get("filename") or f"{kind}.dat"

            if db.get_version(cloud_id):  # już pobrana wcześniej → tylko aktywuj
                db.set_active_version(kind, cloud_id)
                synced[kind] = name
                continue

            content = _fetch(f"{cloud}/api/versions/{kind}/{active['id']}/download", token)
            vdir = version_dir(kind, cloud_id)
            os.makedirs(vdir, exist_ok=True)
            with open(os.path.join(vdir, name), "wb") as f:
                f.write(content)

            db.add_version({
                "id": cloud_id, "kind": kind, "filename": name, "original_name": name,
                "label": f"Z chmury ({active.get('label') or name})",
                "size": len(content), "is_active": 0,
                "uploaded_at": active.get("uploaded_at") or _now(),
            })
            db.set_active_version(kind, cloud_id)
            synced[kind] = name
        except Exception as e:  # noqa: BLE001
            errors[kind] = str(e)

    return {"synced": synced, "errors": errors}


@router.post("")
async def sync_from_cloud(payload: dict):
    cloud = (payload.get("cloud_base") or "").rstrip("/")
    token = payload.get("token") or ""
    if not cloud:
        raise HTTPException(400, "Brak adresu chmury (cloud_base).")
    if cloud.startswith(("http://localhost", "http://127.0.0.1")):
        raise HTTPException(400, "Adres chmury wskazuje na localhost — nie ma skąd synchronizować.")
    return pull_active_from_cloud(cloud, token)

