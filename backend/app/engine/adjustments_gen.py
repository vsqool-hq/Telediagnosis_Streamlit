"""
Generator współczynników cen jednostek z pliku ZOBOWIĄZANIA (SZPITALE).

Dla każdej jednostki (arkusz) i każdego badania POCHODNEGO (klucz zawiera
PORÓWNAWCZE / PORÓW. / ONKO / ANGIO) liczy:

    factor = stawka_pochodna / stawka_bazowa

gdzie baza = ten sam klucz z usuniętymi modyfikatorami (np.
„TK PORÓWNAWCZE CITO" → „TK CITO", „MR PLANOWE GŁ/KRG ONKO PORÓW." →
„MR PLANOWE GŁ/KRG"). Obie stawki bierzemy z NAJNOWSZEJ kolumny aneksu, w której
jednocześnie są > 0 (kolumny aneksów rozpoznajemy po nagłówku zawierającym „STAWK"
oraz zawsze kolumnie B). To odtwarza regułę umowną „pochodne liczone jako procent
bazowej", żeby uzupełnić współczynniki w Ustawieniach dla pozycji, których w
cenniku (zbiorczym) nie ma wprost (myślnik „-").

Wynik jest PROPOZYCJĄ do zatwierdzenia przez człowieka (nie stosujemy automatycznie).
"""

import re
import datetime as dt

SKIP_SHEETS = {"LEKARZE", "TABELA", "ZBIORCZO 2026", "FORMUŁY (5)"}
_MODS = ("PORÓWNAWCZE", "PORÓW.", "PORÓW", "ONKO", "ANGIO")


def _nkey(s) -> str:
    return re.sub(r"\s+", " ", str(s if s is not None else "").strip()).upper()


def _base_key(k: str) -> str:
    """Klucz bazowy = badanie bez tokenów pochodnych."""
    return " ".join(t for t in k.split(" ") if t and t not in _MODS)


def _is_derived(k: str) -> bool:
    return any(m in k.split(" ") for m in _MODS)


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def generate_adjustments(path_or_bytes) -> dict:
    """Zwraca:
      { proposal: { jednostka: { KLUCZ_POCHODNY: {base, factor} } },
        detail:   [ {unit, key, base, factor, base_rate, derived_rate} ],
        stats:    {units, rules, skipped_no_base, sheets_scanned},
        warning:  str|None }
    """
    from openpyxl import load_workbook  # openpyxl dopiero tutaj
    wb = load_workbook(path_or_bytes, data_only=True, read_only=True)

    proposal: dict = {}
    detail: list = []
    skipped_no_base = 0
    sheets_scanned = 0

    for sheet in wb.sheetnames:
        if _nkey(sheet) in SKIP_SHEETS:
            continue
        rows = list(wb[sheet].iter_rows(values_only=True))
        if not rows:
            continue
        # wiersz nagłówka = ten z 'RTG' w kolumnie A (etykiety STAWKI / daty miesięcy)
        hdr_i = next((i for i, r in enumerate(rows[:6]) if _nkey(r[0]) == "RTG"), None)
        if hdr_i is None:
            continue
        hdr = rows[hdr_i]
        # kolumny stawek: nagłówek zawiera 'STAWK' albo kolumna B (idx 1), byle nie data
        stawka_cols = sorted({
            j for j, h in enumerate(hdr)
            if j != 0 and not isinstance(h, dt.datetime) and ("STAWK" in _nkey(h) or j == 1)
        })
        if not stawka_cols:
            continue
        sheets_scanned += 1

        # klucz badania -> {kolumna: stawka}
        ratemap: dict = {}
        for r in rows:
            k = _nkey(r[0])
            if not k or "SUMA" in k or k in ("RTG", "TK", "MR", "MMG", "ILOŚĆ OKOLIC"):
                continue
            col_rates = {c: _num(r[c]) for c in stawka_cols if c < len(r) and _num(r[c]) is not None}
            if col_rates:
                ratemap[k] = col_rates

        rules: dict = {}
        for k, col_rates in ratemap.items():
            if not _is_derived(k):
                continue
            bk = _base_key(k)
            if bk == k or bk not in ratemap:
                skipped_no_base += 1
                continue
            base_rates = ratemap[bk]
            chosen = None
            for c in reversed(stawka_cols):                 # od najnowszej kolumny aneksu
                dv, bv = col_rates.get(c), base_rates.get(c)
                if dv and dv > 0 and bv and bv > 0:
                    chosen = (dv, bv)
                    break
            if not chosen:
                continue
            dv, bv = chosen
            factor = round(dv / bv, 6)
            rules[k] = {"base": bk, "factor": factor}
            detail.append({"unit": sheet, "key": k, "base": bk, "factor": factor,
                           "base_rate": bv, "derived_rate": dv})
        if rules:
            proposal[sheet] = rules

    wb.close()

    warning = None
    if sheets_scanned == 0:
        warning = ("Nie znaleziono arkuszy jednostek ze stawkami. Upewnij się, że to "
                   "pełny plik ZOBOWIĄZANIA SZPITALE (arkusze per jednostka), a nie sam "
                   "arkusz zbiorczy.")

    detail.sort(key=lambda d: (d["unit"], d["key"]))
    return {
        "proposal": proposal,
        "detail": detail,
        "stats": {
            "units": len(proposal),
            "rules": sum(len(v) for v in proposal.values()),
            "skipped_no_base": skipped_no_base,
            "sheets_scanned": sheets_scanned,
        },
        "warning": warning,
    }
