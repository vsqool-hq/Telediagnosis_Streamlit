"""
Aplikacja FastAPI — Automatyzator Rozliczeń Medycznych (backend).

Uruchomienie lokalne:
    cd backend
    uvicorn app.main:app --reload

Zmienne środowiskowe:
    TELEDIAG_DATA_DIR   – katalog na dane (domyślnie /data; lokalnie ustaw np. ./data)
    TELEDIAG_API_TOKEN  – jeśli ustawiony, chroni /api tokenem (nagłówek X-API-Token lub ?token=)
    TELEDIAG_CORS_ORIGINS – lista dozwolonych originów front-endu (po przecinku)
    TELEDIAG_ALLOW_ANONYMOUS – „1" = świadome wyłączenie ochrony (TYLKO instalacja lokalna)
    TELEDIAG_SESSION_TTL_HOURS – bezczynność, po której sesja wygasa (domyślnie 12 h)
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.storage import UnsafePathError
from app.routers import (
    jobs, files, settings, stats, cennik, cennik_lekarzy, doctors, sync, reference, units, teamup, auth, windykacja,
    cashflow, invoices,
)

app = FastAPI(title="Automatyzator Rozliczeń Medycznych", version="0.1.0")

# CORS. Gdy lista originów nie jest podana, zostaje „*", ale WTEDY nie wolno włączać
# allow_credentials — „*" + credentials to konfiguracja, która pozwala dowolnej stronie
# wykonywać uwierzytelnione żądania. Aplikacja i tak nie używa ciasteczek (token idzie
# w nagłówku X-API-Token), więc credentials są potrzebne tylko przy jawnej liście originów.
_cors_env = os.environ.get("TELEDIAG_CORS_ORIGINS", "").strip()
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] or ["*"]
_cors_wildcard = CORS_ORIGINS == ["*"]
if _cors_wildcard:
    print("[bezpieczeństwo] TELEDIAG_CORS_ORIGINS nie jest ustawione — CORS działa jako '*'. "
          "Na produkcji ustaw adres front-endu.", flush=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=not _cors_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

import secrets as _secrets

API_TOKEN = os.environ.get("TELEDIAG_API_TOKEN", "").strip()

# Świadome wyłączenie ochrony — wyłącznie dla instalacji lokalnej (ustawiane przez
# start-local.command). Na serwerze publicznym NIE ustawiać.
ALLOW_ANONYMOUS = os.environ.get("TELEDIAG_ALLOW_ANONYMOUS", "").strip() == "1"

# Ścieżki dostępne bez tokenu (logowanie — token dopiero powstaje).
PUBLIC_PATHS = {"/api/auth/login"}

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


def _is_loopback(request: Request) -> bool:
    """Czy żądanie przyszło z tej samej maszyny? Instalacja lokalna nasłuchuje na
    loopbacku, więc taki ruch jest z definicji „od użytkownika przy komputerze".
    Ruch przez proxy (Fly.io) NIGDY nie ma adresu loopback, więc chmura tędy nie
    przejdzie. Nie ufamy nagłówkom X-Forwarded-* (można je podrobić)."""
    client = request.client
    return bool(client and client.host in _LOOPBACK_HOSTS)


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
      • brak/niepoprawny token → 401.

    Zasada „domyślnie zamknięte": gdy ochrona NIE jest skonfigurowana (brak
    TELEDIAG_API_TOKEN i brak kont w bazie), dostęp bez logowania dostaje wyłącznie
    ruch z tej samej maszyny (instalacja lokalna) albo instancja z jawnie ustawionym
    TELEDIAG_ALLOW_ANONYMOUS=1. Serwer publiczny bez konfiguracji odpowiada 401,
    zamiast — jak dotąd — wpuszczać każdego jako administratora.

    Zmiany danych (metody != GET) oraz zarządzanie kontami (/api/users) — TYLKO
    admin. Podgląd (GET) — każdy zalogowany.
    """
    path = request.url.path
    request.state.role = None
    request.state.username = None
    configured = bool(API_TOKEN) or db.has_users()
    # Tryb otwarty tylko wtedy, gdy ochrony nie skonfigurowano I ruch jest lokalny
    # (albo administrator jawnie zgodził się na brak ochrony).
    anonymous_ok = (not configured) and (ALLOW_ANONYMOUS or _is_loopback(request))
    request.state.auth_enabled = not anonymous_ok

    if path.startswith("/api") and request.method != "OPTIONS" and path not in PUBLIC_PATHS:
        # Token z adresu URL (?token=) jest potrzebny tam, gdzie nie da się ustawić
        # nagłówka: pobieranie plików <a href> / obrazki / EventSource. Takie tokeny
        # trafiają do logów serwera, historii przeglądarki i nagłówka Referer, więc
        # akceptujemy je WYŁĄCZNIE dla żądań odczytu — nigdy dla zmian danych.
        header_token = request.headers.get("X-API-Token")
        url_token = request.query_params.get("token")
        if request.method in ("GET", "HEAD"):
            token = header_token or url_token
        else:
            token = header_token
            if not token and url_token:
                return JSONResponse(
                    {"detail": "Token w adresie URL jest dozwolony tylko dla odczytu. "
                               "Zmiany danych wymagają nagłówka X-API-Token."},
                    status_code=401,
                )

        role = username = None
        if API_TOKEN and token and _secrets.compare_digest(token, API_TOKEN):
            role, username = "admin", "administrator"
        elif token:
            u = db.get_session_user(token)
            if u:
                role, username = u["role"], u["username"]
        if anonymous_ok:
            role = role or "admin"          # lokalnie bez ochrony → admin
        request.state.role = role
        request.state.username = username

        if role is None:
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
    db.purge_expired_sessions()
    if not (bool(API_TOKEN) or db.has_users()):
        print("[bezpieczeństwo] Brak TELEDIAG_API_TOKEN i brak kont użytkowników. "
              + ("Ochrona WYŁĄCZONA jawnie (TELEDIAG_ALLOW_ANONYMOUS=1)."
                 if ALLOW_ANONYMOUS else
                 "Dostęp mają tylko żądania z tej maszyny; z sieci API zwraca 401. "
                 "Aby uruchomić instancję publiczną, ustaw sekret TELEDIAG_API_TOKEN, "
                 "zaloguj się nim i załóż konta użytkowników."), flush=True)
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


@app.exception_handler(UnsafePathError)
async def _unsafe_path_handler(request: Request, exc: UnsafePathError):
    """Identyfikator z żądania nie nadaje się na element ścieżki (próba path traversal).
    Odpowiadamy 404 — bez ujawniania szczegółów — i zostawiamy ślad w logu serwera."""
    print(f"[bezpieczeństwo] Odrzucono ścieżkę: {request.method} {request.url.path} ({exc})", flush=True)
    return JSONResponse({"detail": "Nie znaleziono zasobu."}, status_code=404)


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
