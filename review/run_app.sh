#!/usr/bin/env bash
# Start the EXONAUT engine (FastAPI, :8000) and the web app (Next.js, :3000).
# Run from anywhere:  bash review/run_app.sh      Stop with Ctrl-C.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${EXONAUT_VENV:-$HOME/.venvs/lunar-swarm-nav}"

if [ ! -f "$VENV/bin/activate" ]; then
  echo "No virtualenv at $VENV. Create one (outside the repo - the folder name has a colon):"
  echo "  python3 -m venv ~/.venvs/exonaut && source ~/.venvs/exonaut/bin/activate"
  echo "  pip install -r requirements.txt && pip install -e ."
  echo "Then: EXONAUT_VENV=~/.venvs/exonaut bash review/run_app.sh"
  exit 1
fi
source "$VENV/bin/activate"

cd "$ROOT"
python -m uvicorn exonaut.api:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

cd "$ROOT/web"
[ -d node_modules ] || npm install
echo "Engine: http://127.0.0.1:8000/docs   App: http://localhost:3000"
npm run dev
