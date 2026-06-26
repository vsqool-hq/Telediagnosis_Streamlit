"""
Podgląd zawartości wgranego pliku (miniaturka/„co to za plik").

Czyta pierwsze wiersze i kolumny pliku (xlsx/xls/csv) i zwraca je jako prostą
strukturę JSON do wyświetlenia w tabelce na froncie. Służy do rozpoznania, jaki
plik należy wgrać w danym miejscu — bez otwierania go w Excelu.
"""

import os


def file_preview(path: str, max_rows: int = 30, max_cols: int = 15) -> dict:
    import pandas as pd

    if not path or not os.path.isfile(path):
        return {"empty": True, "reason": "Plik nie istnieje."}

    ext = os.path.splitext(path)[1].lower()
    sheet = None
    try:
        if ext in (".xlsx", ".xls"):
            xl = pd.ExcelFile(path)
            sheet = xl.sheet_names[0] if xl.sheet_names else None
            df = xl.parse(sheet, nrows=max_rows, dtype=object) if sheet else pd.DataFrame()
        else:  # CSV — wykryj separator (cenniki używają „;"); utf-8-sig usuwa BOM
            df = pd.read_csv(path, sep=None, engine="python", nrows=max_rows,
                             dtype=str, encoding="utf-8-sig")
    except Exception as e:  # noqa: BLE001
        return {"empty": True, "reason": f"Nie udało się odczytać podglądu ({e})."}

    total_cols = int(df.shape[1])
    df = df.iloc[:, :max_cols]
    columns = [str(c) for c in df.columns]
    # NaN → "", wszystko jako tekst (do wyświetlenia)
    rows = df.astype(object).where(pd.notna(df), "").astype(str).values.tolist()
    return {
        "empty": False,
        "sheet": sheet,
        "columns": columns,
        "rows": rows,
        "more_cols": max(0, total_cols - max_cols),
    }
