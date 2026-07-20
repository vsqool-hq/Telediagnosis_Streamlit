"""
Silnik modułu WINDYKACJA — należności per jednostka, niezależny od Modułów 1/2.

Zasada: po każdym pełnym przeliczeniu jednostek (Moduł 1) powstaje/aktualizuje się
propozycja należności per jednostka per miesiąc, na podstawie POLICZONEGO PRZYCHODU
(ten sam, co na Pulpicie/Mapie — `_job_revenue_by_client`). Synchronizacja jest
LENIWA: wywoływana przy każdym odczycie listy (jak cache Mapy), a nie przez hook
w silniku rozliczeniowym — więc Moduł 1 pozostaje całkowicie nietknięty.

Bezpieczeństwo przy ponownym przeliczeniu: rekord NIETKNIĘTY ręcznie (kwota wciąż
równa source_amount, brak wpłat/transz) jest aktualizowany do nowej kwoty. Rekord
EDYTOWANY lub z wpłatami/transzami NIE jest nadpisywany — dostaje tylko flagę
source_changed, żeby użytkownik świadomie zdecydował.

Transze: suma MUSI się równać amount_due (twarda walidacja, ustalone z użytkownikiem)
— sprawdzana przy zapisie CAŁEGO harmonogramu (nie przy dodawaniu pojedynczej raty,
bo to uniemożliwiłoby budowanie planu krok po kroku).

Usunięcie: jeśli usuwana należność pochodziła z rozliczenia (source_run_id), samo
DELETE nie wystarczy — leniwa synchronizacja odtworzyłaby ją przy kolejnym odczycie
(bo źródłowe zadanie wciąż istnieje w historii). Dlatego usunięcie takiego wpisu
zapisuje (unit_key, period) w `wind_sync_skip` — sync_receivables() trwale je pomija.

Podpozycje (kary umowne, korekty): dolicza się je do amount_due jako DELTĘ (kwota
może być ujemna) — nie zastępują ręcznej edycji kwoty, tylko ją korygują o konkretną,
nazwaną pozycję z własną datą. Jeśli należność ma już harmonogram rat, dodanie
podpozycji rozjeżdża sumę rat z nową kwotą (installments_balanced=false) — użytkownik
świadomie poprawia raty, tak samo jak po ręcznej zmianie amount_due.

Wpłaty: oprócz zbiorczego licznika paid_amount (na należności/racie) każda wpłata
zapisuje się też jako osobny wiersz w wind_payments z RZECZYWISTĄ datą wpłaty —
dzięki temu można wpisać dowolną, także wsteczną, wpłatę i zobaczyć pełną listę.
"""

import datetime
import uuid

from app import db
from app.engine.config import DEFAULT_CONFIG

STICKY_STATUSES = {"sporna", "odpisana"}
TOLERANCE = 0.01  # zł — tolerancja zaokrągleń przy sumowaniu transz


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _today() -> datetime.date:
    return datetime.date.today()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def resolve_due_days(unit_key: str, cfg: dict | None = None) -> int:
    """Termin płatności (dni) dla jednostki: ustawienia użytkownika > mapa startowa
    (z pliku Słownik) > domyślny globalny."""
    cfg = cfg or db.get_settings()
    seed_map = DEFAULT_CONFIG.get("payment_terms_by_unit", {})
    user_map = cfg.get("payment_terms_by_unit") or {}
    merged = {**seed_map, **user_map}
    default_days = int(cfg.get("default_payment_term_days")
                        or DEFAULT_CONFIG.get("default_payment_term_days", 14))
    try:
        return int(merged.get(unit_key, default_days))
    except (TypeError, ValueError):
        return default_days


# ---- Synchronizacja z rozliczeniem jednostek --------------------------------

def sync_receivables() -> dict:
    """Tworzy/aktualizuje propozycje należności dla wszystkich miesięcy z „ostatnim"
    przeliczeniem (latest_jobs_by_month). Zwraca podsumowanie {created, updated, flagged}."""
    from app.routers.stats import latest_jobs_by_month, _job_revenue_by_client

    cfg = db.get_settings()
    created = updated = flagged = 0
    best = latest_jobs_by_month()
    skip_keys = db.list_sync_skip_keys()
    for period, info in best.items():
        job_id = info["job_id"]
        try:
            by_client = _job_revenue_by_client(job_id)
        except Exception:  # noqa: BLE001
            continue
        for unit_key, amount in by_client.items():
            amount = round(float(amount or 0), 2)
            if amount <= 0:
                continue
            if (unit_key, period) in skip_keys:
                continue  # użytkownik świadomie usunął ten wpis — nie odtwarzamy go
            existing = db.find_receivable_by_unit_period(unit_key, period)
            if existing is None:
                due = (_today() + datetime.timedelta(days=resolve_due_days(unit_key, cfg))).isoformat()
                db.create_receivable({
                    "id": new_id(), "unit_key": unit_key, "unit_name": unit_key,
                    "period": period, "source_amount": amount, "amount_due": amount,
                    "paid_amount": 0.0, "status": "wystawiona", "due_date": due,
                    "note": None, "source_run_id": job_id, "source_changed": 0,
                    "created_at": _now(), "updated_at": _now(),
                })
                created += 1
                continue
            if existing.get("source_run_id") is None:
                continue  # wpis ręczny — synchronizacja nigdy go nie rusza
            untouched = (
                abs(float(existing["amount_due"]) - float(existing["source_amount"])) < TOLERANCE
                and not db.list_installments(existing["id"])
                and float(existing.get("paid_amount") or 0) <= 0
            )
            if untouched:
                db.update_receivable(existing["id"], source_amount=amount, amount_due=amount,
                                     source_run_id=job_id, source_changed=0, updated_at=_now())
                updated += 1
            elif abs(float(existing["source_amount"]) - amount) >= TOLERANCE:
                db.update_receivable(existing["id"], source_amount=amount,
                                     source_run_id=job_id, source_changed=1, updated_at=_now())
                flagged += 1
    return {"created": created, "updated": updated, "flagged": flagged}


# ---- Widok (pola wyliczane) ---------------------------------------------------

def _recompute_status(receivable: dict, installments: list) -> str:
    """Status auto-wyliczany z wpłat, chyba że ustawiony ręcznie na 'sporna'/'odpisana'
    (te są STICKY — trzymają się, dopóki użytkownik ich nie zmieni)."""
    if receivable.get("status") in STICKY_STATUSES:
        return receivable["status"]
    total_due = float(receivable.get("amount_due") or 0)
    if installments:
        paid = sum(float(i.get("paid_amount") or 0) for i in installments)
    else:
        paid = float(receivable.get("paid_amount") or 0)
    if total_due > 0 and paid >= total_due - TOLERANCE:
        return "oplacona"
    if paid > TOLERANCE:
        return "czesciowo_oplacona"
    return "wystawiona"


def receivable_view(receivable: dict) -> dict:
    """Rekord + pola wyliczane: transze, saldo, czy po terminie, ile dni."""
    installments = db.list_installments(receivable["id"])
    total_due = float(receivable.get("amount_due") or 0)
    paid = (sum(float(i.get("paid_amount") or 0) for i in installments) if installments
            else float(receivable.get("paid_amount") or 0))
    remaining = round(total_due - paid, 2)
    status = _recompute_status(receivable, installments)
    if status != receivable.get("status"):
        db.update_receivable(receivable["id"], status=status, updated_at=_now())

    due_date = receivable.get("due_date")
    is_overdue = False
    days_overdue = 0
    if due_date and status not in ("oplacona", "odpisana") and remaining > TOLERANCE:
        d = datetime.date.fromisoformat(due_date)
        delta = (_today() - d).days
        if delta > 0:            # "od razu" po terminie — bez karencji
            is_overdue = True
            days_overdue = delta

    inst_sum = round(sum(float(i.get("amount") or 0) for i in installments), 2)
    items = db.list_receivable_items(receivable["id"])
    payments = db.list_payments(receivable["id"])
    return {
        **receivable,
        "status": status,
        "paid_amount": round(paid, 2),
        "remaining": remaining,
        "is_overdue": is_overdue,
        "days_overdue": days_overdue,
        "installments": installments,
        "installments_count": len(installments),
        "installments_balanced": (not installments) or abs(inst_sum - total_due) < TOLERANCE,
        "items": items,
        "items_total": round(sum(float(i.get("amount") or 0) for i in items), 2),
        "payments": payments,
    }


def summary_tiles(receivables_views: list) -> dict:
    """Kafelki podsumowania: przeterminowane, do zapłaty w tym tygodniu, zapłacone
    w tym miesiącu, saldo całkowite."""
    today = _today()
    week_end = today + datetime.timedelta(days=7)
    month_start = today.replace(day=1)

    overdue_amt = overdue_n = 0.0
    week_amt = week_n = 0.0
    paid_month_amt = paid_month_n = 0.0
    balance = 0.0
    for r in receivables_views:
        balance += float(r["remaining"])
        if r["is_overdue"]:
            overdue_amt += r["remaining"]
            overdue_n += 1
        elif r.get("due_date") and r["remaining"] > TOLERANCE:
            d = datetime.date.fromisoformat(r["due_date"])
            if today <= d <= week_end:
                week_amt += r["remaining"]
                week_n += 1
        if r["status"] == "oplacona":
            u = datetime.datetime.fromisoformat(r["updated_at"]).date()
            if u >= month_start:
                paid_month_amt += float(r["amount_due"])
                paid_month_n += 1
    return {
        "overdue_amount": round(overdue_amt, 2), "overdue_count": int(overdue_n),
        "due_this_week_amount": round(week_amt, 2), "due_this_week_count": int(week_n),
        "paid_this_month_amount": round(paid_month_amt, 2), "paid_this_month_count": int(paid_month_n),
        "total_balance": round(balance, 2),
    }


# ---- Edycja pól z historią ----------------------------------------------------

def apply_edit(receivable_id: str, field: str, new_value, reason: str | None = None):
    """Edytuje pole i zapisuje wpis do historii (stara -> nowa wartość)."""
    rec = db.get_receivable(receivable_id)
    if rec is None:
        raise ValueError("Nie znaleziono należności.")
    old_value = rec.get(field)
    if str(old_value) == str(new_value):
        return
    db.update_receivable(receivable_id, **{field: new_value}, updated_at=_now())
    db.add_history({
        "id": new_id(), "receivable_id": receivable_id, "field": field,
        "old_value": None if old_value is None else str(old_value),
        "new_value": None if new_value is None else str(new_value),
        "reason": reason, "changed_at": _now(),
    })


# ---- Transze -------------------------------------------------------------------

def replace_installments(receivable_id: str, items: list) -> dict:
    """Zastępuje CAŁY harmonogram transz. Twarda walidacja: suma kwot MUSI się
    równać amount_due (z tolerancją grosza). Transze z odnotowaną wpłatą (paid_amount>0),
    które nie występują w nowej liście, NIE są usuwane (chroni historię wpłat) —
    zamiast tego zgłaszamy błąd i prosimy o ich zachowanie.

    Walidacja (suma ORAZ ochrona opłaconych rat) biegnie W CAŁOŚCI PRZED jakimkolwiek
    zapisem do bazy — inaczej błąd wykryty w połowie zostawiałby połowicznie
    zapisany, niespójny harmonogram."""
    rec = db.get_receivable(receivable_id)
    if rec is None:
        raise ValueError("Nie znaleziono należności.")

    new_sum = round(sum(float(i.get("amount") or 0) for i in items), 2)
    due = round(float(rec["amount_due"]), 2)
    if abs(new_sum - due) > TOLERANCE:
        raise ValueError(
            f"Suma rat ({new_sum:.2f} zł) różni się od kwoty należności ({due:.2f} zł) "
            f"o {new_sum - due:+.2f} zł. Popraw kwoty rat, żeby się sumowały dokładnie."
        )

    existing = {i["id"]: i for i in db.list_installments(receivable_id)}
    kept_ids = {it.get("id") for it in items if it.get("id") in existing}
    for iid, old in existing.items():
        if iid not in kept_ids and float(old.get("paid_amount") or 0) > TOLERANCE:
            raise ValueError(
                f"Rata „{old.get('label') or iid}” ma odnotowaną wpłatę — nie można jej usunąć "
                f"z harmonogramu. Zostaw ją na liście (możesz zmienić kwotę/termin)."
            )

    # Walidacja przeszła — dopiero teraz zapisujemy.
    for it in items:
        iid = it.get("id")
        if iid in kept_ids:
            db.update_installment(iid, label=it.get("label"), amount=float(it["amount"]),
                                  due_date=it.get("due_date"), note=it.get("note"))
        else:
            db.add_installment({
                "id": new_id(), "receivable_id": receivable_id, "label": it.get("label"),
                "amount": float(it["amount"]), "due_date": it.get("due_date"),
                "status": "oczekuje", "paid_amount": 0.0, "paid_at": None,
                "note": it.get("note"), "created_at": _now(),
            })
    for iid in existing:
        if iid not in kept_ids:
            db.delete_installment(iid)

    db.add_history({
        "id": new_id(), "receivable_id": receivable_id, "field": "installments",
        "old_value": None, "new_value": f"{len(items)} rat, suma {new_sum:.2f} zł",
        "reason": None, "changed_at": _now(),
    })
    db.update_receivable(receivable_id, updated_at=_now())
    return receivable_view(db.get_receivable(receivable_id))


def pay_installment(installment_id: str, amount: float, paid_at: str | None = None, note: str | None = None):
    inst = db.get_installment(installment_id)
    if inst is None:
        raise ValueError("Nie znaleziono raty.")
    paid_at = paid_at or _now()[:10]
    new_paid = round(float(inst.get("paid_amount") or 0) + float(amount), 2)
    status = "oplacona" if new_paid >= float(inst["amount"]) - TOLERANCE else "czesciowo_oplacona"
    db.update_installment(installment_id, paid_amount=new_paid, paid_at=paid_at,
                          status=status, note=note if note is not None else inst.get("note"))
    db.add_payment({
        "id": new_id(), "receivable_id": inst["receivable_id"], "installment_id": installment_id,
        "amount": round(float(amount), 2), "paid_at": paid_at, "note": note, "created_at": _now(),
    })
    db.add_history({
        "id": new_id(), "receivable_id": inst["receivable_id"], "field": "installment_payment",
        "old_value": None, "new_value": f"+{float(amount):.2f} zł (rata „{inst.get('label') or installment_id}”)",
        "reason": note, "changed_at": paid_at,
    })
    db.update_receivable(inst["receivable_id"], updated_at=_now())
    return receivable_view(db.get_receivable(inst["receivable_id"]))


def pay_receivable(receivable_id: str, amount: float, paid_at: str | None = None, note: str | None = None):
    """Odnotowanie wpłaty BEZ podziału na transze (prosta ścieżka). `paid_at` to
    DOWOLNA data (także wsteczna) — trafia do listy wpłat i do historii."""
    rec = db.get_receivable(receivable_id)
    if rec is None:
        raise ValueError("Nie znaleziono należności.")
    if db.list_installments(receivable_id):
        raise ValueError("Ta należność ma harmonogram rat — odnotuj wpłatę przy konkretnej racie.")
    paid_at = paid_at or _now()[:10]
    new_paid = round(float(rec.get("paid_amount") or 0) + float(amount), 2)
    db.update_receivable(receivable_id, paid_amount=new_paid, updated_at=_now())
    db.add_payment({
        "id": new_id(), "receivable_id": receivable_id, "installment_id": None,
        "amount": round(float(amount), 2), "paid_at": paid_at, "note": note, "created_at": _now(),
    })
    db.add_history({
        "id": new_id(), "receivable_id": receivable_id, "field": "payment",
        "old_value": None, "new_value": f"+{float(amount):.2f} zł",
        "reason": note, "changed_at": paid_at,
    })
    return receivable_view(db.get_receivable(receivable_id))


# ---- Podpozycje (kary umowne, korekty) -----------------------------------------

ITEM_KIND_LABELS = {"kara": "Kara umowna", "korekta": "Korekta", "inne": "Inne"}


def add_receivable_item(receivable_id: str, kind: str, amount: float, label: str | None = None,
                        item_date: str | None = None, note: str | None = None) -> dict:
    """Dolicza podpozycję (karę umowną, korektę, inne) do faktury — zmienia amount_due
    o `amount` (może być ujemna). Jeśli są już raty, ich suma przestanie się zgadzać
    (installments_balanced=false) — to świadomy sygnał, żeby poprawić harmonogram."""
    rec = db.get_receivable(receivable_id)
    if rec is None:
        raise ValueError("Nie znaleziono należności.")
    kind = kind if kind in ITEM_KIND_LABELS else "inne"
    amount = round(float(amount), 2)
    if amount == 0:
        raise ValueError("Kwota podpozycji nie może być zerowa.")
    iid = new_id()
    db.add_receivable_item({
        "id": iid, "receivable_id": receivable_id, "kind": kind, "label": label or None,
        "amount": amount, "item_date": item_date or None, "note": note, "created_at": _now(),
    })
    new_due = round(float(rec["amount_due"]) + amount, 2)
    db.update_receivable(receivable_id, amount_due=new_due, updated_at=_now())
    desc = ITEM_KIND_LABELS[kind] + (f" — {label}" if label else "")
    db.add_history({
        "id": new_id(), "receivable_id": receivable_id, "field": "item",
        "old_value": None, "new_value": f"{desc}: {amount:+.2f} zł",
        "reason": note, "changed_at": item_date or _now()[:10],
    })
    return receivable_view(db.get_receivable(receivable_id))


def delete_receivable_item(item_id: str) -> dict:
    item = db.get_receivable_item(item_id)
    if item is None:
        raise ValueError("Nie znaleziono podpozycji.")
    rec = db.get_receivable(item["receivable_id"])
    db.delete_receivable_item(item_id)
    new_due = round(float(rec["amount_due"]) - float(item["amount"]), 2)
    db.update_receivable(item["receivable_id"], amount_due=new_due, updated_at=_now())
    desc = ITEM_KIND_LABELS.get(item["kind"], item["kind"]) + (f" — {item['label']}" if item.get("label") else "")
    db.add_history({
        "id": new_id(), "receivable_id": item["receivable_id"], "field": "item_removed",
        "old_value": f"{desc}: {float(item['amount']):+.2f} zł", "new_value": None,
        "reason": None, "changed_at": _now()[:10],
    })
    return receivable_view(db.get_receivable(item["receivable_id"]))
