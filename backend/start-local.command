#!/bin/zsh
# Lokalny backend Telediagnosis — dwuklik w Finderze uruchamia liczenie „na tym komputerze".
# (Wymaga jednorazowej instalacji: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt)
cd "$(dirname "$0")"
source .venv/bin/activate
export TELEDIAG_DATA_DIR=./data
export TELEDIAG_SEED_DIR=../seed_data
# Synchronizacja z chmury przy starcie (opcjonalna) — patrz ../sync.env
[ -f "../sync.env" ] && source "../sync.env"
echo "Backend lokalny: http://localhost:8080  (zamknij to okno, by zatrzymać)"
exec uvicorn app.main:app --port 8080
