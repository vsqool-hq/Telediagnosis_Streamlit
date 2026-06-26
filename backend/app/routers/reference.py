"""
Obrazki-wzory (referencyjne) dla miejsc wgrywania plików.

Administrator wgrywa raz przykładowy obrazek (zrzut ekranu) pod dany slot, a
osoba zastępująca widzi miniaturkę i po kliknięciu powiększenie na cały ekran —
dzięki temu wie, jaki plik wgrać w danym miejscu. Jeden obrazek na slot
(ponowne wgranie nadpisuje). Pliki leżą na wolumenie danych (/data).
"""

import os
import glob

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.storage import DATA_DIR

router = APIRouter(prefix="/api/reference-image", tags=["reference"])

SLOTS = {"wzorcowe", "cennik", "cennik_lekarzy", "rozliczenie"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MEDIA = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif",
}
REF_DIR = os.path.join(DATA_DIR, "reference_images")


def _existing(slot: str):
    found = glob.glob(os.path.join(REF_DIR, f"{slot}.*"))
    return found[0] if found else None


@router.get("")
async def list_reference_images():
    """Mapa slot → rozszerzenie obrazka (albo null, gdy brak)."""
    return {s: (os.path.splitext(_existing(s))[1] if _existing(s) else None) for s in SLOTS}


@router.post("/{slot}")
async def upload_reference_image(slot: str, file: UploadFile = File(...)):
    if slot not in SLOTS:
        raise HTTPException(404, "Nieznany slot.")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in IMG_EXT:
        raise HTTPException(400, f"Dozwolone obrazy: {', '.join(sorted(IMG_EXT))}")
    os.makedirs(REF_DIR, exist_ok=True)
    for old in glob.glob(os.path.join(REF_DIR, f"{slot}.*")):
        try:
            os.remove(old)
        except OSError:
            pass
    content = await file.read()
    with open(os.path.join(REF_DIR, f"{slot}{ext}"), "wb") as f:
        f.write(content)
    return {"ok": True, "slot": slot, "ext": ext}


@router.get("/{slot}")
async def get_reference_image(slot: str):
    if slot not in SLOTS:
        raise HTTPException(404, "Nieznany slot.")
    path = _existing(slot)
    if not path:
        raise HTTPException(404, "Brak obrazka.")
    return FileResponse(path, media_type=MEDIA.get(os.path.splitext(path)[1].lower(), "application/octet-stream"))


@router.delete("/{slot}")
async def delete_reference_image(slot: str):
    if slot not in SLOTS:
        raise HTTPException(404, "Nieznany slot.")
    for old in glob.glob(os.path.join(REF_DIR, f"{slot}.*")):
        try:
            os.remove(old)
        except OSError:
            pass
    return {"ok": True}
