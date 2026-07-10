"""
Router modułu WINDYKACJA — należności per jednostka. Prosty CRUD (bez zadań
w tle/SSE — nie ma tu ciężkich obliczeń). Lista i podsumowanie najpierw
SYNCHRONIZUJĄ propozycje z ostatnich rozliczeń jednostek (leniwie, jak Mapa),
więc dane są zawsze świeże bez potrzeby hooka w silniku rozliczeniowym.
"""

import datetime

from fastapi import APIRouter, HTTPException

from app import db
from app.engine import windykacja as wnd

router = APIRouter(prefix="/api/windykacja", tags=["windykacja"])


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


@router.get("/receivables")
async def list_receivables(period: str | None = None, status: str | None = None, unit: str | None = None):
    wnd.sync_receivables()
    rows = db.list_receivables(period=period, status=status, unit_key=unit)
    views = [wnd.receivable_view(r) for r in rows]
    views.sort(key=lambda v: (not v["is_overdue"], v.get("due_date") or "9999-99-99"))
    return {"receivables": views}


@router.get("/summary")
async def summary(period: str | None = None):
    wnd.sync_receivables()
    rows = db.list_receivables(period=period)
    views = [wnd.receivable_view(r) for r in rows]
    return wnd.summary_tiles(views)


@router.post("/receivables")
async def create_manual_receivable(payload: dict):
    """Ręczne dodanie należności — np. zaległość historyczna sprzed wdrożenia modułu."""
    unit_key = str(payload.get("unit_key") or "").strip().lower()
    unit_name = str(payload.get("unit_name") or unit_key).strip()
    amount = payload.get("amount_due")
    if not unit_key or amount is None:
        raise HTTPException(400, "Podaj jednostkę i kwotę.")
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        raise HTTPException(400, "Nieprawidłowa kwota.")
    rid = wnd.new_id()
    db.create_receivable({
        "id": rid, "unit_key": unit_key, "unit_name": unit_name,
        "period": payload.get("period") or None,
        "source_amount": amount, "amount_due": amount, "paid_amount": 0.0,
        "status": payload.get("status") or "wystawiona",
        "due_date": payload.get("due_date") or None,
        "note": payload.get("note") or None,
        "source_run_id": None, "source_changed": 0,
        "created_at": _now(), "updated_at": _now(),
    })
    return wnd.receivable_view(db.get_receivable(rid))


@router.get("/receivables/{receivable_id}")
async def get_receivable(receivable_id: str):
    rec = db.get_receivable(receivable_id)
    if rec is None:
        raise HTTPException(404, "Nie znaleziono należności.")
    view = wnd.receivable_view(rec)
    view["history"] = db.list_history(receivable_id)
    return view


@router.patch("/receivables/{receivable_id}")
async def edit_receivable(receivable_id: str, payload: dict):
    rec = db.get_receivable(receivable_id)
    if rec is None:
        raise HTTPException(404, "Nie znaleziono należności.")
    editable = {"amount_due", "due_date", "status", "note", "unit_name"}
    for field in editable & set(payload.keys()):
        value = payload[field]
        if field == "amount_due":
            try:
                value = round(float(value), 2)
            except (TypeError, ValueError):
                raise HTTPException(400, "Nieprawidłowa kwota.")
        wnd.apply_edit(receivable_id, field, value, reason=payload.get("reason"))
    if "amount_due" in payload:
        # kwota zmieniona ręcznie -> gasimy flagę „source_changed", bo użytkownik
        # już świadomie zdecydował o aktualnej wartości.
        db.update_receivable(receivable_id, source_changed=0, updated_at=_now())
    return wnd.receivable_view(db.get_receivable(receivable_id))


@router.delete("/receivables/{receivable_id}")
async def delete_receivable(receivable_id: str):
    rec = db.get_receivable(receivable_id)
    if rec is None:
        raise HTTPException(404, "Nie znaleziono należności.")
    db.delete_receivable(receivable_id)
    return {"ok": True}


@router.put("/receivables/{receivable_id}/installments")
async def set_installments(receivable_id: str, payload: dict):
    items = payload.get("items")
    if not isinstance(items, list):
        raise HTTPException(400, "Pole 'items' musi być listą rat.")
    try:
        return wnd.replace_installments(receivable_id, items)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/receivables/{receivable_id}/installments/{installment_id}/pay")
async def pay_installment(receivable_id: str, installment_id: str, payload: dict):
    amount = payload.get("amount")
    if amount is None:
        raise HTTPException(400, "Podaj kwotę wpłaty.")
    try:
        return wnd.pay_installment(installment_id, float(amount),
                                   paid_at=payload.get("paid_at"), note=payload.get("note"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/receivables/{receivable_id}/pay")
async def pay_receivable(receivable_id: str, payload: dict):
    amount = payload.get("amount")
    if amount is None:
        raise HTTPException(400, "Podaj kwotę wpłaty.")
    try:
        return wnd.pay_receivable(receivable_id, float(amount),
                                  paid_at=payload.get("paid_at"), note=payload.get("note"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/sync")
async def sync_now():
    return wnd.sync_receivables()


# ---- Terminy płatności per jednostka (ustawienia) -----------------------------

@router.get("/payment-terms")
async def get_payment_terms():
    from app.engine.config import DEFAULT_CONFIG
    cfg = db.get_settings()
    seed = DEFAULT_CONFIG.get("payment_terms_by_unit", {})
    user_map = cfg.get("payment_terms_by_unit") or {}
    return {
        "default_days": int(cfg.get("default_payment_term_days")
                            or DEFAULT_CONFIG.get("default_payment_term_days", 14)),
        "terms": {**seed, **user_map},
    }


@router.put("/payment-terms")
async def save_payment_terms(payload: dict):
    cfg = db.get_settings()
    if "default_days" in payload:
        try:
            cfg["default_payment_term_days"] = int(payload["default_days"])
        except (TypeError, ValueError):
            raise HTTPException(400, "Nieprawidłowa liczba dni.")
    if "terms" in payload:
        if not isinstance(payload["terms"], dict):
            raise HTTPException(400, "Pole 'terms' musi być obiektem {jednostka: dni}.")
        clean = {}
        for k, v in payload["terms"].items():
            try:
                clean[str(k).strip().lower()] = int(v)
            except (TypeError, ValueError):
                continue
        cfg["payment_terms_by_unit"] = clean
    db.save_settings(cfg)
    return await get_payment_terms()
