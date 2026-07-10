"""
Konfiguracja silnika rozliczeniowego.

Wszystkie wartości, które wcześniej były zahardkodowane w backend.py,
żyją tutaj jako DEFAULT_CONFIG i są edytowalne z panelu Ustawienia.

Każde zadanie (job) uruchamiane jest w osobnym procesie (run_job.py),
który ustawia zmienną środowiskową TELEDIAG_CONFIG na ścieżkę pliku JSON
z konfiguracją. Silnik czyta ją przy imporcie, więc nadpisanie ustawień
nie wymaga modyfikacji kodu.
"""

import os
import json
import copy

# ==================================================================================
# DOMYŚLNA KONFIGURACJA — wartości przeniesione 1:1 z oryginalnego backend.py
# ==================================================================================

DEFAULT_CONFIG = {
    # Priorytety rodzajów procedur (wyższa liczba = wyższy priorytet przy korekcie)
    "priority_dict": {
        "MR": {
            "MR Angiografia": 4,
            "MR Inne - wtym prostata, miednica, jama brzuszna tkanki miekkie": 3,
            "MR Neurologia": 1,
            "MR Onkologia": 5,
            "MR Ortopedia": 2,
        },
        "TK": {
            "TK Angiografia": 2,
            "TK Zwykłe": 1,
            "TK Onkologia": 3,
        },
    },

    # Mapowanie priorytetu opisu na sufiks cennikowy
    "priority_map": {
        "CITO-CITO": "CITO",
        "Pilny": "PILNE",
        "Planowy": "PLANOWE",
        "CITO NA RATUNEK": "CITO",
        "CITO-UDAR": "CITO",
        "Bardzo pilny": "PILNE",
    },

    # Sufiksy dla TK wg rodzaju procedury
    "tk_suffix_map": {
        "TK Zwykłe": "",
        "TK Angiografia": "ANGIO",
        "TK Onkologia": "ONKO",
    },

    # Słowa kluczowe klasyfikacji anatomicznej MR
    "mr_glkrg_keywords": [
        "głow", "gło", "gl ", "mózg", "kręgosłup", "kregosłup", "kregoslup",
        "szyjn", "piersiow", "lędźwiow", "ledzwiow", "krzyżow", "krzyzow",
        "krg", "gł",
    ],
    "mr_stawy_keywords": [
        "staw", "bark", "kolan", "biodr", "łokc", "lokc", "nadgarst", "skok",
        "palc", "stop", "dłoń", "dlon", "ręk", "rek", "ramie", "ramię",
        "kończyn", "konczyn", "podudz", "uda", "udo", "mięśni", "miesni",
        "szkielet", "splot", "pięt", "piet", "przedram",
    ],

    # Kolory raportu Excel (kolejność priorytetów + rodzaje procedur)
    "master_priority_order": [
        "CITO NA RATUNEK", "CITO-UDAR", "Bardzo pilny",
        "CITO-CITO", "Pilny", "Planowy",
    ],
    "priority_colors": {
        "CITO NA RATUNEK": "FF6347",
        "CITO-UDAR": "FF4500",
        "Bardzo pilny": "FFA500",
        "CITO-CITO": "FFC7CE",
        "Pilny": "FFEB9C",
        "Planowy": "C6EFCE",
    },
    "procedure_type_colors": {
        "MR Onkologia": "E8D4F0",
        "TK Onkologia": "E8D4F0",
        "MR Angiografia": "D4E8F0",
        "TK Angiografia": "D4E8F0",
        "MR Neurologia": "FFE5CC",
        "MR Ortopedia": "D4F0E8",
        "MR Inne - wtym prostata, miednica, jama brzuszna tkanki miekkie": "F0E8D4",
        "TK Zwykłe": "E8E8E8",
    },

    # Wydajność — jedna liczba rdzeni dla całego procesu (weryfikacja + rozliczenia).
    # 0 = Auto (użyj wszystkich rdzeni dostępnych na serwerze).
    # Wartość jest zawsze ograniczana do liczby fizycznych rdzeni maszyny.
    "num_processes": 0,

    # (zachowane dla zgodności wstecznej — nieużywane w UI)
    "num_processes_verify": 4,
    "num_processes_billing": 5,

    # Moduł lekarzy: klucze lekarzy (doctor_key) wyłączonych z rozliczenia lekarzy.
    "doctors_excluded": [],

    # Współczynniki (adjustmenty) cen jednostek.
    # Niektóre jednostki nie mają w cenniku własnej stawki dla danego badania —
    # jest ona liczona jako stawka innego badania × współczynnik (np. wsswroclaw:
    # „TK CITO ONKO" = stawka „TK CITO" × 1,25). Stawki wyliczane współczynnikiem
    # mają pierwszeństwo przed heurystykami dziedziczenia ceny (ONKO/ANGIO→baza),
    # ale NIE nadpisują bezpośredniej stawki z cennika (jeśli istnieje i jest >0).
    # Struktura: { "jednostka": { "BADANIE": { "base": "BADANIE_BAZOWE", "factor": 1.25 } } }
    # Dane startowe wczytywane z seed_data/unit_adjustments.json przy pierwszym uruchomieniu.
    "unit_adjustments": {},

    # Grupy jednostek — łączą wybrane jednostki w jeden wiersz na PODGLĄDACH
    # (Pulpit, Porównanie). Czysto wizualne: nie wpływa na rozliczenia ani ceny.
    # Struktura: [{ "name": "Szpitale Wrocław", "units": ["wsswroclaw", "wss5wroclaw"] }]
    "unit_groups": [],

    # Moduł Windykacja: domyślny termin płatności (dni od wystawienia należności),
    # używany gdy jednostka nie ma własnego wpisu w payment_terms_by_unit.
    "default_payment_term_days": 14,

    # Moduł Windykacja: indywidualne terminy płatności per jednostka (dni), z pliku
    # "Słownik" (kolumna „TERMIN PŁATNOŚCI [DNI]", klucz „NAZWA SYSTEM" = jak „Klient").
    # Edytowalne z Ustawień; wartości spoza tej listy używają default_payment_term_days.
    "payment_terms_by_unit": {
        "alfasochaczew": 14, "almed": 14, "arterieart": 14, "bialogard": 14, "bimed": 14,
        "brodnica": 30, "brzesko": 30, "centermedpoznan": 14, "cobydgoszcz": 14,
        "dabrowatarnowska": 14, "dcmdolmed": 14, "diamed": 14, "domchojna": 14,
        "dzierzoniow": 30, "faceclinic": 14, "goleniow": 30, "gorlice": 30, "grajewo": 30,
        "grodzisk": 30, "grupazdrowie": 14, "gz": 14, "gzplonsk": 14, "kamienpomorski": 60,
        "kartuzy": 30, "klodzko": 14, "komed": 14, "kosmowroclaw": 14, "lubaczow": 14,
        "medflow": 14, "medinet": 14, "mswiapoznan": 60, "mswsiedlce": 14, "nml": 14,
        "nrkrakow": 14, "nzozevita": 14, "ostrow": 30, "poddebice": 25, "powiatsredzki": 14,
        "puszczykowo": 14, "radiomedica": 14, "rodamed": 30, "rybnik": 30, "scanmed": 14,
        "smtorun": 60, "sokolow": 60, "spzozgrodzisk": 14, "spzozlezajsk": 14, "spzozmc": 30,
        "spzozswidnica": 14, "spzzozsierpc": 14, "starachowice": 30, "swk": 30, "swp": 14,
        "szpitaldzieciecy": 14, "szpitaljaslo": 14, "szpitallubartow": 25, "szpitalmikolow": 60,
        "szpitalopole": 21, "szpitalrydygier": 21, "szpitalsiemiatycze": 45,
        "szpitalzakopane": 21, "szpitalzawiercie": 30, "td7szmw": 60, "tdblachownia": 14,
        "tdbonifratrzy": 14, "tdemcpiaseczno": 14, "tdgammaknife": 14, "tdgniezno": 30,
        "tdgvmcarint": 14, "tdipin": 30, "tdkolbuszowa": 14, "tdksskrakow": 30, "tdmilicz": 14,
        "tdneuromedyka": 14, "tdnowomedica": 14, "tdorzesze": 30, "tdparczew": 14,
        "tdprzemysl": 14, "tdscanmed2": 14, "tdscanmedak5": 14, "tdscanmedpila": 14,
        "tdsmswinoujscie": 28, "tdspzozkolo": 30, "tdspzozsiedlce": 30, "tdstalowawola": 14,
        "tdsuchab": 14, "tdsulechow": 30, "tdszpitalkolno": 30, "tdtargowek": 14,
        "tduskszczecin": 28, "tdwszplock": 30, "tomograf": 14, "tworki": 30,
        "uskbialystok": 14, "uskpoznan": 30, "wegorzewo": 30, "wimed": 14, "wizjamed": 14,
        "wlodawa": 30, "wsswroclaw": 30, "wysmaz": 14, "zambrow": 14,
        "zarywojskowy105": 30, "zgorzelec": 14, "zozbiala": 14, "zozbol": 14,
        "zozboleslawiec": 14, "zozolawa": 60, "zozswietochlowice": 30,
    },
}


def build_unit_group_map(groups) -> dict:
    """[{name, units:[...]}] → {jednostka_znormalizowana: nazwa_grupy}."""
    mapping = {}
    for g in (groups or []):
        if not isinstance(g, dict):
            continue
        name = str(g.get("name", "")).strip()
        if not name:
            continue
        for u in (g.get("units") or []):
            key = str(u).strip().lower()
            if key:
                mapping[key] = name
    return mapping


def group_label(klient, group_map) -> str:
    """Zwraca nazwę grupy dla jednostki (jeśli należy) albo samą jednostkę."""
    return group_map.get(str(klient).strip().lower(), str(klient)) if group_map else str(klient)


def deep_merge(base: dict, override: dict) -> dict:
    """Scala override na base (rekurencyjnie dla słowników)."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config() -> dict:
    """
    Zwraca pełną konfigurację: DEFAULT_CONFIG nadpisany przez JSON
    wskazany w zmiennej środowiskowej TELEDIAG_CONFIG (jeśli istnieje).
    """
    path = os.environ.get("TELEDIAG_CONFIG")
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            return deep_merge(DEFAULT_CONFIG, user_cfg)
        except Exception as e:  # noqa: BLE001
            print(f"! OSTRZEŻENIE: nie udało się wczytać konfiguracji ({e}). Używam domyślnej.", flush=True)
    return copy.deepcopy(DEFAULT_CONFIG)
