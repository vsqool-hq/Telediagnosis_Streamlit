"""
Silnik modułu CASHFLOW — prognoza przepływów pieniężnych: przychody z jednostek
(fakt = wpłaty z Windykacji, prognoza = pozostałe kwoty wg terminu płatności) i
koszty lekarzy (WYŁĄCZNIE prognoza — nie śledzimy jeszcze rzeczywistych wypłat
lekarzom, więc zakładamy stały termin: koniec miesiąca rozliczeniowego + N dni
kalendarzowych, patrz `doctor_cost_payment_term_days` w ustawieniach).

Kubełkowanie: tygodniowe „kubełki" po 7 dni, licząc od dziś (kubełek 0 = dziś..
+6 dni), wstecz WEEKS_BACK tygodni i w przód WEEKS_FORWARD tygodni — jak typowa
„13-tygodniowa" prognoza gotówkowa, z odrobiną historii dla kontekstu. Kubełki
PRZED dzisiejszym (indeks < 0) to FAKT; kubełek 0 i późniejsze to PROGNOZA — to
jedyna granica fakt/prognoza w całym module (koszty lekarzy nigdy nie są
„faktem", ale trafiają do kubełka wg założonego terminu tak samo jak przychód).

Skumulowane saldo na wykresie liczy się TYLKO w obrębie widocznego okna (zaczyna
od zera na starcie okna) — to trend, nie prawdziwe saldo konta (tego system nie
zna, bo nie ma integracji bankowej). Kafelek „saldo narastająco" obok jest liczony
NIEZALEŻNIE, po całej historii — te dwie liczby świadomie się nie muszą zgadzać.
"""

import calendar
import datetime
import json
import os

from app import db
from app.engine import windykacja as wnd
from app.storage import job_paths

WEEKS_BACK = 8
WEEKS_FORWARD = 13
TOLERANCE = 0.01


def _today() -> datetime.date:
    return datetime.date.today()


def _month_end(period: str) -> datetime.date:
    y, m = int(period[:4]), int(period[5:7])
    return datetime.date(y, m, calendar.monthrange(y, m)[1])


def doctor_cost_due_date(period: str, term_days: int) -> datetime.date:
    return _month_end(period) + datetime.timedelta(days=term_days)


def _cached_doctor_billing_total(job_id: str) -> float | None:
    """Suma kosztu lekarzy (badania + gotowość/triaż) z cache'a rozliczenia lekarzy
    dla danego zadania — best-effort, bez wymuszania świeżości silnika (to tylko
    zgrubna prognoza, nie źródło prawdy dla samego rozliczenia lekarzy)."""
    path = os.path.join(job_paths(job_id)["base"], "lekarze", "billing.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("empty"):
        return None
    return round(float((data.get("validation") or {}).get("total_value") or 0), 2)


def build_cashflow() -> dict:
    from app.routers.stats import latest_jobs_by_month

    today = _today()
    cfg = db.get_settings()
    doctor_term = int(cfg.get("doctor_cost_payment_term_days") or 14)
    window_start_days = -WEEKS_BACK * 7
    window_end_days = WEEKS_FORWARD * 7 + 6

    buckets = []
    for i in range(-WEEKS_BACK, WEEKS_FORWARD + 1):
        start = today + datetime.timedelta(days=7 * i)
        end = start + datetime.timedelta(days=6)
        buckets.append({
            "index": i, "start": start.isoformat(), "end": end.isoformat(),
            "label": f"{start.day:02d}.{start.month:02d}",
            "inflow_actual": 0.0, "inflow_forecast": 0.0, "outflow_forecast": 0.0,
        })
    offset = WEEKS_BACK  # buckets[offset] == kubełek indeksu 0 (dziś..+6)

    def add_in_window(field: str, d: datetime.date, amount: float, clamp_future: bool):
        """Dolicza kwotę do kubełka daty `d`, jeśli mieści się w widocznym oknie.
        Poza oknem w przyszłości: przypnij do ostatniego kubełka (żeby suma prognozy
        na wykresie zgadzała się z KPI). Poza oknem w przeszłości: pomiń (to już
        jest w kafelku „saldo narastająco", osobnym, niezależnym od wykresu)."""
        delta = (d - today).days
        if delta < window_start_days:
            return
        if delta > window_end_days:
            if not clamp_future:
                return
            delta = window_end_days
        i = delta // 7
        buckets[i + offset][field] += amount

    # ---- Przychody: fakt (wpłaty) + prognoza (pozostałe wg terminu) -----------
    wnd.sync_receivables()
    revenue_collected_to_date = 0.0  # KPI: wszystkie wpłaty w historii, niezależnie od okna wykresu
    revenue_forecast_total = 0.0
    overdue_amount = 0.0
    for rec in db.list_receivables():
        view = wnd.receivable_view(rec)
        for p in view["payments"]:
            amt = round(float(p["amount"]), 2)
            try:
                d = datetime.date.fromisoformat(p["paid_at"])
            except (TypeError, ValueError):
                d = today
            if d <= today:
                revenue_collected_to_date += amt
            add_in_window("inflow_actual", d, amt, clamp_future=False)
        remaining = float(view["remaining"])
        if remaining > TOLERANCE:
            due = view.get("due_date")
            d = datetime.date.fromisoformat(due) if due else today
            if d < today:
                d = today  # zaległe — nieznany termin wpływu, pokazujemy jako „do ściągnięcia teraz"
            revenue_forecast_total += remaining
            if view.get("is_overdue"):
                overdue_amount += remaining
            add_in_window("inflow_forecast", d, remaining, clamp_future=True)

    # ---- Koszty lekarzy: WYŁĄCZNIE prognoza wg założonego terminu -------------
    doctor_cost_settled_to_date = 0.0  # KPI: cała historia
    doctor_cost_forecast_total = 0.0
    for period, info in latest_jobs_by_month().items():
        total = _cached_doctor_billing_total(info["job_id"])
        if not total:
            continue
        due = doctor_cost_due_date(period, doctor_term)
        if due <= today:
            doctor_cost_settled_to_date += total
        else:
            doctor_cost_forecast_total += total
        add_in_window("outflow_forecast", due, total, clamp_future=True)

    # ---- Skumulowane saldo w obrębie okna wykresu (start = 0 na początku okna) -
    running = 0.0
    for b in buckets:
        net = b["inflow_actual"] + b["inflow_forecast"] - b["outflow_forecast"]
        running += net
        if b["index"] < 0:
            b["balance_actual"] = round(running, 2)
            b["balance_forecast"] = None
        else:
            b["balance_actual"] = None
            b["balance_forecast"] = round(running, 2)
        b["inflow_actual"] = round(b["inflow_actual"], 2)
        b["inflow_forecast"] = round(b["inflow_forecast"], 2)
        b["outflow_forecast"] = round(b["outflow_forecast"], 2)
        b["net"] = round(net, 2)
    if offset > 0:
        # Most przy „dziś": kubełek 0 dostaje też punkt fakt=ostatni fakt, żeby
        # linia prognozy zaczynała się dokładnie tam, gdzie kończy się linia faktu.
        buckets[offset]["balance_actual"] = buckets[offset - 1]["balance_actual"]

    def _forecast_within(days: int) -> tuple:
        end = today + datetime.timedelta(days=days)
        inflow = outflow = 0.0
        for b in buckets:
            if b["index"] < 0:
                continue
            if datetime.date.fromisoformat(b["start"]) > end:
                continue
            inflow += b["inflow_forecast"]
            outflow += b["outflow_forecast"]
        return round(inflow, 2), round(outflow, 2)

    inflow_90, outflow_90 = _forecast_within(90)

    return {
        "generated_at": today.isoformat(),
        "doctor_cost_payment_term_days": doctor_term,
        "buckets": buckets,
        "kpis": {
            "balance_to_date": round(revenue_collected_to_date - doctor_cost_settled_to_date, 2),
            "overdue_amount": round(overdue_amount, 2),
            "forecast_inflow_90d": inflow_90,
            "forecast_outflow_90d": outflow_90,
            "forecast_net_90d": round(inflow_90 - outflow_90, 2),
            "revenue_forecast_total": round(revenue_forecast_total, 2),
            "doctor_cost_forecast_total": round(doctor_cost_forecast_total, 2),
        },
    }
