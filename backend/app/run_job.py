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


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


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
