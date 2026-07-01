"""Router wersjonowania plików wzorcowych i cennika."""

import os
import io
import json
import uuid
import shutil
import zipfile
import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse

from app import db
from app.storage import version_dir, ensure_dirs

router = APIRouter(prefix="/api/versions", tags=["versions"])

KINDS = {
    "wzorcowe": (".xlsx", ".xls"),
    "cennik": (".csv",),
    "cennik_lekarzy": (".csv",),
}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


@router.get("/{kind}")
async def list_versions(kind: str):
    if kind not in KINDS:
        raise HTTPException(404, "Nieznany rodzaj plików.")
    return db.list_versions(kind)


@router.post("/{kind}")
async def upload_version(kind: str, file: UploadFile = File(...), label: str = Form("")):
    if kind not in KINDS:
        raise HTTPException(404, "Nieznany rodzaj plików.")
    if not file.filename.lower().endswith(KINDS[kind]):
        raise HTTPException(400, f"Dozwolone rozszerzenia: {', '.join(KINDS[kind])}")

    ensure_dirs()
    version_id = uuid.uuid4().hex[:12]
    vdir = version_dir(kind, version_id)
    os.makedirs(vdir, exist_ok=True)

    dest = os.path.join(vdir, file.filename)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    # Pierwsza wgrana wersja danego rodzaju zostaje automatycznie aktywna
    make_active = db.get_active_version(kind) is None

    db.add_version({
        "id": version_id,
        "kind": kind,
        "filename": file.filename,
        "original_name": file.filename,
        "label": label or "",
        "size": len(content),
        "is_active": 1 if make_active else 0,
        "uploaded_at": _now(),
    })
    return db.get_version(version_id)


@router.post("/{kind}/import")
async def import_version(kind: str, request: Request):
    """Odbiera wersję z innego backendu (bundle ZIP: pliki katalogu wersji +
    meta.json) — używane przy auto-synchronizacji lokal → chmura zaraz po wgraniu
    pliku „na tym komputerze". Idempotentne po id; zawiera też source.xlsx (plik
    zobowiązań) dla cennika lekarzy. Wgrana wersja staje się aktywna."""
    if kind not in KINDS:
        raise HTTPException(404, "Nieznany rodzaj plików.")
    raw = await request.body()
    if not raw:
        raise HTTPException(400, "Puste żądanie.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        meta = json.loads(zf.read("meta.json"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Nieprawidłowa paczka wersji: {e}")

    version_id = str(meta.get("id") or "").strip()
    if not version_id or meta.get("kind") != kind:
        raise HTTPException(400, "Brak lub niezgodny id/kind w paczce.")

    ensure_dirs()
    vdir = version_dir(kind, version_id)
    os.makedirs(vdir, exist_ok=True)
    for name in zf.namelist():
        if name == "meta.json" or name.endswith("/"):
            continue
        if name.startswith("/") or ".." in name.split("/"):  # ochrona przed zip-slip
            continue
        target = os.path.join(vdir, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(zf.read(name))

    if not db.get_version(version_id):
        db.add_version({
            "id": version_id, "kind": kind,
            "filename": meta.get("filename"),
            "original_name": meta.get("original_name") or meta.get("filename"),
            "label": meta.get("label") or "",
            "size": int(meta.get("size") or 0),
            "is_active": 0,
            "uploaded_at": meta.get("uploaded_at") or _now(),
        })
    db.set_active_version(kind, version_id)
    return {"ok": True, "id": version_id}


@router.post("/{kind}/{version_id}/activate")
async def activate_version(kind: str, version_id: str):
    if kind not in KINDS:
        raise HTTPException(404, "Nieznany rodzaj plików.")
    v = db.get_version(version_id)
    if not v or v["kind"] != kind:
        raise HTTPException(404, "Nie znaleziono wersji.")
    db.set_active_version(kind, version_id)
    return {"ok": True, "active": version_id}


@router.get("/{kind}/{version_id}/download")
async def download_version(kind: str, version_id: str):
    v = db.get_version(version_id)
    if not v or v["kind"] != kind:
        raise HTTPException(404, "Nie znaleziono wersji.")
    path = os.path.join(version_dir(kind, version_id), v["filename"])
    if not os.path.isfile(path):
        raise HTTPException(404, "Plik nie istnieje na dysku.")
    return FileResponse(path, filename=v["original_name"])


@router.delete("/{kind}/{version_id}")
async def delete_version(kind: str, version_id: str):
    v = db.get_version(version_id)
    if not v or v["kind"] != kind:
        raise HTTPException(404, "Nie znaleziono wersji.")
    if v["is_active"]:
        raise HTTPException(400, "Nie można usunąć aktywnej wersji. Najpierw aktywuj inną.")
    shutil.rmtree(version_dir(kind, version_id), ignore_errors=True)
    db.delete_version(version_id)
    return {"ok": True}
