"""
Układ katalogów na wolumenie danych (domyślnie /data).

Struktura:
  /data/app.db                              – baza SQLite
  /data/config.json                         – aktywna konfiguracja silnika
  /data/versions/wzorcowe/<vid>/<plik>      – wersje plików wzorcowych
  /data/versions/cennik/<vid>/<plik>        – wersje cennika
  /data/jobs/<job_id>/...                   – katalog roboczy pojedynczego zadania
"""

import os
import re

DATA_DIR = os.environ.get("TELEDIAG_DATA_DIR", "/data")

# Identyfikatory (wersji, zadań) generujemy jako uuid4().hex[:12], a przy imporcie
# przychodzą z zewnętrznej paczki — muszą być bezpieczne jako nazwa katalogu.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class UnsafePathError(ValueError):
    """Identyfikator nie nadaje się na element ścieżki (próba wyjścia z katalogu)."""


def safe_id(value: str) -> str:
    """Waliduje identyfikator używany jako element ścieżki. Rzuca UnsafePathError, gdy
    zawiera cokolwiek poza [A-Za-z0-9_-] — to blokuje „../" i ścieżki bezwzględne."""
    v = str(value or "").strip()
    if not _SAFE_ID_RE.match(v):
        raise UnsafePathError(f"Niedozwolony identyfikator: {value!r}")
    return v


def safe_filename(name: str, default: str = "plik.dat") -> str:
    """Sprowadza nazwę pliku od klienta do samej nazwy — bez katalogów i bez „..".
    Chroni przed zapisem poza katalogiem docelowym (path traversal)."""
    base = os.path.basename(str(name or "").replace("\\", "/")).strip()
    base = base.lstrip(".") or default          # ".." / ".ukryty" → nie zaczynamy od kropki
    return base[:200]

DB_PATH = os.path.join(DATA_DIR, "app.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
VERSIONS_DIR = os.path.join(DATA_DIR, "versions")
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
TMP_DIR = os.path.join(DATA_DIR, "tmp")


def ensure_dirs():
    for d in [DATA_DIR, VERSIONS_DIR, os.path.join(VERSIONS_DIR, "wzorcowe"),
              os.path.join(VERSIONS_DIR, "cennik"), JOBS_DIR, TMP_DIR]:
        os.makedirs(d, exist_ok=True)


def version_dir(kind: str, version_id: str) -> str:
    # Walidacja w JEDNYM miejscu: każda ścieżka wersji przechodzi tędy, więc żadna
    # trasa nie zbuduje katalogu poza VERSIONS_DIR (nawet gdyby zapomniano sprawdzić id).
    return os.path.join(VERSIONS_DIR, safe_id(kind), safe_id(version_id))


def job_dir(job_id: str) -> str:
    return os.path.join(JOBS_DIR, safe_id(job_id))


# Mapa: nazwa katalogu w STARYCH paczkach ZIP (klucz job_paths) → właściwy katalog
# zadania. Stare paczki (_build_job_bundle) zapisywały pliki pod nazwami-kluczami
# ('jednostki'/'wynik'/'sprawdzone'), a aplikacja czyta z 'Jednostki'/'Wynik'/
# 'pliki_sprawdzone' — przez co zaimportowane zadania miały puste rozliczenie lekarzy.
BUNDLE_DIR_FIX = {"jednostki": "Jednostki", "wynik": "Wynik", "sprawdzone": "pliki_sprawdzone"}


def heal_job_dirs(job_id: str) -> None:
    """Naprawia zadania zaimportowane starą paczką: przenosi pliki z katalogów o złej
    nazwie do właściwych (patrz BUNDLE_DIR_FIX). Idempotentne i tanie — dla zdrowych
    zadań nic nie robi. Wołane przy imporcie oraz przy pierwszym otwarciu (rozliczenie
    lekarzy / porównanie / przychód), by istniejące zepsute zadania też się naprawiły."""
    import glob
    import shutil
    base = job_dir(job_id)
    if not os.path.isdir(base):
        return
    for wrong, right in BUNDLE_DIR_FIX.items():
        wp = os.path.join(base, wrong)
        if not os.path.isdir(wp):
            continue
        rp = os.path.join(base, right)
        os.makedirs(rp, exist_ok=True)
        for f in glob.glob(os.path.join(wp, "*")):
            dest = os.path.join(rp, os.path.basename(f))
            if not os.path.exists(dest):
                try:
                    shutil.move(f, dest)
                except OSError:
                    pass
        try:
            if not os.listdir(wp):
                os.rmdir(wp)
        except OSError:
            pass


def job_paths(job_id: str) -> dict:
    base = job_dir(job_id)
    return {
        "base": base,
        "jednostki": os.path.join(base, "Jednostki"),
        "wzorcowe": os.path.join(base, "pliki_wzorcowe"),
        "cennik": os.path.join(base, "Cennik"),
        "sprawdzone": os.path.join(base, "pliki_sprawdzone"),
        "wynik": os.path.join(base, "Wynik"),
        "log": os.path.join(base, "log.txt"),
        "status": os.path.join(base, "status.json"),
        "config": os.path.join(base, "config.json"),
    }
