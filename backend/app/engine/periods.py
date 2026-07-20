"""
Okres rozliczenia z NAZWY pliku.

Pliki wejściowe mają w nazwie datę WYGENEROWANIA, a zawierają dane za POPRZEDNI
miesiąc (np. plik „…01.06.2026…" = dane za 2026-05). Stąd: period = miesiąc z
nazwy − 1. To jeden, spójny sposób ustalania miesiąca dla całego programu
(Pulpit, trend, Mapa, „ostatnie przeliczenie w miesiącu", Historia, nazwy plików
lekarzy). Lekki moduł bez pandas — można go importować wszędzie.
"""

import re


def period_from_filename(name) -> str | None:
    """Zwraca 'YYYY-MM' (miesiąc z nazwy pliku minus 1) dla pliku MIESIĘCZNEGO, albo
    None gdy plik NIE jest miesięczny.

    Umowa: plik MIESIĘCZNY (pełne rozliczenie miesiąca — pokazywane na Pulpicie,
    w Historii, używane w rozliczeniu lekarzy i porównaniu) ma w nazwie datę z
    PIERWSZYM DNIEM miesiąca (np. „…2026-07-01…" = dane za czerwiec). Każdy inny
    plik (bez daty albo z inną datą niż 1. dzień) traktujemy jako JEDNORAZOWY —
    liczony na żądanie, nigdzie indziej nieużywany. Dzięki temu przypadkowe pliki
    (np. „tduskszczecin05") nie są brane jako rozliczenie miesiąca."""
    s = str(name or "")
    y = mo = day = None
    m = re.search(r"(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})", s)            # YYYY-MM-DD
    if m:
        y, mo, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y is None:
        m = re.search(r"(?<!\d)(\d{1,2})[-_.](\d{1,2})[-_.](20\d{2})", s)  # DD-MM-YYYY
        if m:
            day, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y is None:
        m = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", s)          # YYYYMMDD
        if m:
            y, mo, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # Bez pełnej daty (sam YYYY-MM, brak dnia) → nie jest to plik miesięczny.
    if y is None or mo is None or not (1 <= mo <= 12):
        return None
    if day != 1:                               # tylko PIERWSZY dzień miesiąca = miesięczny
        return None
    mo -= 1                                     # dane za POPRZEDNI miesiąc
    if mo == 0:
        mo, y = 12, y - 1
    return f"{y:04d}-{mo:02d}"


def period_to_mmyyyy(period: str | None) -> str:
    """'2026-05' → '052026' (do nazw plików lekarzy). Pusty wynik, gdy brak."""
    if not period or "-" not in period:
        return ""
    yyyy, mm = period.split("-", 1)
    return f"{mm}{yyyy}"
