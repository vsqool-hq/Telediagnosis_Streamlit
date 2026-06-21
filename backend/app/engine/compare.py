"""
Porównanie LEKARZE ↔ JEDNOSTKI — marża per kategoria badań.

Dla tych samych (zweryfikowanych) badań wyceniamy każde badanie z DWÓCH stron:
  * przychód z cennika jednostek  — klucz (Klient, build_price_key(badanie)),
  * koszt z cennika lekarzy        — klucz (Opisujący→klucz, kategoria ze słownika).

Ilość liczona spójnie po obu stronach (mnożnik z „Procedura rozlicz." jak w
rozliczeniu jednostek), więc marża = przychód_jednostki − koszt_lekarza jest
porównywalna 1:1. Agregacja per kategoria lekarska (i modalność).

Moduł NIE modyfikuje rozliczenia jednostek — korzysta tylko z jego funkcji
wyceny (build_price_key, bill_extract_multiplier) w trybie tylko-do-odczytu.
"""

import os
import glob


def _load_units_prices(units_cennik_dir: str):
    import pandas as pd
    csvs = glob.glob(os.path.join(units_cennik_dir, "*.csv"))
    if not csvs:
        return {}
    df = pd.read_csv(csvs[0], sep=";", encoding="utf-8-sig", decimal=",")
    df["BADANIE"] = df["BADANIE"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    out = {}
    for _, r in df.iterrows():
        out[(str(r["Jednostka"]).strip(), r["BADANIE"])] = float(r["Cena"])
    return out


def build_comparison(sprawdzone_dir: str, slownik_path: str,
                     units_cennik_dir: str, doctor_cennik_csv: str) -> dict:
    import pandas as pd
    from app.engine.billing import build_price_key, bill_extract_multiplier, resolve_unit_price
    from app.engine.cennik_lekarzy_convert import doctor_key
    from app.engine.doctors import (
        read_verified_studies, load_lekarz_categories, load_doctor_prices,
        resolve_category, _key,
    )

    df = read_verified_studies(sprawdzone_dir)
    if df is None or df.empty:
        return {"empty": True, "reason": "Brak zweryfikowanych danych."}

    # Częściowo/niewypełniona kolumna „Rodzaj procedury lekarz" nie blokuje porównania —
    # badania bez kategorii są pomijane w marży i raportowane (studies_without_category).
    cat_map = load_lekarz_categories(slownik_path)

    unit_prices = _load_units_prices(units_cennik_dir)
    doc_prices = load_doctor_prices(doctor_cennik_csv)

    df = df.copy()
    df["_mult"] = df["Procedura rozlicz."].map(bill_extract_multiplier)
    # Klucz cenowy jednostki budujemy IDENTYCZNIE jak rozliczenie jednostek/Pulpit:
    # bez flagi „Badania do porównania" (silnik przy grupowaniu zmienia nazwę tej
    # kolumny, więc build_price_key jej nie widzi). Inaczej przychód jednostek w
    # porównaniu byłby zaniżony (klucze „… PORÓWNAWCZE …").
    _dk = df.copy()
    if "Badania do porównania" in _dk.columns:
        _dk["Badania do porównania"] = 0
    df["_badanie"] = _dk.apply(build_price_key, axis=1)
    df["_kategoria"] = [
        resolve_category(r, cat_map.get((_key(r.get("Procedura")), _key(r.get("Rodzaj procedury rozlicz."))), ""))
        for _, r in df.iterrows()
    ]
    df["_lek_key"] = df["Opisujący"].map(doctor_key) if "Opisujący" in df.columns else ""

    def _unit_price(row):
        # Wspólna logika z rozliczeniem jednostek: dziedziczenie ONKO/ANGIO→baza
        # oraz MR CITO→MR PILNE.
        return resolve_unit_price(unit_prices, row.get("Klient", ""), row["_badanie"])

    def _doc_price(row):
        if not row["_kategoria"]:
            return None
        return doc_prices.get((row["_lek_key"], row["_kategoria"].upper()))

    df["_unit_price"] = df.apply(_unit_price, axis=1)
    df["_doc_price"] = df.apply(_doc_price, axis=1)
    df["_units_rev"] = df["_mult"] * df["_unit_price"].fillna(0)
    df["_doc_cost"] = df["_mult"] * df["_doc_price"].fillna(0)

    grp = df[df["_kategoria"] != ""].groupby(["Modalność", "_kategoria"]).agg(
        ilosc=("_mult", "sum"),
        przychod_jednostki=("_units_rev", "sum"),
        koszt_lekarzy=("_doc_cost", "sum"),
    ).reset_index().rename(columns={"_kategoria": "kategoria"})
    grp["marza"] = grp["przychod_jednostki"] - grp["koszt_lekarzy"]
    grp = grp.sort_values("marza", ascending=False)

    for c in ("ilosc", "przychod_jednostki", "koszt_lekarzy", "marza"):
        grp[c] = grp[c].round(2)

    # Marżę liczymy na TYM SAMYM zbiorze po obu stronach — tylko badania z
    # przypisaną kategorią lekarską (inaczej przychód jednostek obejmowałby badania
    # bez policzonego kosztu lekarza i marża byłaby zawyżona). Badania bez kategorii
    # raportujemy osobno (studies_without_category) wraz z ich przychodem jednostek.
    cat = df[df["_kategoria"] != ""]
    nocat = df[df["_kategoria"] == ""]
    return {
        "empty": False,
        "rows": grp.to_dict("records"),
        "totals": {
            "przychod_jednostki": round(float(cat["_units_rev"].sum()), 2),
            "koszt_lekarzy": round(float(cat["_doc_cost"].sum()), 2),
            "marza": round(float(cat["_units_rev"].sum() - cat["_doc_cost"].sum()), 2),
            "studies": int(len(df)),
            "studies_with_category": int(len(cat)),
            "studies_without_category": int(len(nocat)),
            "przychod_jednostki_bez_kategorii": round(float(nocat["_units_rev"].sum()), 2),
        },
    }
