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

DATA_DIR = os.environ.get("TELEDIAG_DATA_DIR", "/data")

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
    return os.path.join(VERSIONS_DIR, kind, version_id)


def job_dir(job_id: str) -> str:
    return os.path.join(JOBS_DIR, job_id)


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
