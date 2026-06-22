"""
Seedowanie danych startowych: jeśli nie ma jeszcze żadnej wersji plików
wzorcowych / cennika, a w katalogu seed_data są pliki przykładowe, importuje
je jako pierwszą (aktywną) wersję. Uruchamiane przy starcie aplikacji.
"""

import os
import json
import uuid
import glob
import shutil
import datetime

from app import db
from app.storage import version_dir, ensure_dirs

# katalog seed_data leży w korzeniu repo, dwa poziomy nad app/
SEED_DIR = os.environ.get(
    "TELEDIAG_SEED_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "seed_data"),
)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _seed_kind(kind: str, patterns: list[str]):
    if db.list_versions(kind):
        return
    files: list[str] = []
    for pat in patterns:
        files += glob.glob(os.path.join(SEED_DIR, pat))
    if not files:
        return
    src = files[0]
    name = os.path.basename(src)
    version_id = uuid.uuid4().hex[:12]
    vdir = version_dir(kind, version_id)
    os.makedirs(vdir, exist_ok=True)
    shutil.copy2(src, os.path.join(vdir, name))
    db.add_version({
        "id": version_id, "kind": kind, "filename": name, "original_name": name,
        "label": "Wersja startowa (seed)", "size": os.path.getsize(src),
        "is_active": 1, "uploaded_at": _now(),
    })
    print(f"[seed] Zaimportowano startową wersję '{kind}': {name}", flush=True)


def load_seed_adjustments() -> dict:
    """Wczytuje startowe współczynniki cen jednostek z seed_data/unit_adjustments.json."""
    path = os.path.join(SEED_DIR, "unit_adjustments.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def seed_adjustments_if_absent():
    """
    Jednorazowo wczytuje współczynniki (adjustmenty) cen jednostek do ustawień, jeśli
    klucza 'unit_adjustments' jeszcze tam nie ma. Dzięki temu istniejąca baza w chmurze
    zostaje wypełniona przy najbliższym starcie, a późniejsze edycje/usuwanie z panelu
    Ustawienia są trwałe (klucz już istnieje → nie nadpisujemy).
    """
    settings = db.get_settings()
    if "unit_adjustments" in settings:
        return
    seed = load_seed_adjustments()
    if not seed:
        return
    settings["unit_adjustments"] = seed
    db.save_settings(settings)
    total = sum(len(v) for v in seed.values() if isinstance(v, dict))
    print(f"[seed] Wczytano startowe współczynniki cen: {len(seed)} jednostek, {total} reguł.", flush=True)


def seed_if_empty():
    if not os.path.isdir(SEED_DIR):
        return
    ensure_dirs()
    _seed_kind("wzorcowe", ["*.xlsx", "*.xls"])
    _seed_kind("cennik", ["*.csv"])
    seed_adjustments_if_absent()
