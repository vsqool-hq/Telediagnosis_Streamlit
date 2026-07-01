"""
Synchronizacja aktywnych plików z chmury do lokalnej instancji.

Gdy liczysz „na tym komputerze", lokalny backend pobiera aktywne wersje
(słownik, cennik, cennik lekarzy) z backendu w chmurze i ustawia je jako aktywne
lokalnie — dzięki temu liczysz na NAJNOWSZYCH plikach ze strony internetowej.

Pobieranie idzie serwer→serwer (urllib), więc nie dotyczą go ograniczenia
przeglądarki (CORS/mixed-content). Token przekazywany jest do chmury w nagłówku.
"""

import os
import io
import glob
import json
import uuid
import zipfile
import datetime
import urllib.request

from fastapi import APIRouter, HTTPException

from app import db
from app.storage import version_dir, ensure_dirs, job_paths

router = APIRouter(prefix="/api/sync", tags=["sync"])

KINDS = ["wzorcowe", "cennik", "cennik_lekarzy"]


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _resolve_cloud(payload: dict):
    """Adres i token chmury. PREFERUJEMY konfigurację serwera (sync.env:
    TELEDIAG_SYNC_URL / TELEDIAG_SYNC_TOKEN) — to są właściwe dane dostępowe TEGO
    komputera do chmury. Token z przeglądarki uwierzytelnia lokalny backend (gdzie
    zwykle nie ma tokenu), więc nie nadaje się do logowania w chmurze (stąd 401).
    Zapas: wartości z żądania."""
    env_url = os.environ.get("TELEDIAG_SYNC_URL", "").strip().rstrip("/")
    env_token = os.environ.get("TELEDIAG_SYNC_TOKEN", "").strip()
    cloud = (env_url or (payload.get("cloud_base") or "")).rstrip("/")
    token = env_token or (payload.get("token") or "")
    return cloud, token


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

    # Ustawienia silnika z chmury (priorytety, słowa kluczowe, WYŁĄCZENI LEKARZE…),
    # żeby liczenie lokalne dało ten sam wynik co w chmurze. Nie nadpisujemy
    # liczby rdzeni — wydajność jest cechą tej konkretnej maszyny.
    try:
        cloud_settings = json.loads(_fetch(f"{cloud}/api/settings", token)).get("settings", {})
        if isinstance(cloud_settings, dict) and cloud_settings:
            local_cfg = db.get_settings()
            for k, v in cloud_settings.items():
                if k in ("num_processes", "num_processes_verify", "num_processes_billing"):
                    continue
                local_cfg[k] = v
            db.save_settings(local_cfg)
            synced["settings"] = "ok"
    except Exception as e:  # noqa: BLE001
        errors["settings"] = str(e)

    # Najnowsze zadanie z chmury (ostatni wgrany plik „rozliczenie" + wyniki),
    # żeby na lokalu było od razu dostępne do podejrzenia / przeliczenia. Bierzemy
    # najnowsze zadanie 'full'; pobieramy tylko jeśli nie mamy go jeszcze lokalnie
    # (dedup po id), więc kolejne synchronizacje nie ściągają go w kółko.
    try:
        jobs = json.loads(_fetch(f"{cloud}/api/jobs", token))
        # Ostatnio wgrany plik = NAJNOWSZE zadanie, niezależnie od trybu (pełne lub
        # „tylko braki wzorca"). Lista z chmury jest malejąco wg daty; pomijamy tylko
        # zadania anulowane (przerwane), bo nie reprezentują realnego wgrania.
        latest = next((j for j in jobs if j.get("status") != "cancelled"), None) or (jobs[0] if jobs else None)
        if latest and latest.get("id"):
            if db.get_job(latest["id"]):
                synced["latest_job"] = None  # już mamy
            else:
                from app.routers.jobs import import_job_bundle
                bundle = _fetch(f"{cloud}/api/jobs/{latest['id']}/bundle", token)
                import_job_bundle(bundle)
                synced["latest_job"] = latest.get("input_name") or latest["id"]
    except Exception as e:  # noqa: BLE001
        errors["latest_job"] = str(e)

    return {"synced": synced, "errors": errors}


@router.post("")
async def sync_from_cloud(payload: dict):
    cloud, token = _resolve_cloud(payload)
    if not cloud:
        raise HTTPException(400, "Brak adresu chmury (TELEDIAG_SYNC_URL lub cloud_base).")
    if cloud.startswith(("http://localhost", "http://127.0.0.1")):
        raise HTTPException(400, "Adres chmury wskazuje na localhost — nie ma skąd synchronizować.")
    return pull_active_from_cloud(cloud, token)


def _build_job_bundle(job_id: str) -> bytes:
    """Pakuje katalog zadania (pliki wejściowe, wyniki, sprawdzone, lekarze, log,
    status) + meta.json do ZIP-a — do wysłania na inny backend."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania.")
    paths = job_paths(job_id)
    meta = {
        "job_id": job_id,
        "mode": job["mode"],
        "input_name": job["input_name"],
        "wzorcowe_version": job.get("wzorcowe_version"),
        "cennik_version": job.get("cennik_version"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))
        for sub in ("jednostki", "wynik", "sprawdzone", "lekarze"):
            d = paths.get(sub) or os.path.join(paths["base"], sub)
            if not os.path.isdir(d):
                continue
            for f in glob.glob(os.path.join(d, "*")):
                if os.path.isfile(f) and not os.path.basename(f).startswith("~$"):
                    zf.write(f, f"{sub}/{os.path.basename(f)}")
        for key in ("log", "status"):
            if os.path.isfile(paths[key]):
                zf.write(paths[key], os.path.basename(paths[key]))
    return buf.getvalue()


@router.post("/push")
async def push_to_cloud(payload: dict):
    """
    Wysyła policzone lokalnie zadanie (wgrany plik + wyniki) do chmury, żeby było
    widoczne online. Wywoływane automatycznie po ukończeniu liczenia „na tym
    komputerze". Transfer serwer→serwer (urllib), więc bez ograniczeń przeglądarki.
    """
    cloud, token = _resolve_cloud(payload)
    job_id = (payload.get("job_id") or "").strip()
    if not cloud or not job_id:
        raise HTTPException(400, "Brak adresu chmury lub job_id.")
    if cloud.startswith(("http://localhost", "http://127.0.0.1")):
        raise HTTPException(400, "Adres chmury wskazuje na localhost — nie ma dokąd wysłać.")

    data = _build_job_bundle(job_id)
    headers = {"Content-Type": "application/zip"}
    if token:
        headers["X-API-Token"] = token
    req = urllib.request.Request(f"{cloud}/api/jobs/import", data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return {"ok": True, "cloud": json.loads(resp.read())}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Nie udało się wysłać do chmury: {e}")


def _build_version_bundle(kind: str, version_id: str) -> bytes:
    """Pakuje katalog wersji (wszystkie pliki: cennik/słownik + ewentualny
    source.xlsx pliku zobowiązań) + meta.json do ZIP-a — do wysłania na chmurę."""
    v = db.get_version(version_id)
    if not v or v["kind"] != kind:
        raise HTTPException(404, "Nie znaleziono wersji.")
    vdir = version_dir(kind, version_id)
    meta = {
        "id": version_id, "kind": kind, "filename": v.get("filename"),
        "original_name": v.get("original_name"), "label": v.get("label"),
        "size": v.get("size"), "uploaded_at": v.get("uploaded_at"),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))
        for f in glob.glob(os.path.join(vdir, "*")):
            if os.path.isfile(f) and not os.path.basename(f).startswith("~$"):
                zf.write(f, os.path.basename(f))
    return buf.getvalue()


@router.post("/push-version")
async def push_version_to_cloud(payload: dict):
    """
    Wysyła wgraną lokalnie wersję pliku (słownik / cennik / cennik lekarzy wraz z
    plikiem zobowiązań) do chmury i ustawia ją tam jako aktywną. Wywoływane
    automatycznie zaraz po wgraniu/zapisaniu pliku „na tym komputerze", żeby ten sam
    plik był od razu widoczny online. Transfer serwer→serwer (bez ograniczeń przeglądarki).
    """
    cloud, token = _resolve_cloud(payload)
    kind = (payload.get("kind") or "").strip()
    version_id = (payload.get("version_id") or "").strip()
    if not cloud or not kind or not version_id:
        raise HTTPException(400, "Brak adresu chmury, kind lub version_id.")
    if cloud.startswith(("http://localhost", "http://127.0.0.1")):
        raise HTTPException(400, "Adres chmury wskazuje na localhost — nie ma dokąd wysłać.")

    data = _build_version_bundle(kind, version_id)
    headers = {"Content-Type": "application/zip"}
    if token:
        headers["X-API-Token"] = token
    req = urllib.request.Request(f"{cloud}/api/versions/{kind}/import", data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return {"ok": True, "cloud": json.loads(resp.read())}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Nie udało się wysłać wersji do chmury: {e}")

