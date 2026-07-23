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


def regroup_by_unit(rows, group_map):
    """Łączy jednostki w `by_unit` wg mapy grup (sumuje ilość/przychód/koszt/marżę).
    Czysto wizualne — wołane przy odczycie, nie modyfikuje zapisanego porównania."""
    if not group_map or not rows:
        return rows
    agg = {}
    for r in rows:
        label = group_map.get(str(r.get("jednostka", "")).strip().lower(), r.get("jednostka"))
        a = agg.setdefault(label, {
            "jednostka": label, "ilosc": 0,
            "przychod_jednostki": 0.0, "koszt_lekarzy": 0.0, "marza": 0.0,
        })
        a["ilosc"] += r.get("ilosc", 0) or 0
        a["przychod_jednostki"] += r.get("przychod_jednostki", 0.0) or 0.0
        a["koszt_lekarzy"] += r.get("koszt_lekarzy", 0.0) or 0.0
        a["marza"] += r.get("marza", 0.0) or 0.0
    out = list(agg.values())
    for a in out:
        for k in ("przychod_jednostki", "koszt_lekarzy", "marza"):
            a[k] = round(a[k], 2)
    out.sort(key=lambda x: x["marza"], reverse=True)
    return out


def build_comparison(sprawdzone_dir: str, slownik_path: str,
                     units_cennik_dir: str, doctor_cennik_csv: str,
                     availability_by_doctor: dict | None = None,
                     excluded_doctor_keys=None) -> dict:
    """availability_by_doctor: {klucz_lekarza: kwota gotowość+triaż za miesiąc} —
    rozbijana PROPORCJONALNIE na badania lekarza (z kategorią) i doliczana do
    kosztu każdego badania, więc wchodzi do marży per kategoria/lekarz/jednostkę."""
    import pandas as pd
    from app.engine.billing import (
        build_price_key, bill_extract_multiplier, resolve_unit_price,
        prepare_adjustments, get_unit_adjustments,
    )
    from app.engine.cennik_lekarzy_convert import doctor_key
    from app.engine.doctors import (
        read_verified_studies, load_lekarz_categories, load_doctor_prices,
        resolve_category, resolve_doctor_price, _key,
        load_consult_config, per_study_consultations,
    )

    df = read_verified_studies(sprawdzone_dir)
    if df is None or df.empty:
        return {"empty": True, "reason": "Brak zweryfikowanych danych."}

    # Jednostki wyłączone w ustawieniach — pomijamy ich badania PO OBU stronach
    # (przychód i koszt), żeby marża liczyła się na tym samym zbiorze.
    from app.engine.billing import get_excluded_units, _norm_unit
    _excl_units = get_excluded_units()
    if _excl_units and "Klient" in df.columns:
        df = df[~df["Klient"].map(_norm_unit).isin(_excl_units)]
        if df.empty:
            return {"empty": True, "reason": "Wszystkie jednostki wyłączone w ustawieniach."}

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

    # Strona LEKARZA: bez podciągania (w górę/dół) — kategorię i okolice liczymy na
    # ORYGINALNym rodzaju procedury i „Procedura rozlicz." (kolumny „(oryg.)" z Etapu 1),
    # a kategorię dobieramy po PARZE (opis procedury, rodzaj procedury). Tak samo jak
    # build_doctor_billing i raporty per lekarz — by koszt lekarzy w marży się zgadzał.
    _rodzaj_doc = (df["Rodzaj procedury rozlicz. (oryg.)"]
                   if "Rodzaj procedury rozlicz. (oryg.)" in df.columns
                   else df["Rodzaj procedury rozlicz."])
    _proc_doc = (df["Procedura rozlicz. (oryg.)"]
                 if "Procedura rozlicz. (oryg.)" in df.columns
                 else df["Procedura rozlicz."])
    df["_rodzaj_doc_key"] = _rodzaj_doc.map(_key)
    df["_mult_doc"] = _proc_doc.map(bill_extract_multiplier)   # okolice lekarza (oryg.)
    df["_kategoria"] = [
        resolve_category(r, cat_map.get((_key(r.get("Procedura")), rk), ""))
        for (_, r), rk in zip(df.iterrows(), df["_rodzaj_doc_key"])
    ]
    df["_lek_key"] = df["Opisujący"].map(doctor_key) if "Opisujący" in df.columns else ""

    # Lekarze wyłączeni w ustawieniach — pomijamy ich badania po OBU stronach marży
    # (rozliczani osobno), spójnie z zakładką „Rozliczenie lekarzy".
    _excl_docs = set(excluded_doctor_keys or [])
    if _excl_docs and "_lek_key" in df.columns:
        df = df[~df["_lek_key"].isin(_excl_docs)]
        if df.empty:
            return {"empty": True, "reason": "Wszystkie badania wyłączone (lekarze/jednostki)."}

    adj_by_unit = prepare_adjustments(get_unit_adjustments())

    def _unit_price(row):
        # Wspólna logika z rozliczeniem jednostek: współczynniki (adjustmenty),
        # dziedziczenie ONKO/ANGIO→baza oraz MR CITO→MR PILNE.
        return resolve_unit_price(unit_prices, row.get("Klient", ""), row["_badanie"], adj_by_unit)

    def _doc_price(row):
        if not row["_kategoria"]:
            return None
        # 0/brak stawki → niższy priorytet tej samej kategorii (jak raporty lekarzy).
        return resolve_doctor_price(doc_prices, row["_lek_key"], row["_kategoria"])

    # Dopłata za badania porównawcze (osobna linia po stawce porównawczej) — tak jak
    # w rozliczeniu jednostek/Pulpicie. Klucz porównawczy budujemy z flagą = 1; dopłatę
    # naliczamy tylko gdy różni się od klucza pełnego (TK/MR; RTG/MMG nie mają wariantu).
    _pk = df.copy()
    _pk["Badania do porównania"] = 1
    df["_porown_badanie"] = _pk.apply(build_price_key, axis=1)
    df["_porown_flag"] = pd.to_numeric(df.get("Badania do porównania", 0), errors="coerce").fillna(0)

    def _porown_rev(row):
        if row["_porown_flag"] <= 0 or row["_porown_badanie"] == row["_badanie"]:
            return 0.0
        p = resolve_unit_price(unit_prices, row.get("Klient", ""), row["_porown_badanie"], adj_by_unit)
        # Dopłata od LICZBY badań porównawczych × OKOLICE (jak faktura i tabela
        # jednostek/Pulpit): flaga (0/1) × mnożnik okolic (_mult) × stawka_porówn.
        return float(row["_porown_flag"]) * float(row["_mult"]) * float(p) if (p and p > 0) else 0.0

    df["_unit_price"] = df.apply(_unit_price, axis=1)
    df["_doc_price"] = df.apply(_doc_price, axis=1)
    df["_units_rev"] = df["_mult"] * df["_unit_price"].fillna(0) + df.apply(_porown_rev, axis=1)
    df["_doc_cost"] = df["_mult_doc"] * df["_doc_price"].fillna(0)   # okolice lekarza (oryg.)

    # KONSULTACJE: dopłatę dla konsultującego doliczamy do KOSZTU lekarzy tego badania,
    # żeby całość (opisy + konsultacje + gotowość) zgadzała się z „Rozliczeniem lekarzy".
    # Liczymy TAK SAMO jak rozliczenie: na ORYGINALNYM rodzaju/okolicach i z
    # „Bardzo pilny"→„Pilny". Wynik mapujemy po indeksie wiersza (_src_idx) na to badanie.
    df["_cons_cost"] = 0.0
    _df_doc = df.copy()
    if "Rodzaj procedury rozlicz. (oryg.)" in _df_doc.columns:
        _df_doc["Rodzaj procedury rozlicz."] = _df_doc["Rodzaj procedury rozlicz. (oryg.)"]
    if "Procedura rozlicz. (oryg.)" in _df_doc.columns:
        _df_doc["Procedura rozlicz."] = _df_doc["Procedura rozlicz. (oryg.)"]
    if "Priorytet opisu" in _df_doc.columns:
        _df_doc["Priorytet opisu"] = _df_doc["Priorytet opisu"].replace({"Bardzo pilny": "Pilny"})
    _cons = per_study_consultations(_df_doc, cat_map, doc_prices, load_consult_config(), _excl_docs)
    if not _cons.empty:
        _cons_by_idx = _cons.groupby("_src_idx")["_wartosc"].sum()
        df["_cons_cost"] = df.index.to_series().map(_cons_by_idx).fillna(0.0)
        df["_doc_cost"] = df["_doc_cost"] + df["_cons_cost"]

    # Gotowość + triaż (TeamUp): kwotę miesięczną lekarza rozbijamy RÓWNO na jego
    # badania z kategorią i doliczamy do kosztu każdego badania — dzięki temu
    # wchodzi w marżę per kategoria, per lekarz, per jednostkę i per priorytet.
    avail_total = avail_alloc = 0.0
    if availability_by_doctor:
        avail_total = round(sum(float(v or 0) for v in availability_by_doctor.values()), 2)
        cat_mask = df["_kategoria"] != ""
        counts = df.loc[cat_mask, "_lek_key"].value_counts().to_dict()
        per_study = {lk: float(amt) / counts[lk]
                     for lk, amt in availability_by_doctor.items() if counts.get(lk)}
        avail_alloc = round(sum(float(availability_by_doctor[lk]) for lk in per_study), 2)
        df["_doc_cost"] = df["_doc_cost"] + [
            per_study.get(lk, 0.0) if has_cat else 0.0
            for lk, has_cat in zip(df["_lek_key"], cat_mask)
        ]

    # WSPARCIE: stała miesięczna opłata jednostki (wiersz „WSPARCIE" w cenniku).
    # Rozbijamy ją RÓWNO na badania z kategorią danej jednostki i doliczamy do
    # przychodu — per jednostka wpada cała kwota, per lekarz/kategoria/priorytet
    # proporcjonalnie. „Całość (jak w rozliczeniu)" liczymy PRZED dodaniem wsparcia,
    # by nadal zgadzała się z Pulpitem/fakturą (badania + porównawcze).
    _total_rev_studies = round(float(df["_units_rev"].sum()), 2)
    wspar_alloc = wspar_unalloc = 0.0
    wsparcie_by_unit = {str(u).strip(): float(c) for (u, b), c in unit_prices.items()
                        if str(b).strip().upper() == "WSPARCIE" and c and float(c) > 0}
    if wsparcie_by_unit:
        _km = df["_kategoria"] != ""
        _klient = df["Klient"].astype(str).str.strip()
        _present = set(_klient.unique())
        _cat_counts = _klient[_km].value_counts().to_dict()
        per_unit_w = {u: amt / _cat_counts[u] for u, amt in wsparcie_by_unit.items() if _cat_counts.get(u)}
        df["_units_rev"] = df["_units_rev"] + [
            per_unit_w.get(k, 0.0) if hc else 0.0 for k, hc in zip(_klient, _km)
        ]
        wspar_alloc = round(sum(wsparcie_by_unit[u] for u in per_unit_w), 2)
        wspar_unalloc = round(sum(wsparcie_by_unit[u] for u in wsparcie_by_unit
                                  if u in _present and u not in per_unit_w), 2)

    grp = df[df["_kategoria"] != ""].groupby(["Modalność", "_kategoria"]).agg(
        ilosc=("_mult_doc", "sum"),
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
    cat = df[df["_kategoria"] != ""].copy()
    nocat = df[df["_kategoria"] == ""]

    # Rentowność per lekarz / per jednostka — „ile jesteśmy do przodu" (marża) na tym
    # samym zbiorze (badania z kategorią), więc spójne z totalem powyżej.
    def _agg_margin(frame, by_col, out_name):
        if frame.empty:
            return []
        g = frame.groupby(by_col).agg(
            ilosc=("_mult", "sum"),
            przychod_jednostki=("_units_rev", "sum"),
            koszt_lekarzy=("_doc_cost", "sum"),
        ).reset_index().rename(columns={by_col: out_name})
        g["marza"] = g["przychod_jednostki"] - g["koszt_lekarzy"]
        for c in ("ilosc", "przychod_jednostki", "koszt_lekarzy", "marza"):
            g[c] = g[c].round(2)
        g = g.sort_values("marza", ascending=False)
        return g.to_dict("records")

    # Per lekarz: grupujemy po znormalizowanym kluczu (scala warianty pisowni),
    # a do wyświetlenia bierzemy najczęstszą formę „Opisujący".
    cat["_lekarz"] = cat["Opisujący"].astype(str).str.strip() if "Opisujący" in cat.columns else ""
    doc = cat[cat["_lek_key"].astype(str).str.strip() != ""].copy()
    by_doctor = []
    if not doc.empty:
        names = (
            doc.groupby(["_lek_key", "_lekarz"]).size().reset_index(name="n")
            .sort_values("n", ascending=False).drop_duplicates("_lek_key").set_index("_lek_key")["_lekarz"]
        )
        gd = doc.groupby("_lek_key").agg(
            ilosc=("_mult_doc", "sum"),
            przychod_jednostki=("_units_rev", "sum"),
            koszt_lekarzy=("_doc_cost", "sum"),
        ).reset_index()
        gd["lekarz"] = gd["_lek_key"].map(names)
        gd["marza"] = gd["przychod_jednostki"] - gd["koszt_lekarzy"]
        for c in ("ilosc", "przychod_jednostki", "koszt_lekarzy", "marza"):
            gd[c] = gd[c].round(2)
        gd = gd.sort_values("marza", ascending=False)
        by_doctor = gd[["lekarz", "ilosc", "przychod_jednostki", "koszt_lekarzy", "marza"]].to_dict("records")

    by_unit = _agg_margin(cat, "Klient", "jednostka")

    # Wariant „kategorie badań JEDNOSTEK": to samo, ale grupowane po
    # „Rodzaj procedury rozlicz." (klasyfikacja jednostkowa) zamiast kategorii
    # lekarskiej. Liczone na tym samym zbiorze (badania z kategorią lekarską),
    # więc marża jest spójna z resztą.
    grp_u = cat.groupby(["Modalność", "Rodzaj procedury rozlicz."]).agg(
        ilosc=("_mult", "sum"),
        przychod_jednostki=("_units_rev", "sum"),
        koszt_lekarzy=("_doc_cost", "sum"),
    ).reset_index().rename(columns={"Rodzaj procedury rozlicz.": "kategoria"})
    grp_u["marza"] = grp_u["przychod_jednostki"] - grp_u["koszt_lekarzy"]
    grp_u = grp_u.sort_values("marza", ascending=False)
    for c in ("ilosc", "przychod_jednostki", "koszt_lekarzy", "marza"):
        grp_u[c] = grp_u[c].round(2)

    # Marża per PRIORYTET (Cito / Pilny / Planowy) — na tym samym zbiorze (badania
    # z kategorią lekarską). „CITO-CITO" → Cito, „Bardzo pilny" → Pilny (jak u lekarzy).
    def _prio_norm(v) -> str:
        s = str(v or "").strip().upper()
        if s.startswith("CITO"):
            return "Cito"
        if "PILN" in s:
            return "Pilny"
        if s.startswith("PLANOW"):
            return "Planowy"
        return str(v or "").strip() or "—"

    rows_priority = []
    if "Priorytet opisu" in cat.columns and not cat.empty:
        cp = cat.copy()
        cp["_prio"] = cp["Priorytet opisu"].map(_prio_norm)
        grp_p = cp.groupby("_prio").agg(
            ilosc=("_mult_doc", "sum"),
            przychod_jednostki=("_units_rev", "sum"),
            koszt_lekarzy=("_doc_cost", "sum"),
        ).reset_index().rename(columns={"_prio": "priorytet"})
        grp_p["marza"] = grp_p["przychod_jednostki"] - grp_p["koszt_lekarzy"]
        for c in ("ilosc", "przychod_jednostki", "koszt_lekarzy", "marza"):
            grp_p[c] = grp_p[c].round(2)
        _order = {"Cito": 0, "Pilny": 1, "Planowy": 2}
        grp_p["_ord"] = grp_p["priorytet"].map(lambda x: _order.get(x, 9))
        rows_priority = grp_p.sort_values("_ord").drop(columns="_ord").to_dict("records")

    return {
        "empty": False,
        # Migawka wyłączonych jednostek — pozwala wykryć nieaktualny zapis (cache).
        "_units_excluded": sorted(_excl_units),
        "_doctors_excluded": sorted(_excl_docs),
        "rows": grp.to_dict("records"),
        "rows_units": grp_u.to_dict("records"),
        "rows_priority": rows_priority,
        "by_doctor": by_doctor,
        "by_unit": by_unit,
        "totals": {
            # Pełny przychód jednostek (badania + porównawcze) — zgodny z Pulpitem,
            # BEZ wsparcia (liczony przed jego doliczeniem do marży).
            "przychod_jednostki_total": _total_rev_studies,
            # Marża liczona na badaniach Z kategorią lekarską (ten sam zbiór po obu
            # stronach); przychód obejmuje doliczone WSPARCIE.
            "przychod_jednostki": round(float(cat["_units_rev"].sum()), 2),
            "koszt_lekarzy": round(float(cat["_doc_cost"].sum()), 2),
            # z czego dopłaty za konsultacje (część kosztu lekarzy).
            "koszt_konsultacje": round(float(cat["_cons_cost"].sum()), 2),
            "marza": round(float(cat["_units_rev"].sum() - cat["_doc_cost"].sum()), 2),
            "studies": int(len(df)),
            "studies_with_category": int(len(cat)),
            "studies_without_category": int(len(nocat)),
            "przychod_jednostki_bez_kategorii": round(float(nocat["_units_rev"].sum()), 2),
            # Gotowość+triaż doliczona do kosztu (i część nieprzypisana — lekarze
            # z gotowością, ale bez badań z kategorią w tym miesiącu).
            "gotowosc_triaz": avail_alloc,
            "gotowosc_triaz_nieprzypisane": round(avail_total - avail_alloc, 2),
            # WSPARCIE doliczone do przychodu marży (i część nieprzypisana — jednostki
            # z badaniami, ale bez ani jednego badania z kategorią lekarską).
            "wsparcie": wspar_alloc,
            "wsparcie_nieprzypisane": wspar_unalloc,
        },
    }
