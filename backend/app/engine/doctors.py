"""
Silnik rozliczenia LEKARZY (moduł niezależny od rozliczenia jednostek).

Wejście:
  * zweryfikowane dane badań (pliki „sprawdzone", arkusz „Szczegółowe") — te same,
    które powstają w Etapie 1 rozliczenia jednostek; nie uruchamiamy nic ponownie,
  * słownik (plik wzorcowy) z wypełnioną kolumną „Rodzaj procedury lekarz",
    która mapuje (Procedura, Rodzaj procedury rozlicz.) → kategoria lekarska,
  * cennik lekarzy w formacie Lekarz;Kategoria;Cena (po konwersji skoroszytu).

Wynik: rozliczenie per lekarz i kategoria (ilość, stawka, wartość) + diagnostyka
(niedopasowani lekarze, procedury bez kategorii, kategorie bez stawki).

Składanie kategorii:
  Kolumna „Rodzaj procedury lekarz" zawiera BAZĘ bez priorytetu („RTG", „TK A",
  „MR C"…), a cennik lekarzy ma priorytet w środku („RTG CITO", „TK CITO A").
  Priorytet bierzemy z kolumny „Priorytet opisu" badania i wstawiamy między
  modalność a rozmiar — patrz resolve_category().
"""

import os
import re
import glob

from app.engine.cennik_lekarzy_convert import doctor_key

LEKARZ_COL_SLOWNIK = "Rodzaj procedury lekarz"
OPISUJACY_COL = "Opisujący"

_PRIORITIES = {"CITO", "PILNE", "PLANOWE"}


def _priority_from_study(value) -> str:
    """Mapuje 'Priorytet opisu' badania na priorytet cennika lekarzy (CITO/PILNE/PLANOWE)."""
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    if "CITO" in raw or "RATUN" in raw or "UDAR" in raw:
        return "CITO"
    if "PIL" in raw:               # Pilny, Bardzo pilny
        return "PILNE"
    if "PLAN" in raw:              # Planowy
        return "PLANOWE"
    return ""


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip()


def _key(s) -> str:
    return _norm(s).lower()


def load_doctor_prices(csv_path: str) -> dict:
    """Czyta Lekarz;Kategoria;Cena → {(klucz_lekarza, kategoria_norm): cena}."""
    import pandas as pd
    df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", decimal=",")
    prices = {}
    for _, r in df.iterrows():
        prices[(doctor_key(r["Lekarz"]), _norm(r["Kategoria"]).upper())] = float(r["Cena"])
    return prices


def load_lekarz_categories(slownik_path: str) -> dict:
    """
    Czyta słownik → {(procedura_klucz, rodzaj_klucz): kategoria_lekarska}.
    Klucze jak w weryfikacji jednostek: Procedura i Rodzaj procedury rozlicz. (lower+strip).
    Zwraca tylko wiersze z niepustą kolumną „Rodzaj procedury lekarz".
    """
    import pandas as pd
    df = pd.read_excel(slownik_path, sheet_name="Szczegółowe")
    if LEKARZ_COL_SLOWNIK not in df.columns:
        return {}
    mapping = {}
    for _, r in df.iterrows():
        kat = _norm(r.get(LEKARZ_COL_SLOWNIK))
        if not kat or kat.lower() in ("none", "nan"):
            continue
        mapping[(_key(r.get("Procedura")), _key(r.get("Rodzaj procedury rozlicz.")))] = kat
    return mapping


def resolve_category(study_row, slownik_category: str) -> str:
    """
    Składa finalną kategorię cennika lekarzy z bazy ze słownika + priorytetu badania.

    Słownik podaje bazę BEZ priorytetu: "RTG", "TK A", "MR C"…
    Cennik lekarzy ma priorytet w środku: "RTG CITO", "TK CITO A", "MR PLANOWE C".
    Wstawiamy więc priorytet (z 'Priorytet opisu') między modalność a rozmiar:
      "RTG" + CITO        -> "RTG CITO"
      "TK A" + PLANOWE     -> "TK PLANOWE A"

    Jeśli baza nie jest modalnością RTG/TK/MR albo już zawiera priorytet
    (np. gotowe "MMG SKRINING"), zwracamy ją bez zmian.
    """
    base = _norm(slownik_category)
    if not base:
        return ""
    toks = base.upper().split(" ")
    modality = toks[0]
    if modality not in ("RTG", "TK", "MR") or any(t in _PRIORITIES for t in toks):
        return base  # gotowa kategoria / inna modalność — bez składania
    priority = _priority_from_study(study_row.get("Priorytet opisu"))
    if not priority:
        return base  # brak priorytetu → zostaw bazę (trafi do „bez stawki")
    rest = " ".join(toks[1:])  # rozmiar: A/B/C/D (lub puste dla RTG)
    return f"{modality} {priority} {rest}".strip()


def read_verified_studies(sprawdzone_dir: str):
    """Wczytuje i łączy arkusze „Szczegółowe" ze wszystkich plików sprawdzonych."""
    import pandas as pd
    frames = []
    for path in sorted(glob.glob(os.path.join(sprawdzone_dir, "*.xlsx"))):
        if os.path.basename(path).startswith("~$"):
            continue
        try:
            frames.append(pd.read_excel(path, sheet_name="Szczegółowe"))
        except Exception:  # noqa: BLE001
            continue
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def build_doctor_billing(sprawdzone_dir: str, slownik_path: str, doctor_cennik_csv: str) -> dict:
    """
    Liczy rozliczenie lekarzy. Zwraca:
      rows: [{lekarz, kategoria, ilosc, stawka, wartosc}]
      by_doctor: [{lekarz, ilosc, wartosc}]
      validation: diagnostyka niedopasowań
    """
    import pandas as pd

    df = read_verified_studies(sprawdzone_dir)
    if df is None or df.empty:
        return {"empty": True, "reason": "Brak zweryfikowanych danych (plików sprawdzonych)."}
    if OPISUJACY_COL not in df.columns:
        return {"empty": True, "reason": f"Brak kolumny '{OPISUJACY_COL}' w danych."}

    # Częściowo (a nawet w ogóle nie) wypełniona kolumna „Rodzaj procedury lekarz"
    # NIE blokuje liczenia — badania bez przypisanej kategorii są pomijane i
    # raportowane (studies_without_category). Pełna pustka = po prostu 0 wycenionych.
    cat_map = load_lekarz_categories(slownik_path)

    prices = load_doctor_prices(doctor_cennik_csv)

    # mapowanie badanie → kategoria lekarska
    df = df.copy()
    df["_proc_key"] = df["Procedura"].map(_key)
    df["_rodzaj_key"] = df["Rodzaj procedury rozlicz."].map(_key)
    df["_kategoria"] = [
        resolve_category(r, cat_map.get((r["_proc_key"], r["_rodzaj_key"]), ""))
        for _, r in df.iterrows()
    ]
    df["_lek_key"] = df[OPISUJACY_COL].map(doctor_key)
    df["_lek_disp"] = df[OPISUJACY_COL].map(_norm)

    # diagnostyka
    no_category = df[df["_kategoria"] == ""]
    studies_no_cat = int(len(no_category))

    priced = df[df["_kategoria"] != ""].copy()
    priced["_stawka"] = [
        prices.get((lk, kat.upper())) for lk, kat in zip(priced["_lek_key"], priced["_kategoria"])
    ]

    missing_price = priced[priced["_stawka"].isna()]
    pairs_no_price = (
        missing_price.groupby(["_lek_disp", "_kategoria"]).size().reset_index(name="n")
        .sort_values("n", ascending=False)
    )

    doctors_in_data = set(df["_lek_key"]) - {""}
    doctors_in_cennik = {k for (k, _) in prices.keys()}
    doctors_unmatched = sorted(
        df[df["_lek_key"].isin(doctors_in_data - doctors_in_cennik)]["_lek_disp"].unique().tolist()
    )

    ok = priced[priced["_stawka"].notna()].copy()
    ok["ilosc"] = 1  # TODO: mnożnik/ilość okolic do potwierdzenia po wypełnieniu słownika
    ok["wartosc"] = ok["ilosc"] * ok["_stawka"]

    by_cat = (
        ok.groupby(["_lek_disp", "_kategoria"])
        .agg(ilosc=("ilosc", "sum"), stawka=("_stawka", "first"), wartosc=("wartosc", "sum"))
        .reset_index().rename(columns={"_lek_disp": "lekarz", "_kategoria": "kategoria"})
        .sort_values(["lekarz", "kategoria"])
    )
    by_doctor = (
        ok.groupby("_lek_disp").agg(ilosc=("ilosc", "sum"), wartosc=("wartosc", "sum"))
        .reset_index().rename(columns={"_lek_disp": "lekarz"})
        .sort_values("wartosc", ascending=False)
    )

    return {
        "empty": False,
        "rows": by_cat.to_dict("records"),
        "by_doctor": by_doctor.to_dict("records"),
        "validation": {
            "total_studies": int(len(df)),
            "priced_studies": int(len(ok)),
            "studies_without_category": studies_no_cat,
            "slownik_categories": len(cat_map),
            "n_doctors": int(by_doctor.shape[0]),
            "total_value": round(float(ok["wartosc"].sum()), 2),
            "doctors_unmatched": doctors_unmatched[:100],
            "pairs_without_price": pairs_no_price.head(100).to_dict("records"),
        },
    }
