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
from app.storage import version_dir, ensure_dirs, safe_id, safe_filename

router = APIRouter(prefix="/api/versions", tags=["versions"])

KINDS = {
    "wzorcowe": (".xlsx", ".xls"),
    "cennik": (".csv",),
    "cennik_lekarzy": (".csv",),
}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _vid(version_id: str) -> str:
    """Identyfikator wersji jako bezpieczny element ścieżki (inaczej 404)."""
    try:
        return safe_id(version_id)
    except ValueError:
        raise HTTPException(404, "Nie znaleziono wersji.")


@router.get("/{kind}")
async def list_versions(kind: str):
    if kind not in KINDS:
        raise HTTPException(404, "Nieznany rodzaj plików.")
    return db.list_versions(kind)


@router.post("/{kind}")
async def upload_version(kind: str, request: Request, file: UploadFile = File(...), label: str = Form("")):
    if kind not in KINDS:
        raise HTTPException(404, "Nieznany rodzaj plików.")
    # Nazwa pliku pochodzi od klienta — sprowadzamy ją do samej nazwy (bez katalogów
    # i „..") ZANIM zbudujemy z niej ścieżkę zapisu.
    filename = safe_filename(file.filename)
    if not filename.lower().endswith(KINDS[kind]):
        raise HTTPException(400, f"Dozwolone rozszerzenia: {', '.join(KINDS[kind])}")

    ensure_dirs()
    version_id = uuid.uuid4().hex[:12]
    vdir = version_dir(kind, version_id)
    os.makedirs(vdir, exist_ok=True)

    dest = os.path.join(vdir, filename)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    # Pierwsza wgrana wersja danego rodzaju zostaje automatycznie aktywna
    make_active = db.get_active_version(kind) is None

    db.add_version({
        "id": version_id,
        "kind": kind,
        "filename": filename,
        "original_name": filename,
        "label": label or "",
        "size": len(content),
        "is_active": 1 if make_active else 0,
        "uploaded_at": _now(),
        "uploaded_by": getattr(request.state, "username", None),
    })
    return db.get_version(version_id)


@router.post("/wzorcowe/append")
async def append_wzorcowe(request: Request, file: UploadFile = File(...), label: str = Form("")):
    """Doklejenie DODATKOWEGO słownika do wersji aktywnej (zamiast wgrywania całości).

    Powstaje NOWA wersja (aktywna), a poprzednia zostaje w historii — cofnięcie to
    kwestia kliknięcia „Ustaw jako aktywną" na starej pozycji. Reguła: wiersze z
    dosyłki idą na koniec, a powtórzone klucze (Procedura + Rodzaj procedury
    rozlicz.) zastępują stare wpisy. Szczegóły w engine/slownik_merge.py.
    """
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Dosyłany słownik musi być plikiem Excel (.xlsx lub .xls).")
    active = db.get_active_version("wzorcowe")
    if not active:
        raise HTTPException(400, "Brak aktywnego słownika — najpierw wgraj pełną wersję.")
    src = os.path.join(version_dir("wzorcowe", active["id"]), active["filename"])
    if not os.path.isfile(src):
        raise HTTPException(404, "Plik aktywnego słownika nie istnieje na dysku.")

    from app.engine.slownik_merge import merge_reference
    content = await file.read()
    try:
        res = merge_reference(src, content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Nie udało się scalić słowników: {e}")

    ensure_dirs()
    version_id = uuid.uuid4().hex[:12]
    vdir = version_dir("wzorcowe", version_id)
    os.makedirs(vdir, exist_ok=True)
    filename = active["filename"]
    if not filename.lower().endswith(".xlsx"):
        filename = os.path.splitext(filename)[0] + ".xlsx"   # wynik zapisujemy jako .xlsx
    with open(os.path.join(vdir, filename), "wb") as out:
        out.write(res["content"])

    st = res["stats"]
    base_label = (active.get("label") or os.path.splitext(active["filename"])[0] or "Słownik").strip()
    auto = f"{base_label} + dosyłka {os.path.basename(file.filename)}"
    db.add_version({
        "id": version_id, "kind": "wzorcowe", "filename": filename,
        "original_name": filename, "label": (label or auto)[:300],
        "size": len(res["content"]), "is_active": 0, "uploaded_at": _now(),
        "uploaded_by": getattr(request.state, "username", None),
    })
    db.set_active_version("wzorcowe", version_id)
    return {**(db.get_version(version_id) or {}), "merge": st,
            "base_version_id": active["id"]}


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

    # id z paczki staje się nazwą katalogu — musi przejść walidację (blokuje „../").
    try:
        version_id = safe_id(meta.get("id"))
    except ValueError:
        raise HTTPException(400, "Niedozwolone id wersji w paczce.")
    if meta.get("kind") != kind:
        raise HTTPException(400, "Niezgodny kind w paczce.")

    ensure_dirs()
    vdir = version_dir(kind, version_id)
    os.makedirs(vdir, exist_ok=True)
    for name in zf.namelist():
        if name == "meta.json" or name.endswith("/"):
            continue
        # Ochrona przed zip-slip: bierzemy wyłącznie samą nazwę pliku, więc żaden wpis
        # nie może wyjść poza katalog wersji (ani ścieżką względną, ani bezwzględną).
        entry = safe_filename(name)
        if not entry:
            continue
        target = os.path.join(vdir, entry)
        with open(target, "wb") as f:
            f.write(zf.read(name))

    if not db.get_version(version_id):
        db.add_version({
            "id": version_id, "kind": kind,
            "filename": safe_filename(meta.get("filename")),
            "original_name": safe_filename(meta.get("original_name") or meta.get("filename")),
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
    # basename także tutaj — starsze rekordy w bazie mogą pochodzić sprzed sanityzacji.
    path = os.path.join(version_dir(kind, _vid(version_id)), safe_filename(v["filename"]))
    if not os.path.isfile(path):
        raise HTTPException(404, "Plik nie istnieje na dysku.")
    return FileResponse(path, filename=safe_filename(v["original_name"]))


@router.get("/{kind}/{version_id}/source")
async def download_version_source(kind: str, version_id: str):
    """Źródłowy skoroszyt .xlsx zapisany przy wersji — dla cennika lekarzy to „plik
    zobowiązań" (do uzupełniania ilości okolic w paczce rozliczeń lekarzy). 404 gdy
    wersji nie zapisano z .xlsx. Używane przy synchronizacji lokal ← chmura, żeby
    liczenie „na tym komputerze" też dołączało zobowiązania do ZIP-a."""
    v = db.get_version(version_id)
    if not v or v["kind"] != kind:
        raise HTTPException(404, "Nie znaleziono wersji.")
    vdir = version_dir(kind, _vid(version_id))
    path = os.path.join(vdir, "source.xlsx")
    if not os.path.isfile(path):
        raise HTTPException(404, "Ta wersja nie ma zapisanego źródłowego pliku .xlsx.")
    name = "ZOBOWIĄZANIA LEKARZY.xlsx"
    nf = os.path.join(vdir, "source_name.txt")
    if os.path.isfile(nf):
        try:
            name = open(nf, encoding="utf-8").read().strip() or name
        except OSError:
            pass
    return FileResponse(path, filename=name)


@router.delete("/{kind}/{version_id}")
async def delete_version(kind: str, version_id: str):
    v = db.get_version(version_id)
    if not v or v["kind"] != kind:
        raise HTTPException(404, "Nie znaleziono wersji.")
    if v["is_active"]:
        raise HTTPException(400, "Nie można usunąć aktywnej wersji. Najpierw aktywuj inną.")
    shutil.rmtree(version_dir(kind, _vid(version_id)), ignore_errors=True)
    db.delete_version(version_id)
    return {"ok": True}
