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

    # Wydajność — liczba rdzeni dla każdego etapu
    "num_processes_verify": 4,
    "num_processes_billing": 5,
}


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
