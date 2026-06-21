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

from app.engine.billing import build_price_key, bill_extract_multiplier

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


def build_revenue(wynik_dir: str, cennik_dir: str) -> pd.DataFrame:
    """Zwraca DataFrame [Klient, Modalność, Ilość, Wartość] zsumowany po grupach."""
    prices = _load_prices(cennik_dir)
    if prices is None or not os.path.isdir(wynik_dir):
        return pd.DataFrame(columns=["Klient", "Modalność", "Ilość", "Wartość"])

    frames = []
    for path in glob.glob(os.path.join(wynik_dir, "*.xlsx")):
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

        for col in GROUPING_COLUMNS:
            if pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].astype(str).str.strip()

        grouped = (
            df.groupby(GROUPING_COLUMNS)
            .agg({"Nr badania": "count", "Badania do porównania": "sum"})
            .reset_index()
        )
        # rename jak w silniku — dzięki temu build_price_key nie widzi 'Badania do porównania'
        grouped.rename(columns={"Nr badania": "#", "Badania do porównania": "Porownawcze_Flag"}, inplace=True)

        grouped["Mnożnik"] = grouped["Procedura rozlicz."].apply(bill_extract_multiplier)
        grouped["CENA_KLUCZ"] = grouped.apply(build_price_key, axis=1)

        merged = grouped.merge(
            prices[["Jednostka", "BADANIE", "Cena"]],
            left_on=["Klient", "CENA_KLUCZ"],
            right_on=["Jednostka", "BADANIE"],
            how="left",
        )
        merged["Ilość"] = merged["#"] * merged["Mnożnik"]
        merged["Wartość"] = merged["Ilość"] * merged["Cena"].fillna(0)
        frames.append(merged[["Klient", "Modalność", "Ilość", "Wartość"]])

    if not frames:
        return pd.DataFrame(columns=["Klient", "Modalność", "Ilość", "Wartość"])

    return pd.concat(frames, ignore_index=True)


def _modality_norm(m) -> str:
    m = str(m).strip().upper()
    return m if m in {"RTG", "TK", "MR", "MMG"} else "INNE"


def summarize(wynik_dir: str, cennik_dir: str) -> dict:
    """Podsumowanie zadania: przychód/ilości łącznie, wg modalności i top klienci."""
    df = build_revenue(wynik_dir, cennik_dir)
    if df.empty:
        return {"empty": True}
    df = df.copy()
    df["Modalność"] = df["Modalność"].map(_modality_norm)
    by_mod = df.groupby("Modalność").agg(count=("Ilość", "sum"), revenue=("Wartość", "sum")).reset_index()
    by_client = (
        df.groupby("Klient").agg(count=("Ilość", "sum"), revenue=("Wartość", "sum"))
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

    return {
        "empty": False,
        "total_studies": int(df["Ilość"].sum()),
        "total_revenue": round(float(df["Wartość"].sum()), 2),
        "clients_count": int(df["Klient"].nunique()),
        "zero_clients": zero_clients,
        "by_modality": [
            {"modality": r["Modalność"], "count": int(r["count"]), "revenue": round(float(r["revenue"]), 2)}
            for _, r in by_mod.iterrows()
        ],
        "top_clients": [
            {"client": r["Klient"], "count": int(r["count"]), "revenue": round(float(r["revenue"]), 2)}
            for _, r in by_client.iterrows()
        ],
    }


def cached_summary(base_dir: str, wynik_dir: str, cennik_dir: str) -> dict:
    """
    Zwraca podsumowanie zadania z cache (stats.json w katalogu zadania). Liczone
    RAZ — wyniki zadania są niezmienne, więc cache nigdy się nie dezaktualizuje.
    Dzięki temu Historia/Pulpit nie przeliczają wszystkich plików przy każdym wejściu.
    """
    cache = os.path.join(base_dir, "stats.json")
    if os.path.isfile(cache):
        try:
            with open(cache, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    summary = summarize(wynik_dir, cennik_dir)
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False)
    except OSError:
        pass
    return summary
