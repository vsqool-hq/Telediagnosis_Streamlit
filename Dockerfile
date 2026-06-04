# Backend: FastAPI + silnik rozliczeniowy (pandas/openpyxl + multiprocessing)
# Budowane z korzenia repo, by mieć dostęp do backend/ oraz seed_data/.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TELEDIAG_DATA_DIR=/data \
    TELEDIAG_SEED_DIR=/srv/seed_data

WORKDIR /srv

# Zależności systemowe minimalne (openpyxl/pandas nie wymagają kompilacji na slim+wheels)
COPY backend/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

# Kod aplikacji
COPY backend/ /srv/
# Dane startowe (seed) — importowane przy pierwszym uruchomieniu, jeśli baza pusta
COPY seed_data/ /srv/seed_data/

# Wolumen na dane trwałe (SQLite, wersje plików, katalogi zadań)
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8080

# Jeden worker uvicorn — przeliczenia i tak biegną w osobnych procesach (app.run_job)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
