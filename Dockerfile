# Backend: FastAPI + silnik rozliczeniowy (pandas/openpyxl + multiprocessing)
# Budowane z korzenia repo (dostęp do backend/). seed_data/ jest poza repo.
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
# Dane startowe (seed) NIE są w repo (higiena bezpieczeństwa — realne dane klientów
# poza publicznym GitHubem). Tworzymy pusty katalog: app.seed.seed_if_empty znosi jego
# brak (globy zwracają pusto), a istniejące wdrożenie ma dane na wolumenie /data.
# Aby doseedować świeżą instalację, wgraj pliki przez aplikację albo zamontuj je
# w /srv/seed_data (TELEDIAG_SEED_DIR).
RUN mkdir -p /srv/seed_data

# Wolumen na dane trwałe (SQLite, wersje plików, katalogi zadań)
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8080

# Jeden worker uvicorn — przeliczenia i tak biegną w osobnych procesach (app.run_job)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
