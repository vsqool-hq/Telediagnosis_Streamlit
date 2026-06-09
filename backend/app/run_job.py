"""
Entrypoint pojedynczego zadania liczącego, uruchamiany jako osobny proces:

    python -m app.run_job <job_id> <full|unmatched>

Działa w osobnym procesie celowo:
  * izoluje multiprocessing.Pool od serwera FastAPI (brak konfliktu z pętlą async),
  * pozwala czysto przechwycić stdout (silnik loguje przez print(..., flush=True)),
  * pojedyncza awaria nie ubija API.

Cały stdout/stderr leci do pliku log.txt zadania; status zapisywany jest do status.json.
"""

import os
import sys
import json
import datetime
import traceback
import threading


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _start_keepalive() -> threading.Event:
    """
    Utrzymuje maszynę „obudzoną" na czas liczenia (Fly scale-to-zero usypia maszynę,
    gdy przez kilka minut nie ma połączeń). Co ~50 s wykonujemy żądanie HTTP na
    PUBLICZNY adres aplikacji — przechodzi ono przez proxy Fly i resetuje licznik
    bezczynności, więc zadanie nie zostanie przerwane, nawet gdy nikt nie patrzy.

    Adres bierzemy z TELEDIAG_PUBLIC_URL, a w razie braku budujemy z FLY_APP_NAME
    (ustawiane automatycznie na Fly.io). Lokalnie (brak obu) wątek nic nie robi.
    """
    stop = threading.Event()
    base = os.environ.get("TELEDIAG_PUBLIC_URL", "").strip().rstrip("/")
    if not base:
        app_name = os.environ.get("FLY_APP_NAME", "").strip()
        if app_name:
            base = f"https://{app_name}.fly.dev"
    if not base:
        return stop  # lokalnie — keep-alive niepotrzebny

    url = base + "/health"

    def _loop():
        import urllib.request
        while not stop.wait(50):
            try:
                urllib.request.urlopen(url, timeout=10).read()
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=_loop, daemon=True).start()
    return stop


def main():
    job_id = sys.argv[1]
    mode = sys.argv[2]

    # Importy storage są bezpieczne (nie ciągną silnika/pandas)
    from app.storage import job_paths

    paths = job_paths(job_id)

    # Konfiguracja silnika dla tego zadania — ustawiamy PRZED importem silnika.
    os.environ["TELEDIAG_CONFIG"] = paths["config"]

    # Przekierowanie całego wyjścia do pliku logu.
    log_file = open(paths["log"], "a", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file

    keepalive = _start_keepalive()

    status = {"status": "running", "started_at": _now(), "finished_at": None, "error": None}
    _write_status(paths["status"], status)

    try:
        # Import silnika po ustawieniu TELEDIAG_CONFIG
        from app.engine import billing

        if mode == "full":
            billing.main(
                paths["jednostki"], paths["wzorcowe"], paths["cennik"],
                paths["wynik"], paths["sprawdzone"],
            )
        elif mode == "unmatched":
            billing.run_unmatched_only(
                paths["jednostki"], paths["wzorcowe"], paths["sprawdzone"],
            )
        else:
            raise ValueError(f"Nieznany tryb: {mode}")

        status["status"] = "done"
    except Exception as e:  # noqa: BLE001
        status["status"] = "error"
        status["error"] = str(e)
        print(f"\n\nKRYTYCZNY BŁĄD ZADANIA: {e}", flush=True)
        traceback.print_exc(file=log_file)
    finally:
        keepalive.set()
        status["finished_at"] = _now()
        _write_status(paths["status"], status)
        log_file.flush()
        log_file.close()


def _write_status(path, status):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
