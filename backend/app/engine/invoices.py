"""
Generowanie faktur (import do SaldeoSMART) z gotowego rozliczenia jednostek.

Mechanika odwzorowana 1:1 ze starego skoroszytu (arkusz „Wzór dodawania faktur"
+ „Dane_do_faktur" + „Słownik"):

- każda JEDNOSTKA = jedna faktura wielopozycyjna,
- pozycje = rozbicie na kategorie badań („Badanie" — jak w eksporcie importowym:
  RTG/TK/MR/MMG + priorytet + ANGIO/ONKO/PORÓWNAWCZE), z ilością i ceną jednostkową,
- badania porównawcze dają DODATKOWĄ linię „PORÓWNAWCZE" po stawce porównawczej,
- na końcu (o ile w cenniku jest wiersz „WSPARCIE;jednostka;kwota" > 0) linia
  „WSPARCIE" ze stawką VAT 23%,
- dane nabywcy (pełna nazwa, adres, kod, miejscowość) oraz termin płatności [dni]
  pochodzą ze Słownika jednostek (edytowalnego w zakładce Faktury),
- Data wystawienia: wspólna dla wszystkich, z możliwością indywidualnego wyjątku,
- Data dostawy: ostatni dzień rozliczanego miesiąca,
- Termin płatności = Data wystawienia + termin [dni] ze Słownika.

Wartości pozycji sumują się CO DO GROSZA do przychodu jednostki z silnika
przychodów (revenue.build_revenue) — czytamy z tych samych plików sprawdzonych.
"""

from __future__ import annotations

import calendar
import datetime as _dt

import pandas as pd

from app.engine.summary import generate_badanie_string, extract_multiplier
from app.engine.billing import (
    build_price_key,
    resolve_unit_price,
    prepare_adjustments,
    get_unit_adjustments,
    get_excluded_units,
    _prices_to_pmap,
    _norm_unit,
)
from app.engine.revenue import _studies_dir, _load_prices
from app.engine.invoice_template import SALDEO_HEADERS, SALDEO_HINTS, COL_WIDTHS

# --- Stałe faktury (jak w szablonie SaldeoSMART) ---------------------------
PRODUCT_PREFIX = "Wynagrodzenie za świadczenie usług medycznych w systemie teleradiologii - "
WSPARCIE_LABEL = "WSPARCIE"
DEFAULT_BANK_ACCOUNT = "59 1160 2202 0000 0005 3366 4933"
PKWIU = "86.90"
CURRENCY = "PLN"
UNIT_SZT = "szt."
PAYMENT_FORM = "przelew"
VAT_ZW = "zw."
ZW_BASIS = "a43"
VAT_WSPARCIE = "23%"
DEFAULT_PAYMENT_TERM_DAYS = 14

_STUDIES_SHEET = "Szczegółowe"
_REQUIRED_COLS = ["Klient", "Modalność", "Priorytet opisu",
                  "Rodzaj procedury rozlicz.", "Procedura", "Procedura rozlicz."]


# --- Kolejność pozycji w obrębie faktury (kosmetyka, jak we wzorcu) --------
def _line_sort_key(badanie: str):
    b = str(badanie)
    if b == WSPARCIE_LABEL:
        return (99, 0, 0, 0, b)
    if b.startswith("RTG"):
        mod = 0
    elif b.startswith("TK"):
        mod = 1
    elif b.startswith("MR"):
        mod = 2
    elif b.startswith("MMG"):
        mod = 3
    else:
        mod = 4
    comp = 1 if "PORÓWNAWCZE" in b else 0
    prio = 0 if "CITO-CITO" in b else (1 if "Pilny" in b else (2 if "Planowy" in b else 3))
    sub = 1 if "ANGIO" in b else (2 if "ONKO" in b else 0)
    return (mod, comp, prio, sub, b)


# --- Wyliczenie pozycji per jednostka --------------------------------------
def compute_invoice_lines(wynik_dir: str, cennik_dir: str) -> tuple[dict, dict]:
    """
    Zwraca (lines_by_unit, wsparcie_by_unit):
      lines_by_unit: { klient: [ {badanie, ilosc, cena} ... ] }  (bez WSPARCIE, posortowane)
      wsparcie_by_unit: { klient: kwota_wsparcia }               (tylko > 0)

    Ceny i ilości liczone identycznie jak w rozliczeniu jednostek (revenue.py):
    ta sama drabinka cen (resolve_unit_price), ten sam klucz (build_price_key),
    ta sama dopłata porównawcza, te same pliki źródłowe (pliki sprawdzone).
    """
    import glob
    import os

    prices = _load_prices(cennik_dir)
    if prices is None:
        raise ValueError("Brak cennika jednostek (pliku CSV) dla tego rozliczenia.")
    pmap = _prices_to_pmap(prices)
    adj = prepare_adjustments(get_unit_adjustments())
    excluded = get_excluded_units()

    src_dir = _studies_dir(wynik_dir)
    if not os.path.isdir(src_dir):
        raise ValueError("Brak plików rozliczenia dla wskazanego miesiąca.")

    # agregacja: (klient, badanie) -> [suma ilości (okolic), cena jednostkowa]
    agg: dict[tuple[str, str], list] = {}

    for path in glob.glob(os.path.join(src_dir, "*.xlsx")):
        if os.path.basename(path).startswith("~$"):
            continue
        try:
            df = pd.read_excel(path, sheet_name=_STUDIES_SHEET,
                               dtype={"Badania do porównania": "str"})
        except Exception:
            continue
        if not all(c in df.columns for c in _REQUIRED_COLS):
            continue
        df = df.dropna(subset=["Modalność", "Klient"])
        if df.empty:
            continue

        for _, r in df.iterrows():
            kl = str(r["Klient"]).strip()
            if not kl or _norm_unit(kl) in excluded:
                continue
            okolice = extract_multiplier(r.get("Procedura rozlicz.", ""))

            # --- linia bazowa (pełna stawka) ---
            rb = r.copy()
            rb["Badania do porównania"] = 0
            base_bad = generate_badanie_string(rb, include_comparative_word=False)
            base_key = build_price_key(rb)
            base_price = resolve_unit_price(pmap, kl, base_key, adj)
            _add(agg, kl, base_bad, okolice, base_price)

            # --- linia porównawcza (osobna, po stawce porównawczej) ---
            porow = pd.to_numeric(r.get("Badania do porównania", 0), errors="coerce")
            if pd.notna(porow) and porow > 0 and str(r["Modalność"]).strip().upper() in ("TK", "MR"):
                rc = r.copy()
                rc["Badania do porównania"] = 1
                comp_key = build_price_key(rc)
                if comp_key != base_key:  # dopłata istnieje tylko dla TK/MR
                    comp_bad = generate_badanie_string(rc, include_comparative_word=True)
                    comp_price = resolve_unit_price(pmap, kl, comp_key, adj)
                    _add(agg, kl, comp_bad, okolice, comp_price)

    # złożenie do struktury per jednostka
    lines_by_unit: dict[str, list] = {}
    for (kl, bad), (ilosc, cena) in agg.items():
        if ilosc <= 0:
            continue
        lines_by_unit.setdefault(kl, []).append(
            {"badanie": bad, "ilosc": int(ilosc), "cena": round(float(cena or 0), 4)}
        )
    for kl in lines_by_unit:
        lines_by_unit[kl].sort(key=lambda x: _line_sort_key(x["badanie"]))

    # WSPARCIE per jednostka (z cennika jednostek: BADANIE=WSPARCIE)
    wsparcie_by_unit: dict[str, float] = {}
    for kl in lines_by_unit:
        w = pmap.get((kl, WSPARCIE_LABEL))
        if w is not None and pd.notna(w) and float(w) > 0:
            wsparcie_by_unit[kl] = round(float(w), 2)

    return lines_by_unit, wsparcie_by_unit


def _add(agg, kl, bad, okolice, price):
    if not bad:
        return
    # linie bez dodatniej stawki pomijamy — nie trafiają na fakturę (spójnie z przychodem)
    if price is None or not pd.notna(price) or float(price) <= 0:
        # nadal dodajemy ilość, ale bez ceny nie ma pozycji — pomijamy całkowicie
        return
    rec = agg.setdefault((kl, bad), [0, None])
    rec[0] += int(okolice)
    # cena jednostkowa jest stała w obrębie (klient, badanie) — bierzemy najwyższą na wszelki wypadek
    if rec[1] is None or float(price) > rec[1]:
        rec[1] = float(price)


# --- Daty -------------------------------------------------------------------
def last_day_of_period(period: str) -> _dt.date:
    """'2026-07' → date(2026,7,31)."""
    y, m = period.split("-")
    y, m = int(y), int(m)
    return _dt.date(y, m, calendar.monthrange(y, m)[1])


def _fmt(d) -> str:
    if isinstance(d, _dt.date):
        return d.strftime("%Y-%m-%d")
    return str(d or "")


def _parse_date(s) -> _dt.date | None:
    if isinstance(s, _dt.date):
        return s
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# --- Budowa skoroszytu ------------------------------------------------------
def build_invoice_workbook(
    lines_by_unit: dict,
    wsparcie_by_unit: dict,
    slownik: dict,
    issue_date: str,
    delivery_date,
    overrides: dict | None = None,
    bank_account: str = DEFAULT_BANK_ACCOUNT,
):
    """
    Tworzy openpyxl.Workbook z arkuszem „Faktury" w formacie importu SaldeoSMART.

    - slownik: { system_name: {full_name, address, postal_code, city, payment_term_days} }
    - issue_date: 'YYYY-MM-DD' wspólna data wystawienia
    - delivery_date: date/'YYYY-MM-DD' — data dostawy (koniec miesiąca)
    - overrides: { system_name: 'YYYY-MM-DD' } — indywidualne daty wystawienia

    Zwraca (workbook, meta) gdzie meta zawiera listę ostrzeżeń (jednostki spoza Słownika).
    """
    from openpyxl import Workbook

    overrides = overrides or {}
    hdr_idx = {h: i for i, h in enumerate(SALDEO_HEADERS)}
    NCOL = len(SALDEO_HEADERS)

    def col(name):
        return hdr_idx[name]

    wb = Workbook()
    ws = wb.active
    ws.title = "Faktury"

    # wiersz 1 (nagłówki) + wiersz 2 (podpowiedzi) — 1:1 ze wzorca
    ws.append(list(SALDEO_HEADERS))
    ws.append(list(SALDEO_HINTS))

    delivery_str = _fmt(delivery_date)
    default_issue = _parse_date(issue_date)

    warnings: list[str] = []
    units = sorted(lines_by_unit.keys())
    lp = 0

    for unit in units:
        lines = list(lines_by_unit.get(unit, []))
        w = wsparcie_by_unit.get(unit)
        if w and w > 0:
            lines = lines + [{"badanie": WSPARCIE_LABEL, "ilosc": 1, "cena": w}]
        if not lines:
            continue

        info = slownik.get(unit) or {}
        if not info:
            warnings.append(unit)
        full_name = info.get("full_name", "")
        address = info.get("address", "")
        postal = info.get("postal_code", "")
        city = info.get("city", "")
        try:
            term_days = int(info.get("payment_term_days", DEFAULT_PAYMENT_TERM_DAYS))
        except (TypeError, ValueError):
            term_days = DEFAULT_PAYMENT_TERM_DAYS

        issue_d = _parse_date(overrides.get(unit)) or default_issue
        issue_str = _fmt(issue_d) if issue_d else ""
        due_str = _fmt(issue_d + _dt.timedelta(days=term_days)) if issue_d else ""

        lp += 1
        for pos, line in enumerate(lines):
            row = [None] * NCOL
            is_wsparcie = line["badanie"] == WSPARCIE_LABEL
            first = pos == 0

            # dane wspólne dla każdej pozycji (nabywca + waluta)
            row[col("Nabywca (nazwa skrócona kontrahenta)")] = unit
            row[col("Nazwa pełna kontrahenta")] = full_name
            row[col("Adres")] = address
            row[col("Kod pocztowy")] = postal
            row[col("Miejscowość")] = city
            row[col("Waluta")] = CURRENCY

            # pozycja towarowa
            name = WSPARCIE_LABEL if is_wsparcie else (PRODUCT_PREFIX + line["badanie"])
            row[col("Nazwa towaru")] = name
            row[col("PKWiU")] = PKWIU
            row[col("Ilość")] = line["ilosc"]
            row[col("Jednostka")] = UNIT_SZT
            row[col("Cena jedn. brutto")] = line["cena"]
            row[col("Stawka VAT")] = VAT_WSPARCIE if is_wsparcie else VAT_ZW
            row[col("Podstawa zastosowania stawki ZW")] = "" if is_wsparcie else ZW_BASIS
            row[col("Forma płatności")] = PAYMENT_FORM

            # tylko pierwszy wiersz faktury: numer, daty, konto bankowe
            if first:
                row[col("Lp.")] = lp
                row[col("Data wystawienia")] = issue_str
                row[col("Data dostawy")] = delivery_str
                row[col("Termin płatności")] = due_str
                row[col("Konto bankowe")] = bank_account

            ws.append(row)

    # szerokości kolumn (kosmetyka)
    for letter, width in COL_WIDTHS.items():
        try:
            ws.column_dimensions[letter].width = width
        except Exception:
            pass

    meta = {
        "units": lp,
        "units_missing_slownik": warnings,
    }
    return wb, meta
