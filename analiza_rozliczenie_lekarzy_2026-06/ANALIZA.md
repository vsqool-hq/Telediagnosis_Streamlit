# Analiza: błąd zawyżenia w rozliczeniu LEKARZY (dr Tomasz Bujalski, 05/2026)

Data analizy: 2026-06-24 · Repo: `vsqool-hq/Telediagnosis_Streamlit` ·
Branch: `claude/vsqool-board-meeting-m5fxyp`

---

## 1. Z czym przyszedł właściciel
Rozliczenie lekarza generowane przez silnik online wygląda na **zawyżone**. Trzeba
porównać wynik silnika z plikiem WZORCOWYM (ręcznie poprawiony, ma „dobre kwoty"),
znaleźć różnice i naprawić silnik. Dodatkowe reguły zgłoszone przez właściciela:
- priorytety mają brać dobrą stawkę: CITO NA RATUNEK / CITO-UDAR / CITO-CITO → stawka CITO;
  Bardzo pilny / Pilny → stawka PILNE;
- funkcja `AGGREGATE` w sumach nie jest rozpoznawana przez polskiego Excela — ma być
  „suma częściowa" (SUBTOTAL / SUMY.CZĘŚCIOWE);
- u lekarzy **nie pokazujemy kolumn „w tym porównawcze"** (nie różnicujemy badań
  porównawczych na inne stawki dla lekarzy);
- na dole zamiast „RAZEM ILOŚĆ OKOLIC" ma być **GOTOWOŚĆ** i poniżej **SUMA**
  (= suma wartości badań + gotowość);
- **u lekarzy NIE MA żadnego podciągania w górę** — ani rodzaju procedury, ani liczby
  okolic; brane jak w oryginale.

## 2. Pliki wejściowe (folder `pliki/`)
- `wejscie_WZORZEC_dr_Bujalski_052026.xlsx` — wzorzec, poprawne kwoty (RAZEM 141 125 zł:
  suma badań 139 055 + GOTOWOŚĆ 1 950 + KOREKTA Matusiak 120). Bez AGGREGATE, bez kolumn
  porównawczych — tak ma wyglądać wynik.
- `wejscie_SILNIK_ONLINE_dr_Bujalski.xlsx` — surowy wynik silnika online (z AGGREGATE,
  kolumnami „w tym porównawcze", osobnym blokiem „Bardzo pilny", „RAZEM ILOŚĆ OKOLIC").

## 3. Co ustaliłem (różnice + przyczyna)
**Kwota:** online liczy sumę badań **141 755 zł** vs wzorzec **139 055 zł** → **+2 700 zł
zawyżenia** — mimo że online ma MNIEJ badań (776 vs 779).

**Przyczyna źródłowa = błędna KATEGORYZACJA (nie stawki):**
- online: TK Onkologia **190**, TK Zwykłe 404; wzorzec: TK Onkologia **71**, TK Zwykłe 551.
- Mechanizm w kodzie: `engine/billing.py` → `find_recommended_procedure_type` wybiera ze
  słownika kategorię o **najwyższym priorytecie** (Onkologia=3 > Angio=2 > Zwykłe=1), a
  `correct_procedure_types` **tylko podbija w górę**. Skutek: jeśli procedura choć raz w
  słowniku wystąpiła jako Onkologia, WSZYSTKIE jej wystąpienia są podbijane.
  Dowód: „tk głowy" w słowniku = 14× Zwykłe + 1× Onkologia → silnik wymusza Onkologię.
- To podciąganie jest CELOWE dla rozliczeń jednostek, ale **przeciekało do raportu
  lekarza**, bo raport lekarza (`engine/doctors.py` → `generate_doctor_billing_files`)
  buduje plik z „plików sprawdzonych", które mają już podbite kategorie.
- Dowód niezależny (ICD10): ze 190 „TK Onkologia" w online tylko 24 miały kod nowotworowy
  (C…/D…); reszta to m.in. udary (I64), urazy (S00), padaczka (G40) — czyli błędnie
  zakwalifikowane jako onkologia.

**Drobne:** „Bardzo pilny" (2 badania) — w online osobny blok; ma być rozliczany jak Pilny.

## 4. Co zrobiłem (łatka — w repo na tym branchu)
Commit `3c1e5d7`. Pliki zmienione: `backend/app/engine/billing.py`, `.../doctors.py`.
Łatka też jako `lekarze_FULL_etap1_2.patch` (w tym folderze). 6 zmian, sterowane flagą
`for_doctor` — **układ rozliczeń JEDNOSTEK nietknięty**:

ETAP 1
1. `billing.process_client_data` — zapis kolumn `… (oryg.)` przed korektami.
2. `doctors.generate_doctor_billing_files` — raport lekarza używa ORYGINALNYCH kategorii
   i liczby okolic (zero podciągania) + scala „Bardzo pilny" → „Pilny".
3. `AGGREGATE(9,6,…)` → `SUBTOTAL(9,…)` (Excel PL: SUMY.CZĘŚCIOWE).

ETAP 2 (tylko raport lekarza, `for_doctor=True`)
4. usunięcie kolumn „… w tym porównawcze".
5. dół: „RAZEM ILOŚĆ OKOLIC" → „GOTOWOŚĆ" (puste, ręcznie) + „SUMA" (= wartości + gotowość).
6. brak osobnego bloku „Bardzo pilny".

Weryfikacja: `git apply --check` OK, `py_compile` OK, test syntetyczny układu OK
(jednostki bez zmian, lekarze z poprawkami).

## 5. Co zaproponowałem / stan otwarty
- **Przed mergem do `main`**: przebieg pipeline'u dla Bujalskiego i sprawdzenie
  **suma badań = 139 055 zł** oraz **TK Onkologia = 71**. Pełna checklista w
  `INSTRUKCJA_etap1_2.md`.
- **GOTOWOŚĆ**: zrobiona jako PUSTE pole do ręcznego wpisania (SUMA liczy się sama).
  Do decyzji: czy ma być liczona automatycznie (we wzorcu 13 × 150 + KOREKTA 120).
- **Uwaga uboczna**: pliki „Sprawdzony_*.xlsx" i Szczegółowe jednostek zyskają 2 kolumny
  „… (oryg.)" — bez wpływu na liczby; do ewentualnego ukrycia.
- Nie zmergowano do `main` — czeka na test na żywych danych (kod fakturujący).

## 6. Pliki w tym folderze
```
analiza_rozliczenie_lekarzy_2026-06/
├── ANALIZA.md                      # ten dokument
├── INSTRUKCJA_etap1_2.md           # jak nałożyć + checklista testów
├── lekarze_FULL_etap1_2.patch      # łatka (już wniesiona commitem 3c1e5d7 na branchu)
└── pliki/
    ├── wejscie_WZORZEC_dr_Bujalski_052026.xlsx
    └── wejscie_SILNIK_ONLINE_dr_Bujalski.xlsx
```
