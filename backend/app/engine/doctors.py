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

from app.engine.cennik_lekarzy_convert import doctor_key, fix_category_typos

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
        kat = fix_category_typos(_norm(r["Kategoria"])).upper()  # łatka PLINE→PILNE
        prices[(doctor_key(r["Lekarz"]), kat)] = float(r["Cena"])
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
        kat = fix_category_typos(kat)  # łatka PLINE→PILNE również po stronie słownika
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


_PRIORITY_LADDER = ["CITO", "PILNE", "PLANOWE"]
_SIZE_LADDER = ["D", "C", "B", "A"]   # rozmiary od najwyższego do najniższego


def _prio_order(prio: str) -> list:
    """Kolejność prób priorytetów: bieżący → niższe → wyższe (najbliższy najpierw).
    PILNE → [PILNE, PLANOWE, CITO]; CITO → [CITO, PILNE, PLANOWE]."""
    i = _PRIORITY_LADDER.index(prio)
    return [prio] + _PRIORITY_LADDER[i + 1:] + list(reversed(_PRIORITY_LADDER[:i]))


def resolve_doctor_price(prices: dict, lek_key: str, category: str):
    """
    Stawka lekarza dla kategorii z dziedziczeniem, gdy stawka jest 0/pusta:
      1) ta sama literka (rozmiar), niższy priorytet: 'TK CITO A' → 'TK PILNE A'
         → 'TK PLANOWE A';
      2) gdy dla tej literki nie ma stawki na ŻADNYM priorytecie (także wyższym),
         schodzimy po literkach od najwyższej (D → C → B → A, z pominięciem
         własnej), a w obrębie każdej literki: bieżący priorytet → niższe → wyższe.
         Np. 'TK PILNE B' → (B: PLANOWE, CITO) → 'TK PILNE D' → 'TK PLANOWE D'
         → 'TK CITO D' → literka C → literka A.
    Kategorie bez literki (RTG/MMG): tylko krok 1 (priorytety w dół, jak dotąd).
    Zwraca pierwszą stawkę > 0, a gdy brak — oryginalny wynik lookupu (None/0/NaN),
    żeby diagnostyka braków działała jak dotąd.
    """
    cat = str(category or "").strip().upper()
    if not cat:
        return None
    c = prices.get((lek_key, cat))
    if c is not None and c == c and c > 0:   # c == c odrzuca NaN
        return c
    toks = cat.split(" ")
    prio = next((p for p in _PRIORITY_LADDER if p in toks), None)
    if prio is None:
        return c
    pidx = toks.index(prio)
    size = toks[-1] if toks[-1] in _SIZE_LADDER and len(toks) > pidx + 1 else None

    def _try(p, s):
        t = toks[:pidx] + [p] + toks[pidx + 1:]
        if s is not None:
            t = t[:-1] + [s]
        cc = prices.get((lek_key, " ".join(t)))
        return cc if (cc is not None and cc == cc and cc > 0) else None

    if size is None:
        # bez literki — jak dotąd: tylko priorytety W DÓŁ
        for lower in _PRIORITY_LADDER[_PRIORITY_LADDER.index(prio) + 1:]:
            cc = _try(lower, None)
            if cc is not None:
                return cc
        return c

    # 1) własna literka: wszystkie priorytety (bieżący pominięty — już sprawdzony)
    for p in _prio_order(prio)[1:]:
        cc = _try(p, size)
        if cc is not None:
            return cc
    # 2) pozostałe literki od najwyższej (D→A), każda po wszystkich priorytetach
    for s in _SIZE_LADDER:
        if s == size:
            continue
        for p in _prio_order(prio):
            cc = _try(p, s)
            if cc is not None:
                return cc
    return c


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


def build_doctor_billing(sprawdzone_dir: str, slownik_path: str, doctor_cennik_csv: str,
                         excluded_keys=None) -> dict:
    """
    Liczy rozliczenie lekarzy. Zwraca:
      rows: [{lekarz, kategoria, ilosc, stawka, wartosc}]
      by_doctor: [{lekarz, ilosc, wartosc}]
      validation: diagnostyka niedopasowań

    excluded_keys: zbiór kluczy lekarzy (doctor_key) do POMINIĘCIA w rozliczeniu —
    np. lekarze rozliczani osobno. Ich badania nie są wyceniane ani zgłaszane jako
    braki; pokazujemy tylko ile pominięto.
    """
    import pandas as pd
    excluded_keys = set(excluded_keys or [])

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
    # LEKARZE: brak jakiegokolwiek podciągania (w górę/dół). Używamy ORYGINALNego
    # rodzaju procedury i liczby okolic (kolumny zachowane w Etapie 1 PRZED korektami
    # jednostek), a kategorię dobieramy po PARZE (opis procedury, rodzaj procedury) —
    # ten sam opis przy różnych rodzajach bywa w innej kategorii cenowej lekarza.
    # Spójne z generate_doctor_billing_files (raporty per lekarz).
    if "Rodzaj procedury rozlicz. (oryg.)" in df.columns:
        df["Rodzaj procedury rozlicz."] = df["Rodzaj procedury rozlicz. (oryg.)"]
    if "Procedura rozlicz. (oryg.)" in df.columns:
        df["Procedura rozlicz."] = df["Procedura rozlicz. (oryg.)"]
    if "Priorytet opisu" in df.columns:
        df["Priorytet opisu"] = df["Priorytet opisu"].replace({"Bardzo pilny": "Pilny"})
    df["_proc_key"] = df["Procedura"].map(_key)
    df["_rodzaj_key"] = df["Rodzaj procedury rozlicz."].map(_key)
    df["_kategoria"] = [
        resolve_category(r, cat_map.get((r["_proc_key"], r["_rodzaj_key"]), ""))
        for _, r in df.iterrows()
    ]
    df["_lek_key"] = df[OPISUJACY_COL].map(doctor_key)
    df["_lek_disp"] = df[OPISUJACY_COL].map(_norm)

    # Wyłączeni lekarze (z ustawień) — pomijamy ich badania w rozliczeniu.
    excluded_studies = int(df["_lek_key"].isin(excluded_keys).sum()) if excluded_keys else 0
    if excluded_keys:
        df = df[~df["_lek_key"].isin(excluded_keys)].copy()

    # diagnostyka
    no_category = df[df["_kategoria"] == ""]
    studies_no_cat = int(len(no_category))

    priced = df[df["_kategoria"] != ""].copy()
    priced["_stawka"] = [
        resolve_doctor_price(prices, lk, kat)
        for lk, kat in zip(priced["_lek_key"], priced["_kategoria"])
    ]

    missing_price = priced[priced["_stawka"].isna()]
    pairs_no_price = (
        missing_price.groupby(["_lek_disp", "_kategoria"]).size().reset_index(name="n")
        .sort_values("n", ascending=False)
    )

    # Badania rozliczone po stawce 0 zł — pozycja W CENNIKU istnieje, ale stawka = 0
    # (lekarz nieopłacany za tę kategorię). Osobna lista od „braku stawki" (NaN wyżej).
    zero_rate = priced[pd.to_numeric(priced["_stawka"], errors="coerce") == 0]
    zero_rate_pairs = (
        zero_rate.groupby(["_lek_disp", "_kategoria"]).size().reset_index(name="n")
        .rename(columns={"_lek_disp": "lekarz", "_kategoria": "kategoria"})
        .sort_values("n", ascending=False)
    )

    doctors_in_data = set(df["_lek_key"]) - {""}
    doctors_in_cennik = {k for (k, _) in prices.keys()}
    doctors_unmatched = sorted(
        df[df["_lek_key"].isin(doctors_in_data - doctors_in_cennik)]["_lek_disp"].unique().tolist()
    )

    from app.engine.billing import bill_extract_multiplier
    ok = priced[priced["_stawka"].notna()].copy()
    ok["ilosc"] = 1  # licznik badań (do kolumny „Badania")
    # Wartość = stawka × liczba okolic (jak u jednostek) — okolice z „Procedura rozlicz.".
    ok["_okolice"] = ok["Procedura rozlicz."].map(bill_extract_multiplier)
    ok["wartosc"] = ok["_okolice"] * ok["_stawka"]

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

    # Podsumowanie ilościowe: liczba WYKONANYCH badań per lekarz i kategoria
    # (kategoria w formacie cennika lekarzy). Liczymy ze WSZYSTKICH badań mających
    # kategorię — niezależnie od tego, czy cennik ma dla niej stawkę (to licznik
    # badań, nie wartość). Badania bez kategorii są raportowane osobno
    # (studies_without_category) i tu się nie pojawiają.
    cat_counts = (
        priced.groupby(["_lek_disp", "_kategoria"]).size()
        .reset_index(name="ilosc")
        .rename(columns={"_lek_disp": "lekarz", "_kategoria": "kategoria"})
        .sort_values(["lekarz", "kategoria"])
    )

    # Liczba OKOLIC per lekarz i kategoria (count × mnożnik z „Procedura rozlicz.") —
    # do uzupełniania pliku zobowiązań lekarzy (tam wpisuje się okolice, nie sztuki).
    priced["_okolice"] = priced["Procedura rozlicz."].map(bill_extract_multiplier)
    cat_okolice = (
        priced.groupby(["_lek_disp", "_kategoria"])["_okolice"].sum()
        .reset_index()
        .rename(columns={"_lek_disp": "lekarz", "_kategoria": "kategoria", "_okolice": "okolice"})
        .sort_values(["lekarz", "kategoria"])
    )

    # Rozbicie okolic po DACIE BADANIA (dzień) — potrzebne tylko dla miesięcy
    # rozbitych aneksem w połowie (w pliku zobowiązań są wtedy dwie kolumny:
    # np. „01-17.05" i „18-31.05" z różnymi stawkami). Lekka agregacja
    # lekarz × kategoria × data → suma okolic; dla zwykłych miesięcy nieużywana
    # (wpisujemy sumę z category_okolice). Data: data badania (zapas: zatwierdzenia).
    cat_okolice_daily = []
    _date_col = next((c for c in ("Data badania (UTC)", "Data 1. zatwierdzenia")
                      if c in priced.columns), None)
    if _date_col is not None and not priced.empty:
        _pr = priced[["_lek_disp", "_kategoria", "_okolice", _date_col]].copy()
        _pr["_data"] = pd.to_datetime(_pr[_date_col], errors="coerce")
        _pr = _pr[_pr["_data"].notna()]
        if not _pr.empty:
            _pr["_data"] = _pr["_data"].dt.strftime("%Y-%m-%d")
            cat_okolice_daily = (
                _pr.groupby(["_lek_disp", "_kategoria", "_data"])["_okolice"].sum()
                .reset_index()
                .rename(columns={"_lek_disp": "lekarz", "_kategoria": "kategoria",
                                 "_data": "data", "_okolice": "okolice"})
                .to_dict("records")
            )

    return {
        "empty": False,
        "rows": by_cat.to_dict("records"),
        "by_doctor": by_doctor.to_dict("records"),
        "category_counts": cat_counts.to_dict("records"),
        "category_okolice": cat_okolice.to_dict("records"),
        "category_okolice_daily": cat_okolice_daily,
        "validation": {
            "total_studies": int(len(df)),
            "priced_studies": int(len(ok)),
            "studies_without_category": studies_no_cat,
            "slownik_categories": len(cat_map),
            "n_doctors": int(by_doctor.shape[0]),
            "total_value": round(float(ok["wartosc"].sum()), 2),
            "excluded_studies": excluded_studies,
            "doctors_unmatched": doctors_unmatched[:100],
            "pairs_without_price": pairs_no_price.head(100).to_dict("records"),
            "zero_rate_studies": int(len(zero_rate)),
            "zero_rate_pairs": zero_rate_pairs.head(200).to_dict("records"),
        },
    }


def _surname_first(name: str) -> str:
    """„Imię Nazwisko" → „Nazwisko Imię" (np. 'Tomasz Bujalski' → 'Bujalski Tomasz')."""
    toks = _norm(name).split()
    return " ".join(toks[1:] + toks[:1]) if len(toks) >= 2 else _norm(name)


def _safe_filename(s: str) -> str:
    """Usuwa znaki niedozwolone w nazwach plików; zachowuje spacje i myślniki."""
    return re.sub(r'[\\/:*?"<>|]+', "", s).strip()


def _period_mmyyyy(frame) -> str:
    """Okres rozliczenia jako MMRRRR — z daty zatwierdzenia opisu (fallback: data badania)."""
    import pandas as pd
    for col in ("Data 1. zatwierdzenia", "Data badania (UTC)"):
        if col in frame.columns:
            dt = pd.to_datetime(frame[col], errors="coerce").dropna()
            if not dt.empty:
                return dt.dt.strftime("%m%Y").mode().iloc[0]
    return ""


def _append_availability_sheet(path: str, av_doc: dict):
    """Dokłada do pliku lekarza arkusz „Gotowość" (godziny × stawki z TeamUp)."""
    from openpyxl import load_workbook
    wb = load_workbook(path)
    ws = wb.create_sheet("Gotowość")
    ws.append(["Pozycja", "Godziny", "Stawka", "Wartość"])
    for it in av_doc.get("items", []):
        ws.append([it["label"], it["hours"], it["rate"], it["amount"]])
    ws.append([])
    ws.append(["RAZEM gotowość + triaż", None, None, av_doc.get("total", 0)])
    for col, w in (("A", 34), ("B", 10), ("C", 10), ("D", 12)):
        ws.column_dimensions[col].width = w
    wb.save(path)


def generate_doctor_billing_files(sprawdzone_dir: str, slownik_path: str, doctor_cennik_csv: str,
                                  out_dir: str, excluded_keys=None, period_mmyyyy=None,
                                  availability=None) -> dict:
    """
    Tworzy OSOBNY plik Excel dla KAŻDEGO lekarza — w układzie identycznym jak
    rozliczenia jednostek (arkusz „Szczegółowe" z jego badaniami + „Rozliczenie"
    z podziałem na priorytety, liczbą okolic i sumami), ale wyceniony cennikiem
    lekarzy (stawka per Lekarz+Kategoria; Wartość = stawka × ilość_okolic).

    Braki kategorii/stawki → stawka 0 (jak braki cen u jednostek). Wyłączeni
    lekarze pomijani. Zwraca listę utworzonych plików.
    """
    import os as _os
    import shutil
    import numpy as np
    from app.engine.billing import bill_make_grouped, bill_finalize_to_excel

    excluded = set(excluded_keys or [])
    df = read_verified_studies(sprawdzone_dir)
    if df is None or df.empty or OPISUJACY_COL not in df.columns:
        return {"files": [], "count": 0}

    cat_map = load_lekarz_categories(slownik_path)
    prices = load_doctor_prices(doctor_cennik_csv)

    df = df.copy()
    df["_lek_key"] = df[OPISUJACY_COL].map(doctor_key)
    if excluded:
        df = df[~df["_lek_key"].isin(excluded)]

    # świeży katalog wyjściowy
    shutil.rmtree(out_dir, ignore_errors=True)
    _os.makedirs(out_dir, exist_ok=True)

    files = []
    for lek_key, sub in df.groupby("_lek_key"):
        if not lek_key:
            continue
        disp = _norm(sub[OPISUJACY_COL].iloc[0])
        if not disp or disp.lower() in ("nan", "none"):
            continue  # puste/nieznane nazwisko — nie twórz pliku „nan"
        sub = sub.copy()
        # LEKARZE: brak jakiegokolwiek podciągania — przywróć ORYGINALNY rodzaj
        # procedury i liczbę okolic (kolumny zachowane w Etapie 1 w
        # billing.process_client_data, przed korektami priorytetów/okolic).
        if "Rodzaj procedury rozlicz. (oryg.)" in sub.columns:
            sub["Rodzaj procedury rozlicz."] = sub["Rodzaj procedury rozlicz. (oryg.)"]
        if "Procedura rozlicz. (oryg.)" in sub.columns:
            sub["Procedura rozlicz."] = sub["Procedura rozlicz. (oryg.)"]
        # „Bardzo pilny" rozliczamy razem z „Pilny" (ta sama stawka, jeden blok).
        if "Priorytet opisu" in sub.columns:
            sub["Priorytet opisu"] = sub["Priorytet opisu"].replace({"Bardzo pilny": "Pilny"})
        grouped, det = bill_make_grouped(sub, OPISUJACY_COL)

        def _cena(r):
            base = cat_map.get((_key(r["Procedura"]), _key(r["Rodzaj procedury rozlicz."])), "")
            category = resolve_category(r, base)
            if not category:
                return np.nan
            c = resolve_doctor_price(prices, lek_key, category)   # 0/brak → niższy priorytet
            return np.nan if c is None else c

        grouped["Cena"] = grouped.apply(_cena, axis=1)

        # Stawka dla DOWOLNEGO priorytetu danej procedury (także bez badań w tym
        # priorytecie) — żeby w raporcie stawka była wszędzie, nawet gdy ilość=0.
        def _rate(procedura, rodzaj, priorytet, _lk=lek_key):
            base = cat_map.get((_key(procedura), _key(rodzaj)), "")
            category = resolve_category({"Priorytet opisu": priorytet}, base)
            if not category:
                return np.nan
            c = resolve_doctor_price(prices, _lk, category)       # 0/brak → niższy priorytet
            return np.nan if c is None else c

        # Nazwa pliku wg szablonu: „MMRRRR dr Nazwisko Imię" (np. „052026 dr Bujalski Tomasz").
        # Miesiąc w nazwie pliku: z nazwy pliku wejściowego (period_mmyyyy),
        # a w razie braku — z dat w danych (zapas).
        period = period_mmyyyy or _period_mmyyyy(sub)
        fname = (_safe_filename(f"{period} dr {_surname_first(disp)}") or "dr lekarz") + ".xlsx"
        try:
            fpath = _os.path.join(out_dir, fname)
            bill_finalize_to_excel(grouped, det, fpath, for_doctor=True, rate_resolver=_rate)
            # Gotowość + triaż (TeamUp) — osobny arkusz w pliku lekarza.
            if availability and lek_key in availability:
                try:
                    _append_availability_sheet(fpath, availability[lek_key])
                except Exception as e:  # noqa: BLE001
                    print(f"! Arkusz Gotowość ({disp}): {e}", flush=True)
            files.append(fname)
        except Exception as e:  # noqa: BLE001
            print(f"BŁĄD tworzenia pliku lekarza {disp}: {e}", flush=True)

    return {"files": sorted(files), "count": len(files)}
