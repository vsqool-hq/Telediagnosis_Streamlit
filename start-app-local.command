#!/bin/zsh
# Cała aplikacja lokalnie (backend + front) — dwuklik w Finderze.
# Otwiera http://localhost:3000, gdzie liczenie „na tym komputerze" działa bez blokad przeglądarki.
cd "$(dirname "$0")"

# Załaduj nvm, by mieć node/npm w PATH (przy uruchomieniu z Findera .zshrc nie jest wczytywany).
[ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh"

echo "Uruchamiam backend (http://localhost:8080)…"
( cd backend && source .venv/bin/activate && \
  export TELEDIAG_DATA_DIR=./data TELEDIAG_SEED_DIR=../seed_data && \
  uvicorn app.main:app --port 8080 ) &
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
