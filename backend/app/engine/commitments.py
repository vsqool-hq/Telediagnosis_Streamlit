"""
Plik zobowiązań lekarzy — uzupełnianie ILOŚCI OKOLIC po rozliczeniu.

„Plik zobowiązań" to szeroki skoroszyt (zakładka = lekarz), wgrywany przez
konwerter cennika lekarzy i przechowywany jako source.xlsx przy aktywnej wersji
cennika lekarzy. Po policzeniu rozliczenia danego miesiąca wpisujemy do niego
liczbę OKOLIC per lekarz i kategoria, w kolumnie tego miesiąca — KUMULATYWNIE
(kolejne liczone miesiące dopisują się do tego samego pliku; nie ruszamy nic poza
komórkami ilości — formuły SUMA/ŚREDNIA przeliczą się same w Excelu).

Mapowanie:
  * lekarz → zakładka: doctor_key() (niewrażliwe na kolejność imię/nazwisko),
  * miesiąc → kolumna: data w WIERSZU 2 (działa też dla układów z aneksami),
  * kategoria → wiersz: etykieta w kolumnie A (wiersze wspólne dla bloków aneksów).
"""

import os
import re
import shutil
import datetime
from collections import defaultdict

from openpyxl import load_workbook

from app import db
from app.storage import version_dir
from app.engine.cennik_lekarzy_convert import doctor_key


def _ncat(s) -> str:
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip().upper()


def active_commitments_workbook():
    """Zwraca (ścieżka_source.xlsx, nazwa_wyświetlana) aktywnego pliku zobowiązań,
    albo (None, None) jeśli aktywny cennik lekarzy nie był wgrany jako .xlsx."""
    v = db.get_active_version("cennik_lekarzy")
    if not v:
        return None, None
    vdir = version_dir("cennik_lekarzy", v["id"])
    path = os.path.join(vdir, "source.xlsx")
    if not os.path.isfile(path):
        return None, None
    name = "ZOBOWIĄZANIA LEKARZY.xlsx"
    nf = os.path.join(vdir, "source_name.txt")
    if os.path.isfile(nf):
        try:
            name = open(nf, encoding="utf-8").read().strip() or name
        except OSError:
            pass
    return path, name


def fill_workbook(wb_path: str, period_ym: str, okolice_rows: list) -> dict:
    """
    Uzupełnia w skoroszycie (w miejscu) liczbę okolic dla danego miesiąca.
      period_ym    — „YYYY-MM" (miesiąc rozliczenia),
      okolice_rows — [{lekarz, kategoria, okolice}] z build_doctor_billing.
    Nadpisuje TYLKO komórki (kategoria × miesiąc); reszty nie rusza.
    """
    y, m = (int(x) for x in period_ym.split("-")[:2])

    by_doc = defaultdict(dict)   # doctor_key -> {NCAT: okolice}
    disp_by_key = {}
    for r in okolice_rows:
        k = doctor_key(r["lekarz"])
        if not k:
            continue
        by_doc[k][_ncat(r["kategoria"])] = r["okolice"]
        disp_by_key.setdefault(k, r["lekarz"])

    report = {"period": period_ym, "doctors_written": 0, "cells_written": 0,
              "doctors_no_sheet": [], "no_month_column": [], "categories_not_found": []}

    wb = load_workbook(wb_path)  # data_only=False — zachowujemy formuły

    sheet_by_key = {}
    for sn in wb.sheetnames:
        if sn.strip().upper().startswith("ZBIORCZO"):
            continue
        sheet_by_key.setdefault(doctor_key(sn), sn)

    for k, cats in by_doc.items():
        sn = sheet_by_key.get(k)
        if not sn:
            report["doctors_no_sheet"].append(disp_by_key.get(k, k))
            continue
        ws = wb[sn]

        # miesiąc → kolumna (data w wierszu 2)
        target_col = None
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=2, column=c).value
            if isinstance(v, datetime.datetime) and v.year == y and v.month == m:
                target_col = c
                break
        if target_col is None:
            report["no_month_column"].append(sn)
            continue

        # kategoria → wiersz (etykieta w kolumnie A; wiersze wspólne dla bloków)
        cat_row = {}
        for rr in range(1, ws.max_row + 1):
            a = ws.cell(row=rr, column=1).value
            if a is not None:
                cat_row.setdefault(_ncat(a), rr)

        wrote = 0
        for ncat, okolice in cats.items():
            row = cat_row.get(ncat)
            if not row:
                report["categories_not_found"].append({"lekarz": disp_by_key.get(k, k), "kategoria": ncat})
                continue
            ws.cell(row=row, column=target_col).value = int(okolice)
            wrote += 1
        if wrote:
            report["doctors_written"] += 1
            report["cells_written"] += wrote

    wb.save(wb_path)
    return report


def fill_and_package(wb_path: str, period_ym: str, okolice_rows: list,
                     package_dir: str, display_name: str) -> dict:
    """Uzupełnia przechowywany plik (kumulatywnie) i wrzuca jego kopię do paczki."""
    report = fill_workbook(wb_path, period_ym, okolice_rows)
    os.makedirs(package_dir, exist_ok=True)
    base = re.sub(r'[\\/:*?"<>|]+', "", display_name or "ZOBOWIĄZANIA LEKARZY")
    base = re.sub(r"\.(xlsx|xls)$", "", base, flags=re.I).strip() or "ZOBOWIĄZANIA LEKARZY"
    out = os.path.join(package_dir, f"{base} - ilosci.xlsx")
    shutil.copy2(wb_path, out)
    report["package_file"] = os.path.basename(out)
    return report
