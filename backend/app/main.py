"""
Aplikacja FastAPI — Automatyzator Rozliczeń Medycznych (backend).

Uruchomienie lokalne:
    cd backend
    uvicorn app.main:app --reload

Zmienne środowiskowe:
    TELEDIAG_DATA_DIR   – katalog na dane (domyślnie /data; lokalnie ustaw np. ./data)
    TELEDIAG_API_TOKEN  – jeśli ustawiony, chroni /api tokenem (nagłówek X-API-Token lub ?token=)
    TELEDIAG_CORS_ORIGINS – lista dozwolonych originów front-endu (po przecinku)
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.routers import (
    jobs, files, settings, stats, cennik, cennik_lekarzy, doctors, sync, reference, units, teamup, auth, windykacja,
    cashflow, invoices,
)

app = FastAPI(title="Automatyzator Rozliczeń Medycznych", version="0.1.0")

cors_origins = os.environ.get("TELEDIAG_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import secrets as _secrets

API_TOKEN = os.environ.get("TELEDIAG_API_TOKEN", "").strip()

# Ścieżki dostępne bez tokenu (logowanie — token dopiero powstaje).
PUBLIC_PATHS = {"/api/auth/login"}


def _audit_label(method: str, path: str):
    """Czytelny opis akcji do dziennika. None = nie logujemy (szum)."""
    if path.startswith("/api/auth") or path.startswith("/api/sync"):
        return None
    if path.startswith("/api/versions"):
        if method == "DELETE":
            return "Usunięcie wersji pliku"
        if path.endswith("/activate"):
            return "Aktywacja wersji pliku"
        if path.endswith("/import"):
            return "Import wersji (synchronizacja)"
        return "Wgranie pliku (wzorzec/cennik)"
    if path.startswith("/api/jobs"):
        return "Usunięcie rozliczenia" if method == "DELETE" else "Uruchomienie rozliczenia (wgranie pliku)"
    if path.startswith("/api/settings"):
        return "Zmiana ustawień"
    if path.startswith("/api/cennik-lekarzy"):
        return "Zapis cennika lekarzy"
    if path.startswith("/api/cennik"):
        return "Zapis cennika jednostek"
    if path.startswith("/api/doctors/billing"):
        return "Przeliczenie lekarzy"
    if path.startswith("/api/doctors/compare"):
        return "Przeliczenie porównania"
    if path.startswith("/api/doctors/excluded"):
        return "Zmiana wyłączonych lekarzy"
    if path.startswith("/api/units/excluded"):
        return "Zmiana wyłączonych jednostek"
    if path.startswith("/api/reference-image"):
        return "Zmiana obrazka-wzoru" + (" (usunięcie)" if method == "DELETE" else "")
    if path.startswith("/api/teamup"):
        return "Zmiana konfiguracji TeamUp"
    if path.startswith("/api/users"):
        return "Zarządzanie kontami"
    return f"Zmiana danych ({method})"


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    """
    Autoryzacja /api z rolami:
      • token = TELEDIAG_API_TOKEN → „master-admin" (zgodność wstecz),
      • token = sesja użytkownika  → rola z konta (admin | user),
      • brak/niepoprawny token, gdy ochrona włączona → 401.
    Zmiany danych (metody != GET) oraz zarządzanie kontami (/api/users) — TYLKO
    admin. Podgląd (GET) — każdy zalogowany. Gdy ochrona wyłączona (brak tokenu
    i brak kont — lokalnie) → wszystko dozwolone jako admin.
    """
    path = request.url.path
    request.state.role = None
    request.state.username = None
    auth_enabled = bool(API_TOKEN) or db.has_users()
    request.state.auth_enabled = auth_enabled

    if path.startswith("/api") and request.method != "OPTIONS" and path not in PUBLIC_PATHS:
        token = request.headers.get("X-API-Token") or request.query_params.get("token")
        role = username = None
        if API_TOKEN and token and _secrets.compare_digest(token, API_TOKEN):
            role, username = "admin", "administrator"
        elif token:
            u = db.get_session_user(token)
            if u:
                role, username = u["role"], u["username"]
        if not auth_enabled:
            role = role or "admin"          # lokalnie bez ochrony → admin
        request.state.role = role
        request.state.username = username

        if auth_enabled and role is None:
            return JSONResponse({"detail": "Brak autoryzacji."}, status_code=401)
        needs_admin = (request.method not in ("GET", "HEAD")
                       or path.startswith("/api/users") or path.startswith("/api/audit"))
        if needs_admin and role != "admin" and path != "/api/auth/logout":
            return JSONResponse({"detail": "Wymagane uprawnienia administratora."}, status_code=403)

    response = await call_next(request)

    # Audyt: udane zmiany (POST/PUT/DELETE) trafiają do dziennika z loginem sprawcy.
    if (path.startswith("/api") and request.method in ("POST", "PUT", "DELETE", "PATCH")
            and path not in PUBLIC_PATHS and getattr(response, "status_code", 500) < 400):
        label = _audit_label(request.method, path)
        if label:
            db.add_audit(getattr(request.state, "username", None), label, f"{request.method} {path}")
    # Private Network Access: pozwól stronie z HTTPS (Vercel) łączyć się z lokalnym
    # backendem (http://localhost) przy wyborze „Ten komputer" — Chrome tego wymaga.
    if request.headers.get("access-control-request-private-network"):
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


@app.on_event("startup")
def _startup():
    db.init_db()
    from app.services.runner import mark_interrupted_jobs
    mark_interrupted_jobs()
    from app.seed import seed_if_empty
    seed_if_empty()

    # Auto-synchronizacja aktywnych plików z chmury przy starcie LOKALNEGO backendu.
    # Włączana wyłącznie przez zmienną TELEDIAG_SYNC_URL (ustawia ją launcher lokalny),
    # więc backend w chmurze NIE synchronizuje się sam ze sobą. Best-effort: brak sieci
    # / wyłączona chmura nie przerywa startu. Reguła „lokalne nowsze wygrywa" jest w
    # pull_active_from_cloud, więc nie nadpisuje świeższych plików lokalnych.
    sync_url = os.environ.get("TELEDIAG_SYNC_URL", "").strip().rstrip("/")
    if sync_url and not sync_url.startswith(("http://localhost", "http://127.0.0.1")):
        try:
            from app.routers.sync import pull_active_from_cloud
            res = pull_active_from_cloud(sync_url, os.environ.get("TELEDIAG_SYNC_TOKEN", "").strip())
            print(f"[startup-sync] z {sync_url}: {res}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[startup-sync] pominięto ({e}).", flush=True)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(jobs.router)
app.include_router(files.router)
app.include_router(settings.router)
app.include_router(stats.router)
app.include_router(cennik.router)
app.include_router(cennik_lekarzy.router)
app.include_router(doctors.router)
app.include_router(sync.router)
app.include_router(reference.router)
app.include_router(units.router)
app.include_router(teamup.router)
app.include_router(auth.router)
app.include_router(windykacja.router)
app.include_router(cashflow.router)
app.include_router(invoices.router)
