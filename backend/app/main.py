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
from app.routers import jobs, files, settings, stats

app = FastAPI(title="Automatyzator Rozliczeń Medycznych", version="0.1.0")

cors_origins = os.environ.get("TELEDIAG_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_TOKEN = os.environ.get("TELEDIAG_API_TOKEN", "").strip()


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    """Opcjonalna ochrona /api tokenem (gdy TELEDIAG_API_TOKEN ustawiony)."""
    path = request.url.path
    if API_TOKEN and path.startswith("/api") and request.method != "OPTIONS":
        token = request.headers.get("X-API-Token") or request.query_params.get("token")
        if token != API_TOKEN:
            return JSONResponse({"detail": "Brak autoryzacji."}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
def _startup():
    db.init_db()
    from app.seed import seed_if_empty
    seed_if_empty()


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(jobs.router)
app.include_router(files.router)
app.include_router(settings.router)
app.include_router(stats.router)
