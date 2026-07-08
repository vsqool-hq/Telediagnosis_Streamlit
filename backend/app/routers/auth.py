"""
Logowanie, sesje i zarządzanie kontami (role: admin / user).

Model: konta w tabeli `users` (hasło hashowane pbkdf2), sesje w tabeli
`sessions` (token losowy). Token wędruje w nagłówku X-API-Token (jak dotąd).
Zgodność wstecz: wspólne hasło z TELEDIAG_API_TOKEN nadal działa jako
„master-admin" (obsługiwane w auth_guard w main.py), więc obecne logowanie nie
przestaje działać. Autoryzację ról (admin dla zmian) wymusza auth_guard.
"""

from fastapi import APIRouter, HTTPException, Request

from app import db

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login")
async def login(payload: dict):
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    u = db.get_user_by_username(username)
    if not u or not db.verify_password(password, u["password_hash"]):
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")
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
    if not username or len(password) < 4:
        raise HTTPException(400, "Podaj login i hasło (min. 4 znaki).")
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
    if pw is not None and len(str(pw)) < 4:
        raise HTTPException(400, "Hasło musi mieć min. 4 znaki.")
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
