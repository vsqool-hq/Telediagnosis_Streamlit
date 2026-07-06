"""
Rozliczenie LEKARZY jako zadanie w tle (analogicznie do głównego rozliczenia).

Powód: liczenie lekarzy bywa ciężkie (osobny plik Excel per lekarz). Robione
synchronicznie w handlerze HTTP blokowało pętlę async jedynego workera uvicorn,
a długie „ciche" żądanie bywało zrywane przez proxy Fly (front: „failed to fetch").

Dlatego liczymy w OSOBNYM procesie `python -m app.run_doctors <job_id>` (jak
app.run_job), z keep-alive (maszyna nie uśnie) i statusem w pliku — front tylko
odpytuje o status, zamiast czekać na jedno długie żądanie.

Status:  <base>/lekarze/billing_status.json
Log:     <base>/lekarze/billing_log.txt
Wynik:   <base>/lekarze/billing.json  (ten sam cache co dotąd)
"""

import os
import sys
import json
import datetime
import subprocess

from app.storage import job_paths


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _lekarze_dir(paths: dict) -> str:
    d = os.path.join(paths["base"], "lekarze")
    os.makedirs(d, exist_ok=True)
    return d


def status_path(paths: dict) -> str:
    return os.path.join(_lekarze_dir(paths), "billing_status.json")


def log_path(paths: dict) -> str:
    return os.path.join(_lekarze_dir(paths), "billing_log.txt")


def write_status(paths: dict, st: dict):
    try:
        with open(status_path(paths), "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
    except OSError:
        pass


def read_status(paths: dict) -> dict:
    p = status_path(paths)
    if not os.path.isfile(p):
        return {"status": "idle"}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"status": "idle"}


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def compute(job_id: str) -> dict:
    """
    Ciężkie liczenie rozliczenia lekarzy — wołane z app.run_doctors (osobny proces).
    Resolve job + build_doctor_billing + generowanie plików Excel + zapis cache.
    """
    # Import leniwy — unika cyklu (router importuje ten moduł).
    from app.routers.doctors import (
        _resolve_job, _excluded_keys, _save_cache, _now as _rnow,
    )
    from app.engine.doctors import build_doctor_billing, generate_doctor_billing_files

    _job, paths, slownik, cennik_lek = _resolve_job(job_id)
    excluded = _excluded_keys()
    print(f"Liczę rozliczenie lekarzy (zadanie {job_id})…", flush=True)
    result = build_doctor_billing(paths["sprawdzone"], slownik, cennik_lek, excluded_keys=excluded)
    if not result.get("empty"):
        # Miesiąc do nazw plików lekarzy — z nazwy pliku wejściowego (− 1 mies.).
        from app.engine.periods import period_from_filename, period_to_mmyyyy
        period_ym = period_from_filename((_job or {}).get("input_name"))  # "YYYY-MM"
        period_mm = period_to_mmyyyy(period_ym) or None
        pliki_dir = os.path.join(_lekarze_dir(paths), "pliki")

        # Gotowość + triaż z TeamUp (godziny × stawki z pliku ZOBOWIĄZAŃ).
        # Brak konfiguracji/API nie blokuje rozliczenia — tylko notka w wyniku.
        availability = None
        if period_ym:
            try:
                from app.engine.teamup import compute_availability
                availability = compute_availability(period_ym)
                result["availability"] = availability
                print(f"✓ TeamUp {period_ym}: gotowość {availability['sum_gotowosc']} zł, "
                      f"triaż {availability['sum_triaz']} zł, lekarzy {len(availability['doctors'])}"
                      + (f", NIEDOPASOWANE tytuły: {len(availability['unmatched'])}"
                         if availability["unmatched"] else ""), flush=True)
            except RuntimeError as e:
                result["availability_error"] = str(e)
                print(f"! TeamUp — pominięto: {e}", flush=True)
        try:
            gen = generate_doctor_billing_files(
                paths["sprawdzone"], slownik, cennik_lek,
                pliki_dir, excluded_keys=excluded,
                period_mmyyyy=period_mm,
            )
            result["files_count"] = gen["count"]
            print(f"✓ Wygenerowano plików lekarzy: {gen['count']}.", flush=True)
        except Exception as e:  # noqa: BLE001
            result["files_count"] = 0
            result["files_error"] = str(e)
            print(f"! Pliki lekarzy — błąd generowania: {e}", flush=True)

        # Plik zobowiązań: uzupełnij ilości okolic dla tego miesiąca (kumulatywnie)
        # i dołóż jego kopię do paczki (katalog pliki/ → trafia do ZIP-a).
        try:
            from app.engine.commitments import active_commitments_workbook, fill_and_package
            wb_path, disp = active_commitments_workbook()
            if not wb_path:
                print("! Plik zobowiązań: brak — wgraj cennik lekarzy jako .xlsx przez konwerter.", flush=True)
            elif not period_ym:
                print("! Plik zobowiązań: nie rozpoznano miesiąca z nazwy pliku — pomijam.", flush=True)
            else:
                rep = fill_and_package(
                    wb_path, period_ym, result.get("category_okolice", []),
                    pliki_dir, disp, daily_rows=result.get("category_okolice_daily", []),
                )
                result["commitments"] = rep
                msg = (f"✓ Plik zobowiązań uzupełniony ({period_ym}): lekarzy {rep['doctors_written']}, "
                       f"komórek {rep['cells_written']} → {rep.get('package_file')}")
                if rep.get("split_doctors"):
                    msg += f"; miesiące rozbite aneksem: {len(rep['split_doctors'])}"
                if rep.get("split_unallocated"):
                    msg += f"; ⚠ nierozdzielone pozycje: {len(rep['split_unallocated'])}"
                print(msg, flush=True)
        except Exception as e:  # noqa: BLE001
            result["commitments_error"] = str(e)
            print(f"! Plik zobowiązań — błąd: {e}", flush=True)

        result["computed_at"] = _rnow()
        result["_excluded_keys"] = excluded
        _save_cache(paths, "billing.json", result)
    v = result.get("validation", {})
    print(f"✓ Gotowe. Wycenione badania: {v.get('priced_studies', '?')}/{v.get('total_studies', '?')}.", flush=True)
    return result


def _spawn(job_id: str) -> subprocess.Popen:
    """Odpala `python -m app.run_doctors <job_id>` w tle (jak services.runner._spawn)."""
    paths = job_paths(job_id)
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../app
    backend_root = os.path.dirname(app_dir)                               # kontener pakietu `app`
    err_log = open(log_path(paths), "a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.run_doctors", job_id],
        cwd=backend_root,
        stdout=err_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    err_log.close()
    return proc


def start(job_id: str, recompute: bool = False) -> dict:
    """
    Uruchamia liczenie lekarzy w tle (jeśli jeszcze nie trwa). Zwraca:
      {"status": "running"}                         — wystartowano / już trwa,
      {"status": "done", "computed_at": ...}        — był ważny cache (bez recompute).
    """
    from app.routers.doctors import _load_cache, _excluded_keys

    paths = job_paths(job_id)

    st = read_status(paths)
    if st.get("status") == "running" and _pid_alive(st.get("pid")):
        return {"status": "running"}

    if not recompute:
        cached = _load_cache(paths, "billing.json")
        if cached is not None and cached.get("_excluded_keys", []) == _excluded_keys():
            return {"status": "done", "computed_at": cached.get("computed_at")}

    # świeży log + status running (pid dopiszemy po starcie procesu)
    open(log_path(paths), "w", encoding="utf-8").close()
    write_status(paths, {"status": "running", "started_at": _now(),
                         "finished_at": None, "error": None, "pid": None})
    proc = _spawn(job_id)
    write_status(paths, {"status": "running", "started_at": _now(),
                         "finished_at": None, "error": None, "pid": proc.pid})
    return {"status": "running"}


def status(job_id: str) -> dict:
    """
    Status liczenia do odpytywania przez front. Wykrywa przerwanie procesu
    (np. restart maszyny): status 'running' z martwym pid → 'error'.
    """
    paths = job_paths(job_id)
    st = read_status(paths)
    if st.get("status") == "running" and st.get("pid") is not None and not _pid_alive(st.get("pid")):
        st = {"status": "error", "started_at": st.get("started_at"),
              "finished_at": _now(),
              "error": "Liczenie zostało przerwane (restart serwera). Kliknij ponownie."}
        write_status(paths, st)
    return st
