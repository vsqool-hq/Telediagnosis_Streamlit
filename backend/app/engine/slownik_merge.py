"""
Doklejanie DODATKOWEGO pliku wzorcowego (słownika) do wersji aktywnej.

Po co: słownik rośnie stopniowo — dochodzą pojedyncze procedury albo poprawki
kategorii. Zamiast wgrywać za każdym razem cały plik od nowa, można dosłać sam
„dopisek", a aplikacja skleja go z aktywną wersją i zapisuje jako NOWĄ wersję
(stara zostaje w historii, więc zawsze da się cofnąć).

Reguła scalania — nowe wygrywa:
  * wiersze z dosyłki trafiają na KONIEC,
  * jeżeli dosyłka powtarza klucz (Procedura + Rodzaj procedury rozlicz.), stary
    wiersz o tym kluczu jest USUWANY.

Dlaczego usuwamy, a nie tylko dopisujemy: silnik czyta słownik na dwa sposoby i
bez usunięcia dawałyby sprzeczne wyniki.
  * kategorie lekarzy (load_lekarz_categories) budują słownik wiersz po wierszu,
    więc wygrywa OSTATNI wpis — czyli dosyłka;
  * liczba okolic (find_recommended_regions) bierze MAKSIMUM ze wszystkich
    pasujących wierszy — czyli stara, wyższa wartość „przebiłaby" poprawkę.
Usunięcie starych wierszy o tym samym kluczu daje jedno, przewidywalne zachowanie.

Arkusz wyniku nazywa się „Szczegółowe" i jest pierwszy — tego wymagają oba
czytniki (load_lekarz_categories czyta po nazwie, load_single_reference_file
czyta arkusz nr 0).
"""

import io

# Kolumny, po których rozpoznajemy plik wzorcowy (jak w billing.load_single_reference_file).
REQUIRED_KEYWORDS = ("rodzaj procedury rozlicz.", "procedura", "ilość okolic")
KEY_COLS = ("Procedura", "Rodzaj procedury rozlicz.")
SHEET = "Szczegółowe"


def _norm_key(v) -> str:
    return str(v).strip().lower() if v is not None else ""


def _read_reference(src):
    """Wczytuje plik wzorcowy jako DataFrame.

    Nagłówek bywa przesunięty o kilka wierszy (tak jak w silniku próbujemy 0–3),
    a arkusz to „Szczegółowe" albo pierwszy w skoroszycie. Zwraca (df, sheet_used).
    Rzuca ValueError, gdy w żadnym wariancie nie ma wymaganych kolumn.
    """
    import pandas as pd

    if isinstance(src, (bytes, bytearray)):
        src = io.BytesIO(src)
    xls = pd.ExcelFile(src)
    sheets = [SHEET] if SHEET in xls.sheet_names else []
    sheets += [s for s in xls.sheet_names if s not in sheets]

    for sheet in sheets:
        for header_row in (0, 1, 2, 3):
            try:
                df = pd.read_excel(xls, sheet_name=sheet, header=header_row)
            except Exception:  # noqa: BLE001 — próbujemy kolejnego wariantu
                continue
            cols = " ".join(str(c).lower() for c in df.columns)
            if all(k in cols for k in REQUIRED_KEYWORDS):
                return df, sheet
    raise ValueError(
        "Plik nie wygląda na słownik — brak kolumn „Procedura”, "
        "„Rodzaj procedury rozlicz.” i „Ilość Okolic”."
    )


def merge_reference(base_src, add_src) -> dict:
    """Skleja dosyłkę (add_src) z aktywnym słownikiem (base_src).

    Zwraca:
      {"content": bytes nowego .xlsx,
       "stats": {base_rows, add_rows, replaced, added, final_rows, new_columns}}
    """
    import pandas as pd

    base, _ = _read_reference(base_src)
    add, _ = _read_reference(add_src)

    for col in KEY_COLS:
        if col not in base.columns:
            raise ValueError(f"W aktywnym słowniku brakuje kolumny „{col}”.")
        if col not in add.columns:
            raise ValueError(f"W dosyłanym pliku brakuje kolumny „{col}”.")

    base = base.dropna(how="all").copy()
    add = add.dropna(how="all").copy()
    base_rows, add_rows = len(base), len(add)

    def keyset(df):
        return set(zip(df[KEY_COLS[0]].map(_norm_key), df[KEY_COLS[1]].map(_norm_key)))

    add_keys = keyset(add)
    base_key_series = list(zip(base[KEY_COLS[0]].map(_norm_key), base[KEY_COLS[1]].map(_norm_key)))
    keep_mask = [k not in add_keys for k in base_key_series]
    replaced = base_rows - sum(keep_mask)
    base_kept = base[keep_mask]

    # Kolumny: kolejność z aktywnego słownika, a nowe (jeśli dosyłka je wnosi) na końcu.
    new_columns = [c for c in add.columns if c not in base.columns]
    merged = pd.concat([base_kept, add], ignore_index=True, sort=False)
    merged = merged[[c for c in list(base.columns) + new_columns if c in merged.columns]]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        merged.to_excel(w, sheet_name=SHEET, index=False)
    return {
        "content": buf.getvalue(),
        "stats": {
            "base_rows": base_rows,
            "add_rows": add_rows,
            "replaced": replaced,
            "added": add_rows - replaced,
            "final_rows": len(merged),
            "new_columns": new_columns,
        },
    }
