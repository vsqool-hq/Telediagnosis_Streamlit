# Automatyzator Rozliczeń Medycznych — wersja webowa

Aplikacja webowa do weryfikacji i rozliczania badań medycznych. Następca panelu
desktopowego (`main_app.py`) i prototypu Streamlit. Silnik obliczeniowy
(`backend.py`) został przeniesiony 1:1 — z tą różnicą, że wcześniej zahardkodowane
wartości są teraz edytowalne z panelu **Ustawienia**.

## Architektura

```
┌──────────────────────┐        HTTPS / SSE        ┌────────────────────────────┐
│  Frontend (Next.js)  │  ───────────────────────► │  Backend (FastAPI)         │
│  Vercel — zawsze on   │                            │  Fly.io — scale-to-zero    │
│  pulpit, wykresy,     │  ◄─────────────────────── │  API + silnik (4 vCPU)     │
│  upload, ustawienia   │       JSON / pliki         │  SQLite + wolumen /data    │
└──────────────────────┘                            └────────────────────────────┘
```

- **Frontend** — Next.js 14 + TypeScript + Tailwind + Recharts. Hostowany na Vercel
  (statyczny, zawsze natychmiastowy). Każdy kolejny moduł = nowa strona w `app/`.
- **Backend** — FastAPI. Przeliczenia uruchamiane w osobnym procesie
  (`app/run_job.py`), więc `multiprocessing` nie koliduje z serwerem, a logi lecą
  na żywo (SSE). Hostowany na Fly.io ze scale-to-zero: maszyna 4 vCPU / 8 GB budzi
  się na żądanie i usypia po bezczynności.
- **Dane** — SQLite + katalogi na wolumenie `/data` (historia zadań, wersje plików
  wzorcowych i cennika, ustawienia). Bez osobnej bazy i object storage — dla
  jednego użytkownika to zbędny koszt.

## Funkcje

- **Rozliczenie** — wgranie pliku jednostek, pełny proces lub „tylko braki wzorca",
  logi na żywo, pobranie wyników (ZIP lub pojedyncze pliki).
- **Pliki wzorcowe / Cennik** — wersjonowanie: wgrywanie wielu wersji i wskazanie
  aktywnej, używanej przy rozliczeniach.
- **Ustawienia** — edycja konfiguracji silnika (priorytety, mapy sufiksów, słowa
  kluczowe MR, kolory raportu, liczba rdzeni).
- **Pulpit** — statystyki i wykresy z ostatniego rozliczenia.
- **Historia** — lista wszystkich zadań ze statusem i pobieraniem wyników.

## Uruchomienie lokalne

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export TELEDIAG_DATA_DIR=./data          # lokalny katalog danych
export TELEDIAG_SEED_DIR=../seed_data     # przykładowe pliki startowe
uvicorn app.main:app --reload --port 8080
```

### Frontend
```bash
cd frontend
cp .env.example .env.local                # ustaw NEXT_PUBLIC_API_BASE=http://localhost:8080
npm install
npm run dev                               # http://localhost:3000
```

## Wdrożenie produkcyjne

### Backend → Fly.io (scale-to-zero)
```bash
fly launch --no-deploy                    # użyje istniejącego fly.toml i Dockerfile
fly volumes create teledag_data --size 3 --region waw
fly secrets set TELEDIAG_API_TOKEN=<długi-losowy-token>   # ochrona API (zalecane)
fly secrets set TELEDIAG_CORS_ORIGINS=https://<twoj-front>.vercel.app
fly deploy
```

### Frontend → Vercel
1. Zaimportuj repozytorium w Vercel, ustaw **Root Directory = `frontend`**.
2. Zmienne środowiskowe:
   - `NEXT_PUBLIC_API_BASE` = `https://<twoja-app>.fly.dev`
   - `NEXT_PUBLIC_API_TOKEN` = ten sam token co w backendzie (jeśli ustawiony)
3. Deploy.

## Koszt orientacyjny (1 użytkownik)
~150–400 zł/rok: Vercel (front) darmo, Fly.io płatność za faktyczne minuty
liczenia (scale-to-zero), SQLite na wolumenie. Po dłuższej przerwie pierwsze
odwołanie do backendu „budzi" maszynę (~5–20 s) — bez wpływu na wygląd ani
szybkość samych obliczeń.

## Dane startowe
Katalog `seed_data/` zawiera przykładowy słownik i cennik. Przy pierwszym
uruchomieniu (gdy baza jest pusta) zostają zaimportowane jako pierwsza aktywna
wersja. Później wszystko zarządzane jest z poziomu aplikacji.
