"""
Router konwertera cennika zbiorczego (szeroki Excel → cennik 3-kolumnowy).

Przepływ:
  1. POST /api/cennik/convert  — wgranie Excela; konwersja + walidacja; wynik
     zapisywany tymczasowo, zwracany podgląd i raport.
  2. GET  /api/cennik/convert/{id}/download — pobranie wynikowego CSV.
  3. POST /api/cennik/convert/{id}/save — zapis wyniku jako nowej wersji cennika.
"""

import os
import io
import uuid
import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

from app import db
from app.storage import TMP_DIR, ensure_dirs, version_dir
from app.engine.cennik_convert import convert_workbook, rows_to_csv

router = APIRouter(prefix="/api/cennik", tags=["cennik"])


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _tmp_path(conv_id: str) -> str:
    return os.path.join(TMP_DIR, f"{conv_id}.csv")


@router.post("/convert")
async def convert(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Wgraj plik Excel (.xlsx lub .xls).")
    ensure_dirs()
    content = await file.read()

    try:
        result = convert_workbook(io.BytesIO(content))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Nie udało się przetworzyć pliku: {e}")

    if not result["rows"]:
        raise HTTPException(400, "Nie znaleziono żadnych cen w pliku. Sprawdź układ arkusza.")

    conv_id = uuid.uuid4().hex[:12]
    csv_text = rows_to_csv(result["rows"])
    with open(_tmp_path(conv_id), "w", encoding="utf-8") as f:
        f.write(csv_text)

    result_preview = [
        {"badanie": b, "jednostka": j, "cena": p} for b, j, p in result["rows"][:50]
    ]

    return {
        "id": conv_id,
        "source_name": file.filename,
        "source_preview": result["source_preview"],
        "result_preview": result_preview,
        "validation": result["validation"],
    }


@router.get("/convert/{conv_id}/download")
async def download_converted(conv_id: str):
    path = _tmp_path(conv_id)
    if not os.path.isfile(path):
        raise HTTPException(404, "Wynik konwersji wygasł. Wgraj plik ponownie.")
    return FileResponse(path, filename="Cennik.csv", media_type="text/csv")


@router.post("/convert/{conv_id}/save")
async def save_converted(conv_id: str, label: str = Form(""), filename: str = Form("Cennik.csv")):
    path = _tmp_path(conv_id)
    if not os.path.isfile(path):
        raise HTTPException(404, "Wynik konwersji wygasł. Wgraj plik ponownie.")

    if not filename.lower().endswith(".csv"):
        filename = "Cennik.csv"

    version_id = uuid.uuid4().hex[:12]
    vdir = version_dir("cennik", version_id)
    os.makedirs(vdir, exist_ok=True)
    dest = os.path.join(vdir, filename)

    with open(path, "rb") as src, open(dest, "wb") as out:
        data = src.read()
        out.write(data)

    make_active = db.get_active_version("cennik") is None
    db.add_version({
        "id": version_id, "kind": "cennik", "filename": filename,
        "original_name": filename, "label": label or "Z konwersji cennika zbiorczego",
        "size": len(data), "is_active": 1 if make_active else 0, "uploaded_at": _now(),
    })

    # sprzątanie tymczasowego pliku
    try:
        os.remove(path)
    except OSError:
        pass

    return db.get_version(version_id)


@router.post("/apply-additions")
async def apply_additions(payload: dict):
    """Dopisuje zatwierdzone pozycje (jednostka, badanie, kwota) do AKTYWNEGO cennika,
    tworząc jego KOPIĘ jako nową wersję z dopiskiem „(aneks RRRR-MM-DD)" i aktywując ją.
    Pozycje pochodzą z propozycji generatora (luki wyrażone kwotą w ZOBOWIĄZANIACH)."""
    additions = payload.get("additions", [])
    if not isinstance(additions, list) or not additions:
        raise HTTPException(400, "Brak pozycji do dodania.")
    active = db.get_active_version("cennik")
    if not active:
        raise HTTPException(400, "Brak aktywnej wersji cennika — nie ma czego kopiować.")
    src = os.path.join(version_dir("cennik", active["id"]), active["filename"])
    if not os.path.isfile(src):
        raise HTTPException(404, "Plik aktywnego cennika nie istnieje.")

    with open(src, encoding="utf-8-sig") as f:
        text = f.read()
    if text and not text.endswith("\n"):
        text += "\n"

    lines = []
    for a in additions:
        unit = str(a.get("unit", "")).strip().replace(";", " ").replace("\n", " ")
        key = str(a.get("key", "")).strip().replace(";", " ").replace("\n", " ")
        try:
            amt = float(a.get("amount"))
        except (TypeError, ValueError):
            continue
        if not unit or not key or amt <= 0:
            continue
        cena = str(int(amt)) if amt == int(amt) else ("%g" % amt).replace(".", ",")
        lines.append(f"{key};{unit};{cena}")
    if not lines:
        raise HTTPException(400, "Brak poprawnych pozycji do dodania.")

    text += "\n".join(lines) + "\n"
    data = text.encode("utf-8-sig")

    version_id = uuid.uuid4().hex[:12]
    vdir = version_dir("cennik", version_id)
    os.makedirs(vdir, exist_ok=True)
    filename = active["filename"]
    with open(os.path.join(vdir, filename), "wb") as out:
        out.write(data)

    today = datetime.date.today().isoformat()
    base_label = (active.get("label") or os.path.splitext(filename)[0] or "Cennik").strip()
    label = f"{base_label} (aneks {today})"
    db.add_version({
        "id": version_id, "kind": "cennik", "filename": filename,
        "original_name": filename, "label": label,
        "size": len(data), "is_active": 1, "uploaded_at": _now(),
    })
    db.set_active_version("cennik", version_id)
    return {"version": db.get_version(version_id), "added": len(lines)}
