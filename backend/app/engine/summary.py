"""
Agregacja danych z rozliczeń do pliku importowego (dawne podsumowanie.py).
Sparametryzowane na ścieżki, by działało w kontekście pojedynczego zadania.
"""

import pandas as pd
import os
import re
from datetime import date
from dateutil.relativedelta import relativedelta

from app.engine.config import load_config

CONFIG = load_config()
MR_GLKRG_KEYWORDS = CONFIG["mr_glkrg_keywords"]
MR_STAWY_KEYWORDS = CONFIG["mr_stawy_keywords"]


def get_last_day_of_previous_month():
    today = date.today()
    first_day_of_current_month = today.replace(day=1)
    last_day_of_previous_month = first_day_of_current_month - relativedelta(days=1)
    return last_day_of_previous_month.strftime('%d.%m.%Y')


def extract_multiplier(procedure_text):
    if pd.isna(procedure_text) or procedure_text == "":
        return 1
    numbers = re.findall(r'\d+', str(procedure_text))
    return int(numbers[0]) if numbers else 1


def mr_get_anatomical_category(procedura: str, rodzaj_proc: str) -> str:
    if 'MR Ortopedia' in rodzaj_proc:
        return 'stawy'
    proc_lower = str(procedura).lower()
    for kw in MR_GLKRG_KEYWORDS:
        if kw in proc_lower:
            return 'GŁ/KRG'
    for kw in MR_STAWY_KEYWORDS:
        if kw in proc_lower:
            return 'stawy'
    return 'inne'


def generate_badanie_string(row, include_comparative_word=False):
    modalnosc = row['Modalność']
    parts = []
    try:
        try:
            porownawcze_val = int(float(row.get('Badania do porównania', 0)))
            is_comparative = porownawcze_val > 0
        except (ValueError, TypeError):
            is_comparative = False

        if modalnosc == 'Mammografia':
            rodzaj_proc = str(row.get('Rodzaj procedury rozlicz.', ''))
            if 'MMG Screening' in rodzaj_proc:
                parts.append('MMG SKRINING')
            else:
                parts.append('MMG')

        elif modalnosc == 'RTG':
            parts.append('RTG')
            parts.append(row['Priorytet opisu'])

        elif modalnosc == 'TK':
            parts.append('TK')
            if is_comparative and include_comparative_word:
                parts.append('PORÓWNAWCZE')
            parts.append(row['Priorytet opisu'])
            rodzaj_proc = str(row.get('Rodzaj procedury rozlicz.', ''))
            if 'TK Angiografia' in rodzaj_proc:
                parts.append('ANGIO')
            elif 'TK Onkologia' in rodzaj_proc:
                parts.append('ONKO')

        elif modalnosc == 'MR':
            parts.append('MR')
            parts.append(row['Priorytet opisu'])
            procedura = str(row.get('Procedura', ''))
            rodzaj_proc = str(row.get('Rodzaj procedury rozlicz.', ''))
            kat = mr_get_anatomical_category(procedura, rodzaj_proc)
            parts.append(kat)
            mr_typ = ''
            if 'MR Angiografia' in rodzaj_proc:
                mr_typ = 'angio'
                parts.append('angio')
            elif 'MR Onkologia' in rodzaj_proc:
                mr_typ = 'ONKO'
            if is_comparative and include_comparative_word:
                if mr_typ == 'ONKO':
                    parts.append('ONKO')
                    parts.append('PORÓW.')
                else:
                    parts.append('PORÓWNAWCZE')
            else:
                if mr_typ == 'ONKO':
                    parts.append('ONKO')
        else:
            if modalnosc:
                parts.append(str(modalnosc))

        return ' '.join(filter(None, parts)).strip()
    except (KeyError, TypeError) as e:
        print(f"Błąd w przetwarzaniu wiersza: {e}.", flush=True)
        return f"BŁĄD - {modalnosc}"


def build_import_data(wynik_folder: str) -> pd.DataFrame:
    """Buduje zagregowany DataFrame importowy z plików rozliczeń w wynik_folder."""
    all_data_to_append = []
    settlement_date = get_last_day_of_previous_month()
    print(f"Data rozliczenia dla bieżącego uruchomienia: {settlement_date}", flush=True)

    if not os.path.isdir(wynik_folder):
        print(f"BŁĄD: Folder '{wynik_folder}' nie istnieje.", flush=True)
        return pd.DataFrame()

    for filename in os.listdir(wynik_folder):
        if filename.endswith('.xlsx') and not filename.startswith('~$'):
            file_path = os.path.join(wynik_folder, filename)
            print(f"Przetwarzam plik: {filename}...", flush=True)
            try:
                df = pd.read_excel(file_path, sheet_name='Szczegółowe', dtype={'Badania do porównania': 'str'})
                df.dropna(subset=['Modalność', 'Klient'], inplace=True)
                if df.empty:
                    continue

                df_base = df.copy()
                df_base['Badanie'] = df_base.apply(
                    lambda row: generate_badanie_string(row, include_comparative_word=False), axis=1)

                comparative_mask = (df['Modalność'].isin(['TK', 'MR'])) & (
                    df['Badania do porównania'].fillna('0').astype(str).str.strip()
                    .apply(lambda x: int(float(x)) if x.replace('.', '', 1).lstrip('-').isdigit() else 0) > 0)

                df_comparative_only = df[comparative_mask].copy()
                df_processed = df_base

                if not df_comparative_only.empty:
                    df_comparative_only['Badanie'] = df_comparative_only.apply(
                        lambda row: generate_badanie_string(row, include_comparative_word=True), axis=1)
                    df_processed = pd.concat([df_base, df_comparative_only], ignore_index=True)

                df_processed['Ilość_okolic'] = df_processed['Procedura rozlicz.'].apply(extract_multiplier)
                aggregated_df = (df_processed.groupby(['Klient', 'Badanie'])
                                 .agg(Ilość=('Ilość_okolic', 'sum')).reset_index())
                all_data_to_append.append(aggregated_df)
            except Exception as e:
                print(f"  > BŁĄD podczas przetwarzania {filename}: {e}", flush=True)

    if not all_data_to_append:
        return pd.DataFrame()

    new_data_df = pd.concat(all_data_to_append, ignore_index=True)
    new_data_df = new_data_df.groupby(['Klient', 'Badanie'])['Ilość'].sum().reset_index()
    new_data_df['Data Rozliczenia'] = settlement_date
    return new_data_df[['Data Rozliczenia', 'Klient', 'Badanie', 'Ilość']]
