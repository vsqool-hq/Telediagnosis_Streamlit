# Łatka rozliczenia LEKARZY — Etap 1 + 2 (komplet)

Plik: `lekarze_FULL_etap1_2.patch`
Repo: `vsqool-hq/Telediagnosis_Streamlit`
Status: nakłada się czysto (`git apply --check` OK), kompiluje się, układ przetestowany
syntetycznie (jednostki bez zmian, lekarze z poprawkami). NIE testowane end-to-end na
prawdziwym cenniku lekarzy / bazie — patrz checklista.

## Zmiany (6 punktów, sterowane flagą for_doctor — układ JEDNOSTEK nietknięty)
ETAP 1:
1. billing.py / process_client_data — zapis kolumn „… (oryg.)" przed korektami.
2. doctors.py — raport lekarza używa ORYGINALNYCH kategorii i okolic (zero podciągania)
   + scala „Bardzo pilny" → „Pilny".
3. billing.py — AGGREGATE(9,6,…) → SUBTOTAL(9,…) (Excel PL: SUMY.CZĘŚCIOWE).
ETAP 2 (tylko raport lekarza, flaga for_doctor=True):
4. usunięcie kolumn „… w tym porównawcze".
5. dół: „RAZEM ILOŚĆ OKOLIC" → „GOTOWOŚĆ" + „SUMA" (= RAZEM WARTOŚĆ + GOTOWOŚĆ).
   GOTOWOŚĆ = pole PUSTE do ręcznego wpisania; SUMA liczy się sama (=B(wartość)+B(gotowość)).
6. brak osobnego bloku „Bardzo pilny" (wynik scalenia z pkt 2).

## Nałożenie + push (Twoja strona — patrz uwaga niżej)
```bash
cd <repo Telediagnosis_Streamlit>
git checkout -b claude/vsqool-board-meeting-m5fxyp     # branch deweloperski
git apply lekarze_FULL_etap1_2.patch
python -m py_compile backend/app/engine/billing.py backend/app/engine/doctors.py
git add -A && git commit -m "Rozliczenie lekarzy: bez podciagania; AGGREGATE->SUBTOTAL; bez porownawczych; GOTOWOSC+SUMA"
git push -u origin claude/vsqool-board-meeting-m5fxyp
# po przejściu testów (niżej) — merge do main:
git checkout main && git merge claude/vsqool-board-meeting-m5fxyp && git push origin main
```

## ⚠️ Checklista przed mergem do main (uruchom pipeline dla Bujalskiego 05/2026)
- [ ] TK Onkologia = 71 (było 190)
- [ ] suma wartości badań = 139 055 zł (było 141 755)
- [ ] „Bardzo pilny" (2 bad.) w bloku „Pilny", brak osobnego bloku
- [ ] brak kolumn „… w tym porównawcze" w raporcie lekarza
- [ ] dół: GOTOWOŚĆ (puste) + SUMA; brak „RAZEM ILOŚĆ OKOLIC"
- [ ] sumy „SUMA TK/MR" liczą się w PL Excelu (SUMY.CZĘŚCIOWE), bez #NAZWA?
- [ ] rozliczenia JEDNOSTEK wyglądają jak dotąd (bez zmian)

## Uwaga uboczna
Pliki „Sprawdzony_*.xlsx" i arkusz „Szczegółowe" raportów jednostek będą miały 2
dodatkowe kolumny „… (oryg.)". Nie wpływają na liczby. Mogę dopisać ich ukrycie/usuwanie
przy zapisie jednostek, jeśli przeszkadzają.
