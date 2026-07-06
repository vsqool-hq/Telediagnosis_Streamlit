"""
Integracja z TeamUp — godziny gotowości i triażu lekarzy.

Źródła:
  * TeamUp API (https://apidocs.teamup.com): dwa kalendarze — GRAFIK DYŻURÓW
    (gotowość) i TRIAŻ. Lekarz jest w TYTULE wydarzenia (np. „Piłat Krzysztof",
    czasem z dopiskiem typu „RTG"). Wydarzenia całodniowe i wpisy URLOP/L4
    pomijamy. Klucz API: zmienna środowiskowa TEAMUP_API_KEY (sekret Fly) albo
    plik /data/teamup.json (ustawiany w Ustawieniach).
  * Stawki: plik ZOBOWIĄZAŃ (source.xlsx aktywnego cennika lekarzy) — każda
    zakładka to lekarz, na dole wiersze GOTOWOŚĆ/GODZINA TRIAŻ w wariantach
    (powszedni/weekend/święta × 8:00-21:00/21:00-8:00).

Klasyfikacja godzin: każdą godzinę (ułamkowo, minutowo) przypisujemy do
wariantu wg DATY tej godziny: święto (polskie ustawowe) > weekend > powszedni;
pasmo 8:00–21:00 = dzień, reszta = noc. Triaż ma tylko dzień/noc.
"""

import os
import json
import datetime as dt
import urllib.request
import urllib.parse

API_BASE = "https://api.teamup.com"
# Domyślne kalendarze (z linków klienta) — można nadpisać w /data/teamup.json.
DEFAULT_CAL_GOTOWOSC = "ks4dfo7jwkbaqg2he8"
DEFAULT_CAL_TRIAZ = "ks9cti68r1xnjj5m9m"

# Tytuły wydarzeń pomijanych (nieobecności) — dopasowanie po fragmencie, bez liter wielkości.
SKIP_TOKENS = ("urlop", "l4", "zwolnien", "chorob", "nieobecn")

# Warianty rozliczeniowe: (rodzaj, pasmo, typ dnia) → etykieta do raportów.
VARIANTS = {
    ("G", "D", "POW"): "Gotowość 8:00–21:00",
    ("G", "N", "POW"): "Gotowość 21:00–8:00",
    ("G", "D", "WKD"): "Gotowość weekend 8:00–21:00",
    ("G", "N", "WKD"): "Gotowość weekend 21:00–8:00",
    ("G", "D", "SW"): "Gotowość święta 8:00–21:00",
    ("G", "N", "SW"): "Gotowość święta 21:00–8:00",
    ("T", "D", "*"): "Godzina triaż 8:00–21:00",
    ("T", "N", "*"): "Godzina triaż 21:00–8:00",
}


def _config_path() -> str:
    from app.storage import DATA_DIR
    return os.path.join(DATA_DIR, "teamup.json")


def _env_key() -> str:
    """Klucz z ENV — odporny na wielkość liter nazwy (sekret na Fly bywa
    'teamup_api_key' zamiast 'TEAMUP_API_KEY', a zmienne środowiskowe są
    case-sensitive)."""
    v = os.environ.get("TEAMUP_API_KEY")
    if v:
        return v.strip()
    for k, val in os.environ.items():
        if k.lower() == "teamup_api_key" and val:
            return val.strip()
    return ""


def load_config() -> dict:
    cfg = {}
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f) or {}
    except (OSError, ValueError):
        cfg = {}
    env_key = _env_key()
    file_key = (cfg.get("api_key") or "").strip()
    return {
        "api_key": env_key or file_key,
        "cal_gotowosc": cfg.get("cal_gotowosc") or DEFAULT_CAL_GOTOWOSC,
        "cal_triaz": cfg.get("cal_triaz") or DEFAULT_CAL_TRIAZ,
        "key_from_env": bool(env_key),
        "key_source": "env" if env_key else ("file" if file_key else "none"),
        # Nazwy zmiennych środowiskowych zawierające „teamup" (BEZ wartości) —
        # do diagnostyki „mam sekret, a apka go nie widzi".
        "env_names": sorted(k for k in os.environ if "teamup" in k.lower()),
    }


def save_config(api_key: str | None = None, cal_gotowosc: str | None = None,
                cal_triaz: str | None = None) -> dict:
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f) or {}
    except (OSError, ValueError):
        cfg = {}
    if api_key is not None:
        cfg["api_key"] = api_key.strip()
    if cal_gotowosc is not None:
        cfg["cal_gotowosc"] = cal_gotowosc.strip()
    if cal_triaz is not None:
        cfg["cal_triaz"] = cal_triaz.strip()
    os.makedirs(os.path.dirname(_config_path()), exist_ok=True)
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    return load_config()


# --- Święta polskie (ustawowe) ---------------------------------------------

def _easter(year: int) -> dt.date:
    """Niedziela wielkanocna (algorytm Meeusa)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def polish_holidays(year: int) -> set:
    e = _easter(year)
    days = {
        dt.date(year, 1, 1), dt.date(year, 1, 6),
        e, e + dt.timedelta(days=1),                      # Wielkanoc + poniedziałek
        dt.date(year, 5, 1), dt.date(year, 5, 3),
        e + dt.timedelta(days=49),                        # Zielone Świątki
        e + dt.timedelta(days=60),                        # Boże Ciało
        dt.date(year, 8, 15), dt.date(year, 11, 1), dt.date(year, 11, 11),
        dt.date(year, 12, 25), dt.date(year, 12, 26),
    }
    if year >= 2025:
        days.add(dt.date(year, 12, 24))                   # Wigilia — ustawowe od 2025
    return days


def _day_type(d: dt.date, holidays: set) -> str:
    if d in holidays:
        return "SW"
    if d.weekday() >= 5:
        return "WKD"
    return "POW"


# --- TeamUp API --------------------------------------------------------------

def fetch_events(cal_key: str, start: dt.date, end: dt.date, api_key: str) -> list:
    """Wydarzenia kalendarza w przedziale dat (włącznie). Rzuca RuntimeError z
    czytelnym komunikatem przy problemach z API/kluczem."""
    q = urllib.parse.urlencode({"startDate": start.isoformat(), "endDate": end.isoformat()})
    url = f"{API_BASE}/{cal_key}/events?{q}"
    req = urllib.request.Request(url, headers={"Teamup-Token": api_key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:  # noqa: PERF203
        try:
            detail = json.load(e).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            detail = ""
        raise RuntimeError(f"TeamUp HTTP {e.code}: {detail or e.reason}")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"TeamUp — błąd połączenia: {e}")
    return data.get("events", [])


def _skip_title(title: str) -> bool:
    t = str(title or "").lower()
    return any(tok in t for tok in SKIP_TOKENS)


def _slices(start: dt.datetime, end: dt.datetime):
    """Tnie przedział na kawałki w obrębie pełnych godzin zegarowych.
    Zwraca (data, godzina, ułamek_godziny)."""
    cur = start
    while cur < end:
        nxt = (cur.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1))
        nb = min(end, nxt)
        yield cur.date(), cur.hour, (nb - cur).total_seconds() / 3600.0
        cur = nb


def hours_by_variant(events: list, kind: str, month_start: dt.date, month_end: dt.date,
                     holidays: set) -> dict:
    """Sumuje godziny wydarzeń per (tytuł, wariant). kind: 'G' (gotowość) / 'T' (triaż).
    Godziny spoza miesiąca (wydarzenia na styku) są przycinane do miesiąca."""
    out: dict = {}
    for ev in events:
        if ev.get("all_day") or _skip_title(ev.get("title")):
            continue
        try:
            s = dt.datetime.fromisoformat(ev["start_dt"])
            e = dt.datetime.fromisoformat(ev["end_dt"])
        except (KeyError, ValueError):
            continue
        if e <= s:
            continue
        title = str(ev.get("title") or "").strip()
        if not title:
            continue
        for d, hour, frac in _slices(s, e):
            if not (month_start <= d <= month_end):
                continue
            band = "D" if 8 <= hour < 21 else "N"
            day_t = _day_type(d, holidays) if kind == "G" else "*"
            key = (kind, band, day_t)
            per = out.setdefault(title, {})
            per[key] = per.get(key, 0.0) + frac
    return out


# --- Stawki z pliku ZOBOWIĄZAŃ ----------------------------------------------

def parse_availability_rates(workbook_path: str) -> dict:
    """
    Czyta stawki gotowości/triażu z KAŻDEJ zakładki (zakładka = lekarz).
    Zwraca { doctor_key(nazwa zakładki): {"name": zakładka, "rates": {wariant: stawka}} }.
    Wiersz rozpoznajemy po kolumnie A: GOTOWOŚĆ/TRIAŻ (+ ŚWIĘTA/WEEKEND) i godzinie
    startu pasma (8→dzień, 21→noc). Stawka w kolumnie B.
    """
    import re
    from openpyxl import load_workbook
    from app.engine.cennik_lekarzy_convert import doctor_key

    wb = load_workbook(workbook_path, data_only=True, read_only=True)
    out = {}
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        rates = {}
        for row in ws.iter_rows(min_col=1, max_col=2, values_only=True):
            label = str(row[0] or "").strip().upper()
            if not label or ("GOTOW" not in label and "TRIA" not in label):
                continue
            m = re.search(r"(\d{1,2})[:.]?\d{0,2}\s*[-–]", label)
            if not m:
                continue
            band = "D" if int(m.group(1)) == 8 else "N"
            try:
                rate = float(row[1] or 0)
            except (TypeError, ValueError):
                continue
            if "TRIA" in label:
                rates[("T", band, "*")] = rate
            else:
                day_t = "SW" if ("ŚWI" in label or "SWI" in label) else \
                        ("WKD" if "WEEKEND" in label else "POW")
                rates[("G", band, day_t)] = rate
        if rates:
            out[doctor_key(sheet)] = {"name": sheet.strip(), "rates": rates}
    wb.close()
    return out


# --- Dopasowanie lekarza z tytułu wydarzenia ---------------------------------

def match_doctor(title: str, known: dict) -> str | None:
    """
    Dopasowuje tytuł wydarzenia do klucza lekarza (known: {doctor_key: ...}).
    1) dokładny klucz; 2) klucz lekarza zawarty w tytule (tytuł ma dopiski, np.
    „Dreżewski Karol RTG"); 3) tytuł zawarty w kluczu (samo nazwisko) — tylko
    gdy pasuje DOKŁADNIE jeden lekarz.
    """
    from app.engine.cennik_lekarzy_convert import doctor_key
    tk = doctor_key(title)
    if not tk:
        return None
    if tk in known:
        return tk
    t_tokens = set(tk.split(" "))
    contained = [k for k in known if set(k.split(" ")) <= t_tokens]
    if len(contained) == 1:
        return contained[0]
    if len(contained) > 1:   # np. dwóch lekarzy o tym samym nazwisku — wybierz dłuższe dopasowanie
        contained.sort(key=lambda k: -len(set(k.split(" ")) & t_tokens))
        if len(set(contained[0].split(" ")) & t_tokens) > len(set(contained[1].split(" ")) & t_tokens):
            return contained[0]
        return None
    reverse = [k for k in known if t_tokens <= set(k.split(" "))]
    return reverse[0] if len(reverse) == 1 else None


# --- Główne liczenie ---------------------------------------------------------

def compute_availability(period: str) -> dict:
    """
    Gotowość + triaż za miesiąc rozliczenia „YYYY-MM": godziny z TeamUp × stawki
    z pliku ZOBOWIĄZAŃ. Zwraca:
      { doctors: {lek_key: {name, items:[{label,hours,rate,amount}], total}},
        sum_total, sum_gotowosc, sum_triaz, unmatched: [tytuły], period }
    Rzuca RuntimeError z czytelnym powodem (brak klucza / pliku zobowiązań / API).
    """
    cfg = load_config()
    if not cfg["api_key"]:
        raise RuntimeError("Brak klucza API TeamUp (ustaw sekret TEAMUP_API_KEY lub wpisz w Ustawieniach).")
    from app.engine.commitments import active_commitments_workbook
    wb_path, _disp = active_commitments_workbook()
    if not wb_path:
        raise RuntimeError("Brak pliku zobowiązań (wgraj cennik lekarzy jako .xlsx przez konwerter).")

    y, m = int(period[:4]), int(period[5:7])
    month_start = dt.date(y, m, 1)
    month_end = (dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)) - dt.timedelta(days=1)
    holidays = polish_holidays(y) | polish_holidays(y + 1)

    rates_by_doc = parse_availability_rates(wb_path)

    # Pobieramy z 1-dniowym marginesem (dyżur nocny zaczęty ostatniego dnia
    # poprzedniego miesiąca) — i tak przycinamy godziny do miesiąca.
    fetch_from = month_start - dt.timedelta(days=1)
    fetch_to = month_end + dt.timedelta(days=1)
    per_title: dict = {}
    for kind, cal in (("G", cfg["cal_gotowosc"]), ("T", cfg["cal_triaz"])):
        if not cal:
            continue
        events = fetch_events(cal, fetch_from, fetch_to, cfg["api_key"])
        part = hours_by_variant(events, kind, month_start, month_end, holidays)
        for title, variants in part.items():
            agg = per_title.setdefault(title, {})
            for k, v in variants.items():
                agg[k] = agg.get(k, 0.0) + v

    doctors: dict = {}
    unmatched: list = []
    for title, variants in per_title.items():
        lk = match_doctor(title, rates_by_doc)
        if lk is None:
            unmatched.append(title)
            continue
        doc = doctors.setdefault(lk, {"name": rates_by_doc[lk]["name"], "variants": {}})
        for k, v in variants.items():
            doc["variants"][k] = doc["variants"].get(k, 0.0) + v

    sum_g = sum_t = 0.0
    for lk, doc in doctors.items():
        rates = rates_by_doc[lk]["rates"]
        items, total = [], 0.0
        for k, hours in sorted(doc.pop("variants").items()):
            rate = float(rates.get(k, 0.0))
            amount = round(hours * rate, 2)
            total += amount
            if k[0] == "G":
                sum_g += amount
            else:
                sum_t += amount
            items.append({"label": VARIANTS.get(k, str(k)), "hours": round(hours, 2),
                          "rate": rate, "amount": amount, "no_rate": rate <= 0})
        doc["items"] = items
        doc["total"] = round(total, 2)
    return {
        "period": period,
        "doctors": doctors,
        "sum_total": round(sum_g + sum_t, 2),
        "sum_gotowosc": round(sum_g, 2),
        "sum_triaz": round(sum_t, 2),
        "unmatched": sorted(set(unmatched)),
    }
