"""
Entrypoint rozliczenia LEKARZY jako osobny proces (analogicznie do app.run_job):

    python -m app.run_doctors <job_id>

Osobny proces, bo liczenie lekarzy (osobny plik Excel per lekarz) bywa ciężkie i
synchroniczne — w handlerze HTTP blokowałoby pętlę async serwera, a długie żądanie
bywało zrywane przez proxy Fly. Tu: keep-alive trzyma maszynę obudzoną, a status i
log lecą do plików (front odpytuje o status).
"""

import os
import sys
import datetime
import traceback


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def main():
    job_id = sys.argv[1]

    from app.storage import job_paths
    paths = job_paths(job_id)

    # Konfiguracja silnika dla tego zadania — PRZED importem silnika (jak run_job).
    os.environ["TELEDIAG_CONFIG"] = paths["config"]

    from app.services.doctors_job import log_path, write_status, read_status, compute

    log_file = open(log_path(paths), "a", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file

    # Keep-alive współdzielony z głównym zadaniem (Fly scale-to-zero).
    from app.run_job import _start_keepalive
    keepalive = _start_keepalive()

    # Zachowaj started_at/pid ustawione przez proces-rodzica (services.doctors_job.start).
    st = read_status(paths)
    st["status"] = "running"
    write_status(paths, st)

    try:
        compute(job_id)
        st["status"] = "done"
        st["error"] = None
    except Exception as e:  # noqa: BLE001
        st["status"] = "error"
        st["error"] = str(e)
        print(f"\n\nKRYTYCZNY BŁĄD ROZLICZENIA LEKARZY: {e}", flush=True)
        traceback.print_exc(file=log_file)
    finally:
        keepalive.set()
        st["finished_at"] = _now()
        write_status(paths, st)
        log_file.flush()
        log_file.close()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
