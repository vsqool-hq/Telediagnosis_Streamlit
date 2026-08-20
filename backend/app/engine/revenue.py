"""
Liczenie przychodu (wartość w zł) z plików rozliczeń zadania.

Pliki wynikowe (Rozliczenie_*.xlsx) trzymają w arkuszu 'Rozliczenie' formuły Excela,
więc openpyxl/pandas nie odczytają z nich gotowych liczb. Dlatego wartość liczymy
w Pythonie, odtwarzając DOKŁADNIE tę samą logikę grupowania i wyceny, co silnik
rozliczeniowy (ten sam build_price_key i ten sam sposób grupowania), tak by liczby
zgadzały się z arkuszem.
"""

import os
import glob
import json

import pandas as pd

from app.engine.billing import (
    build_price_key, bill_extract_multiplier, fill_price_with_base, porownawcze_surcharge,
    mask_comparative, wsparcie_by_unit,
)

GROUPING_COLUMNS = [
    "Priorytet opisu", "Modalność", "Procedura",
    "Rodzaj procedury rozlicz.", "Procedura rozlicz.", "Klient",
]


def _load_prices(cennik_dir: str) -> pd.DataFrame | None:
    csvs = glob.glob(os.path.join(cennik_dir, "*.csv"))
    if not csvs:
        return None
    df = pd.read_csv(csvs[0], sep=";", encoding="utf-8-sig", decimal=",")
    df["Cena"] = pd.to_numeric(df["Cena"], errors="coerce")
    df["BADANIE"] = df["BADANIE"].str.replace(r"\s+", " ", regex=True).str.strip()
    return df


def _studies_dir(wynik_dir: str) -> str:
    """Źródło badań do policzenia przychodu. PREFERUJEMY pliki SPRAWDZONE (Etap 1) —
    są liczone BIEŻĄCĄ logiką silnika, tak samo jak Porównanie, więc przychód
    jednostek na Pulpicie == przychód w Porównaniu. 'Wynik' bywał policzony starszym
    silnikiem i po zmianach (np. dopłata porównawcza) rozjeżdżał się z Porównaniem.
    Zapas: 'Wynik' (gdy sprawdzonych brak — np. zadania zaimportowane z chmury)."""
    base = os.path.dirname(os.path.normpath(wynik_dir))
    # Napraw zadania zaimportowane starą paczką (pliki w złych katalogach), by przychód
    # też się liczył ze sprawdzonych spójnie z Porównaniem.
    try:
        from app.storage import heal_job_dirs
        heal_job_dirs(os.path.basename(base))
    except Exception:  # noqa: BLE001
        pass
    spr = os.path.join(base, "pliki_sprawdzone")
    if os.path.isdir(spr):
        xs = [f for f in glob.glob(os.path.join(spr, "*.xlsx")) if not os.path.basename(f).startswith("~$")]
        if xs:
            return spr
    return wynik_dir


def build_revenue(wynik_dir: str, cennik_dir: str) -> pd.DataFrame:
    """Zwraca DataFrame [Klient, Modalność, Ilość, Wartość] zsumowany po grupach.
    Liczy z plików SPRAWDZONYCH (spójnie z Porównaniem) — patrz _studies_dir."""
    prices = _load_prices(cennik_dir)
    src_dir = _studies_dir(wynik_dir)
    if prices is None or not os.path.isdir(src_dir):
        return pd.DataFrame(columns=["Klient", "Modalność", "Ilość", "Wartość"])

    # Pliki SPRAWDZONE (wejściowe) mają w „Badania do porównania" surową flagę 0/1 →
    # przemnażamy ją przez okolice per opis (tak jak billing.py na Szczegółowych).
    # Pliki „Wynik" (tryb awaryjny) mają tę kolumnę JUŻ przemnożoną — wtedy nie mnożymy
    # drugi raz, żeby nie liczyć podwójnie.
    _raw_source = os.path.basename(os.path.normpath(src_dir)) == "pliki_sprawdzone"

    frames = []
    for path in glob.glob(os.path.join(src_dir, "*.xlsx")):
        if os.path.basename(path).startswith("~$"):
            continue
        try:
            df = pd.read_excel(path, sheet_name="Szczegółowe")
        except Exception:
            continue
        if not all(c in df.columns for c in GROUPING_COLUMNS):
            continue

        if "Badania do porównania" not in df.columns:
            df["Badania do porównania"] = 0
        df["Badania do porównania"] = pd.to_numeric(df["Badania do porównania"], errors="coerce").fillna(0)

        # Bramka per jednostka (lista 'comparative_units') — spójnie z tabelą jednostek.
        df = mask_comparative(df)

        # Przemnożenie porównawczych przez okolice per opis (tylko dla surowych plików
        # sprawdzonych) — spójnie z billing.py na Szczegółowych. „Wynik" ma już przemnożone.
        if _raw_source:
            df["Badania do porównania"] = (
                df["Badania do porównania"]
                * df["Procedura rozlicz."].apply(bill_extract_multiplier)
            )

        for col in GROUPING_COLUMNS:
            if pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].astype(str).str.strip()

        grouped = (
            df.groupby(GROUPING_COLUMNS)
            .agg({"Nr badania": "count", "Badania do porównania": "sum"})
            .reset_index()
        )
        # rename jak w silniku — dzięki temu build_price_key nie widzi 'Badania do porównania'.
        # „Porownawcze_Flag" = suma już przemnożonej kolumny (bez dalszego mnożenia).
        grouped.rename(columns={"Nr badania": "#", "Badania do porównania": "Porownawcze_Flag"}, inplace=True)

        grouped["Mnożnik"] = grouped["Procedura rozlicz."].apply(bill_extract_multiplier)
        grouped["CENA_KLUCZ"] = grouped.apply(build_price_key, axis=1)

        merged = grouped.merge(
            prices[["Jednostka", "BADANIE", "Cena"]],
            left_on=["Klient", "CENA_KLUCZ"],
            right_on=["Jednostka", "BADANIE"],
            how="left",
        )
        merged = fill_price_with_base(merged, prices)  # ONKO/ANGIO → cena bazowa, gdy 0/brak
        merged["Ilość"] = merged["#"] * merged["Mnożnik"]
        merged["Wartość"] = merged["Ilość"] * merged["Cena"].fillna(0)
        # Dopłata za badania porównawcze — od liczby porównawczych JUŻ przemnożonej przez
        # okolice (per opis wyżej, tylko dla surowych plików sprawdzonych — guard
        # _raw_source), spójnie z tabelą jednostek (billing.py).
        surcharge, _ = porownawcze_surcharge(merged, prices)
        merged["Wartość"] = merged["Wartość"] + surcharge
        # CENA_KLUCZ/#/Cena — do diagnostyki „rozliczone po 0 zł" w summarize().
        frames.append(merged[["Klient", "Modalność", "Ilość", "Wartość", "CENA_KLUCZ", "#", "Cena"]])

    if not frames:
        return pd.DataFrame(columns=["Klient", "Modalność", "Ilość", "Wartość"])

    combined = pd.concat(frames, ignore_index=True)

    # WSPARCIE — stała miesięczna kwota z cennika, doliczana RAZ na jednostkę jako
    # osobny wiersz (Modalność „WSPARCIE"). Wchodzi do przychodu (Pulpit) i marży
    # (Porównanie) — spójnie z podsumowaniem w pliku rozliczenia jednostki.
    wsp = wsparcie_by_unit(prices)
    if wsp:
        rows = []
        for kl in combined["Klient"].dropna().unique():
            amt = wsp.get(str(kl).strip())
            if amt:
                rows.append({"Klient": kl, "Modalność": "WSPARCIE", "Ilość": 0,
                             "Wartość": amt, "CENA_KLUCZ": "WSPARCIE", "#": 0, "Cena": amt})
        if rows:
            combined = pd.concat([combined, pd.DataFrame(rows)], ignore_index=True)

    return combined


def _modality_norm(m) -> str:
    m = str(m).strip().upper()
    if m.startswith("MAMMOGRAF"):
        return "MMG"
    return m if m in {"RTG", "TK", "MR", "MMG", "WSPARCIE"} else "INNE"


def _result_period(wynik_dir: str) -> str | None:
    """Miesiąc rozliczeniowy „YYYY-MM" z dat w plikach wynikowych (data zatwierdzenia,
    fallback: data badania). Służy do grupowania zadań po miesiącu niezależnie od
    tego, kiedy zostały policzone."""
    if not os.path.isdir(wynik_dir):
        return None
    for path in glob.glob(os.path.join(wynik_dir, "*.xlsx")):
        if os.path.basename(path).startswith("~$"):
            continue
        for col in ("Data 1. zatwierdzenia", "Data badania (UTC)"):
            try:
                d = pd.read_excel(path, sheet_name="Szczegółowe", usecols=[col])
            except Exception:  # noqa: BLE001
                continue
            dt = pd.to_datetime(d[col], errors="coerce").dropna()
            if not dt.empty:
                return str(dt.dt.strftime("%Y-%m").mode().iloc[0])
    return None


def summarize(wynik_dir: str, cennik_dir: str) -> dict:
    """Podsumowanie zadania: przychód/ilości łącznie, wg modalności i top klienci."""
    df = build_revenue(wynik_dir, cennik_dir)
    if df.empty:
        return {"empty": True}
    df = df.copy()
    # Jednostki wyłączone w ustawieniach — pomijane w statystykach (Pulpit/trend).
    from app.engine.billing import get_excluded_units, _norm_unit
    excl = get_excluded_units()
    if excl:
        df = df[~df["Klient"].map(_norm_unit).isin(excl)]
        if df.empty:
            return {"empty": True}
    df["Modalność"] = df["Modalność"].map(_modality_norm)
    by_mod = df.groupby("Modalność").agg(count=("Ilość", "sum"), revenue=("Wartość", "sum")).reset_index()

    # Grupy jednostek (czysto wizualne) — łączą wybrane jednostki w jeden wiersz
    # w „top jednostkach". clients_count zostaje surowy (liczba fizycznych jednostek).
    from app.engine.config import load_config, build_unit_group_map, group_label
    gmap = build_unit_group_map(load_config().get("unit_groups", []))
    df["_klient_grp"] = df["Klient"].map(lambda c: group_label(c, gmap))
    by_client = (
        df.groupby("_klient_grp").agg(count=("Ilość", "sum"), revenue=("Wartość", "sum"))
        .sort_values("revenue", ascending=False).head(15).reset_index()
    )

    # --- Diagnostyka: jednostki z 0 zł za cały miesiąc (z podpowiedzią z cennika) ---
    prices = _load_prices(cennik_dir)
    cennik_units = sorted(set(prices["Jednostka"].astype(str).str.strip())) if prices is not None else []
    cennik_lower = {u.lower() for u in cennik_units}
    per_client = df.groupby("Klient").agg(studies=("Ilość", "sum"), revenue=("Wartość", "sum"))

    def _suggest(c: str):
        cl = c.lower().strip()
        out = []
        for u in cennik_units:
            ul = u.lower()
            if ul == cl:
                continue
            if ul.startswith(cl[:5]) or cl.startswith(ul[:5]) or cl in ul or ul in cl:
                out.append(u)
        return out[:3]

    zero_clients = []
    for c, r in per_client[per_client["revenue"] == 0].sort_values("studies", ascending=False).iterrows():
        in_cennik = str(c).strip().lower() in cennik_lower
        zero_clients.append({
            "client": str(c),
            "studies": int(r["studies"]),
            "in_cennik": in_cennik,
            "suggestions": [] if in_cennik else _suggest(str(c)),
        })

    # --- Diagnostyka: badania rozliczone po stawce 0 zł ---
    # Pozycja W CENNIKU istnieje (Cena nie jest pusta), ale wynosi 0 zł — inna sytuacja
    # niż „brak pozycji" (Cena NaN). Tabela: jednostka × kategoria (klucz cennika) × liczba badań.
    zero_rates = []
    zero_rate_studies = 0
    if "Cena" in df.columns:
        zr = df[pd.to_numeric(df["Cena"], errors="coerce") == 0]
        if not zr.empty:
            zero_rate_studies = int(zr["#"].sum())
            zt = (
                zr.groupby(["Klient", "CENA_KLUCZ"])["#"].sum().reset_index()
                .rename(columns={"Klient": "jednostka", "CENA_KLUCZ": "kategoria", "#": "n"})
                .sort_values("n", ascending=False)
            )
            zero_rates = [
                {"jednostka": str(r["jednostka"]), "kategoria": str(r["kategoria"]), "n": int(r["n"])}
                for _, r in zt.head(200).iterrows()
            ]

    return {
        "empty": False,
        "period": _result_period(wynik_dir),  # miesiąc rozliczeniowy „YYYY-MM" z dat w pliku
        "total_studies": int(df["Ilość"].sum()),
        "total_revenue": round(float(df["Wartość"].sum()), 2),
        "clients_count": int(df["Klient"].nunique()),
        "zero_clients": zero_clients,
        "zero_rate_studies": zero_rate_studies,
        "zero_rates": zero_rates,
        "by_modality": [
            {"modality": r["Modalność"], "count": int(r["count"]), "revenue": round(float(r["revenue"]), 2)}
            for _, r in by_mod.iterrows()
        ],
        "top_clients": [
            {"client": r["_klient_grp"], "count": int(r["count"]), "revenue": round(float(r["revenue"]), 2)}
            for _, r in by_client.iterrows()
        ],
    }


def cached_summary(base_dir: str, wynik_dir: str, cennik_dir: str) -> dict:
    """
    Zwraca podsumowanie zadania z cache (stats.json w katalogu zadania). Liczone
    RAZ — wyniki zadania są niezmienne, więc cache nigdy się nie dezaktualizuje.
    Dzięki temu Historia/Pulpit nie przeliczają wszystkich plików przy każdym wejściu.
    """
    from app.engine.config import load_config
    from app.engine import ENGINE_VERSION
    from app.engine.billing import get_excluded_units, get_comparative_units
    # Sygnatura: grupy jednostek (zmiana grupowania → przelicz „top jednostki"),
    # wersja silnika (zmiana logiki wyceny → przelicz cały przychód z bieżącym silnikiem,
    # by Pulpit zgadzał się z Porównaniem), wyłączone jednostki ORAZ lista jednostek
    # z porównawczymi (zmiana → przelicz, bo zmienia przychód).
    _comp = get_comparative_units()
    sig = json.dumps({"groups": load_config().get("unit_groups", []), "engine": ENGINE_VERSION,
                      "units_excluded": sorted(get_excluded_units()),
                      "comparative_units": sorted(_comp) if _comp is not None else "__all__"},
                     ensure_ascii=False, sort_keys=True)
    cache = os.path.join(base_dir, "stats.json")
    if os.path.isfile(cache):
        try:
            with open(cache, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("_groups_sig") == sig:
                return data
        except (OSError, ValueError):
            pass
    summary = summarize(wynik_dir, cennik_dir)
    summary["_groups_sig"] = sig
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False)
    except OSError:
        pass
    return summary
