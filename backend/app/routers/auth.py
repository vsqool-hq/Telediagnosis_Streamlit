"""
Logowanie, sesje i zarządzanie kontami (role: admin / user).

Model: konta w tabeli `users` (hasło hashowane pbkdf2), sesje w tabeli
`sessions` (token losowy). Token wędruje w nagłówku X-API-Token (jak dotąd).
Zgodność wstecz: wspólne hasło z TELEDIAG_API_TOKEN nadal działa jako
„master-admin" (obsługiwane w auth_guard w main.py), więc obecne logowanie nie
przestaje działać. Autoryzację ról (admin dla zmian) wymusza auth_guard.
"""

import time

from fastapi import APIRouter, HTTPException, Request

from app import db

router = APIRouter(prefix="/api", tags=["auth"])

# Minimalna długość hasła dla NOWYCH haseł (istniejące konta działają dalej).
MIN_PASSWORD_LEN = 10

# Ograniczenie prób logowania. Licznik trzymany w pamięci procesu — backend chodzi
# jako pojedynczy worker (patrz Dockerfile), więc to wystarcza bez dokładania
# zależności. Restart czyści licznik: świadomy kompromis, bo blokada ma zatrzymać
# zgadywanie haseł, a nie być trwałą karą.
#
# Liczymy w DWÓCH wymiarach, bo za proxy (Fly.io) wielu użytkowników może dzielić
# jeden adres IP — blokada po samym IP potrafiłaby wtedy odciąć całą firmę:
#   • per LOGIN (próg niski) — to właśnie blokuje zgadywanie hasła do konta,
#   • per IP    (próg wysoki) — zatrzymuje maszynowe ataki „po wielu loginach",
#     a przy współdzielonym adresie normalna praca go nie dotyka.
MAX_ATTEMPTS_LOGIN = 8
MAX_ATTEMPTS_IP = 60
LOCKOUT_SECONDS = 300
_failed: dict[str, list] = {}          # klucz -> [liczba_prób, czas_ostatniej_próby]


def _client_ip(request: Request) -> str:
    """Adres klienta. Za proxy bierzemy nagłówek, który proxy ustawia (Fly-Client-IP /
    X-Forwarded-For) — te nagłówki da się podrobić, ale służą TYLKO do rozdzielania
    liczników, nigdy do decyzji o dostępie, więc podrobienie co najwyżej osłabia limit."""
    fwd = request.headers.get("Fly-Client-IP") or request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    c = request.client
    return c.host if c else "?"


def _hit(key: str, limit: int):
    """Sprawdza licznik dla klucza; rzuca 429 po przekroczeniu progu w oknie."""
    rec = _failed.get(key)
    if not rec:
        return
    attempts, last = rec
    if (time.time() - last) >= LOCKOUT_SECONDS:
        _failed.pop(key, None)         # okno minęło — licznik od zera
        return
    if attempts >= limit:
        wait = int(LOCKOUT_SECONDS - (time.time() - last))
        raise HTTPException(429, f"Zbyt wiele nieudanych prób logowania. Spróbuj za {wait} s.")


def _check_not_locked(ip: str, username: str):
    _hit(f"u:{username.lower()}", MAX_ATTEMPTS_LOGIN)
    _hit(f"i:{ip}", MAX_ATTEMPTS_IP)


def _note_failure(ip: str, username: str):
    for key in (f"u:{username.lower()}", f"i:{ip}"):
        rec = _failed.get(key)
        _failed[key] = [(rec[0] + 1) if rec else 1, time.time()]
    # Higiena pamięci: przy dużej liczbie kluczy usuń te z wygasłym oknem.
    if len(_failed) > 5000:
        now = time.time()
        for k in [k for k, v in _failed.items() if (now - v[1]) >= LOCKOUT_SECONDS]:
            _failed.pop(k, None)


def _clear_failures(ip: str, username: str):
    _failed.pop(f"u:{username.lower()}", None)
    _failed.pop(f"i:{ip}", None)


@router.post("/auth/login")
async def login(payload: dict, request: Request):
    ip = _client_ip(request)
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    _check_not_locked(ip, username)
    u = db.get_user_by_username(username)
    if not u or not db.verify_password(password, u["password_hash"]):
        _note_failure(ip, username)
        db.add_audit(username or "(brak loginu)", "Nieudane logowanie", f"IP {ip}")
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")
    _clear_failures(ip, username)
    token = db.create_session(u["id"])
    db.add_audit(u["username"], "Logowanie", None)
    return {"token": token, "username": u["username"], "role": u["role"]}


@router.post("/auth/logout")
async def logout(request: Request):
    token = request.headers.get("X-API-Token") or request.query_params.get("token")
    if token:
        db.delete_session(token)
    return {"ok": True}


@router.get("/auth/me")
async def me(request: Request):
    """Kim jestem (rola) — do sterowania UI. Ustawiane przez auth_guard."""
    return {
        "role": getattr(request.state, "role", None),
        "username": getattr(request.state, "username", None),
        "auth_enabled": getattr(request.state, "auth_enabled", True),
    }


@router.get("/audit")
async def audit_log(limit: int = 300):
    """Dziennik zdarzeń (audyt akcji) — tylko admin (wymuszane w auth_guard)."""
    return {"entries": db.list_audit(limit)}


# ---- Zarządzanie kontami (tylko admin — wymuszane w auth_guard: /api/users) ----

@router.get("/users")
async def users_list():
    return {"users": db.list_users()}


@router.post("/users")
async def users_create(payload: dict):
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    role = payload.get("role") if payload.get("role") in ("admin", "user") else "user"
    if not username or len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Podaj login i hasło (min. {MIN_PASSWORD_LEN} znaków).")
    if db.get_user_by_username(username):
        raise HTTPException(400, "Użytkownik o tym loginie już istnieje.")
    return db.create_user(username, password, role)


@router.put("/users/{user_id}")
async def users_update(user_id: int, payload: dict):
    target = next((u for u in db.list_users() if u["id"] == user_id), None)
    if not target:
        raise HTTPException(404, "Nie znaleziono użytkownika.")
    new_role = payload.get("role")
    # Nie pozwól zdegradować ostatniego administratora.
    if target["role"] == "admin" and new_role == "user" and db.count_admins() <= 1:
        raise HTTPException(400, "Nie można odebrać roli ostatniemu administratorowi.")
    pw = payload.get("password") or None
    if pw is not None and len(str(pw)) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Hasło musi mieć min. {MIN_PASSWORD_LEN} znaków.")
    db.update_user(user_id, password=pw, role=new_role)
    return {"ok": True}


@router.delete("/users/{user_id}")
async def users_delete(user_id: int):
    target = next((u for u in db.list_users() if u["id"] == user_id), None)
    if not target:
        raise HTTPException(404, "Nie znaleziono użytkownika.")
    if target["role"] == "admin" and db.count_admins() <= 1:
        raise HTTPException(400, "Nie można usunąć ostatniego administratora.")
    db.delete_user(user_id)
    return {"ok": True}
