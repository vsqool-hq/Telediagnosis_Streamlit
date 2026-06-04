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
    df = pd.read_csv(csvs[0], sep=";", encoding="utf-8", decimal=",")
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
