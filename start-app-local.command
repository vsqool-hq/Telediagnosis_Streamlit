#!/bin/zsh
# Cała aplikacja lokalnie (backend + front) — dwuklik w Finderze.
# Otwiera http://localhost:3000, gdzie liczenie „na tym komputerze" działa bez blokad przeglądarki.
cd "$(dirname "$0")"

# Załaduj nvm, by mieć node/npm w PATH (przy uruchomieniu z Findera .zshrc nie jest wczytywany).
[ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh"

# --- Aktualizacja aplikacji do najnowszej wersji (front + backend jak online) ---
# Front startuje w trybie dev (next dev serwuje bieżący kod źródłowy), więc żeby
# zobaczyć aktualny wygląd wystarczy pobrać najnowsze zmiany z repozytorium.
if [ -d .git ] && command -v git >/dev/null 2>&1; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  echo "Sprawdzam aktualizacje aplikacji (gałąź ${BRANCH})…"
  if git pull --ff-only --quiet 2>/dev/null; then
    echo "✓ Aplikacja zaktualizowana do najnowszej wersji."
    # Doinstaluj ewentualne nowe zależności (szybkie, gdy nic się nie zmieniło).
    ( cd frontend && npm install --no-audit --no-fund >/dev/null 2>&1 ) && echo "✓ Zależności frontu aktualne."
    ( cd backend && source .venv/bin/activate && pip install -q -r requirements.txt >/dev/null 2>&1 ) && echo "✓ Zależności backendu aktualne."
    [ "$BRANCH" != "main" ] && echo "! Uwaga: jesteś na gałęzi '${BRANCH}', a wersja produkcyjna jest na 'main'."
  else
    echo "! Nie udało się automatycznie zaktualizować (lokalne zmiany w plikach albo brak sieci)."
    echo "  Uruchamiam wersję, którą masz lokalnie."
  fi
fi

# Konfiguracja synchronizacji z chmury (opcjonalna, niewersjonowana — patrz sync.env).
# Gdy ustawisz TELEDIAG_SYNC_URL/TELEDIAG_SYNC_TOKEN, lokalny backend pobierze przy
# starcie najnowsze aktywne pliki z chmury (chyba że lokalne są nowsze).
[ -f "./sync.env" ] && source "./sync.env"

echo "Uruchamiam backend (http://localhost:8080)…"
( cd backend && source .venv/bin/activate && \
  export TELEDIAG_DATA_DIR=./data TELEDIAG_SEED_DIR=../seed_data && \
  export TELEDIAG_ALLOW_ANONYMOUS=1 && \
  uvicorn app.main:app --host 127.0.0.1 --port 8080 ) &
BPID=$!

echo "Uruchamiam front (http://localhost:3000)…"
( cd frontend && npm run dev ) &
FPID=$!

trap "kill $BPID $FPID 2>/dev/null" EXIT INT TERM
sleep 6
open http://localhost:3000
echo ""
echo "Aplikacja lokalna: http://localhost:3000"
echo "ZAMKNIJ TO OKNO, aby zatrzymać aplikację."
wait
