#!/usr/bin/env bash

# ── OverClaw Gateway — Stop All Services ───────────────────────────

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$ROOT_DIR/.pids"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

stopped=0

for service in backend frontend; do
  pidfile="$PID_DIR/$service.pid"
  if [[ -f "$pidfile" ]]; then
    PID=$(cat "$pidfile")
    if kill "$PID" 2>/dev/null; then
      echo -e "${GREEN}[ok]${NC}    Stopped $service (PID $PID)"
      ((stopped++))
    else
      echo -e "${CYAN}[info]${NC}  $service (PID $PID) was not running"
    fi
    rm -f "$pidfile"
  fi
done

# Also kill any stray uvicorn/node processes for this project
pkill -f "uvicorn server:app.*--port 8001" 2>/dev/null && ((stopped++)) || true
pkill -f "react-scripts start" 2>/dev/null && ((stopped++)) || true

if [[ $stopped -eq 0 ]]; then
  echo -e "${CYAN}[info]${NC}  No services were running"
else
  echo -e "${GREEN}[ok]${NC}    All services stopped"
fi

echo ""
echo -e "  MongoDB is still running (managed by brew services)."
echo -e "  To stop it: ${RED}brew services stop mongodb-community${NC}"
echo ""
