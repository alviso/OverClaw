#!/usr/bin/env bash
set -e

# ── OverClaw Gateway — Local Setup & Start (macOS) ─────────────────
# Usage: ./start.sh
# Installs all dependencies (if needed) and starts backend + frontend.

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
PID_DIR="$ROOT_DIR/.pids"
LOG_DIR="$ROOT_DIR/.logs"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()  { echo -e "${CYAN}[info]${NC}  $1"; }
ok()    { echo -e "${GREEN}[ok]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $1"; }
fail()  { echo -e "${RED}[fail]${NC}  $1"; exit 1; }

mkdir -p "$PID_DIR" "$LOG_DIR"

# ── 1. Check Homebrew ────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
  warn "Homebrew not found. Installing..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add brew to PATH for Apple Silicon
  if [[ -f /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
fi
ok "Homebrew"

# ── 2. Check Python 3.11+ ───────────────────────────────────────────────
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
    warn "Python $PY_VER found, need 3.11+. Installing..."
    brew install python@3.12
  fi
else
  warn "Python not found. Installing..."
  brew install python@3.12
fi
ok "Python $(python3 --version 2>&1 | awk '{print $2}')"

# ── 3. Check Node.js 18+ ────────────────────────────────────────────────
if command -v node &>/dev/null; then
  NODE_VER=$(node -v | sed 's/v//' | cut -d. -f1)
  if [[ "$NODE_VER" -lt 18 ]]; then
    warn "Node $NODE_VER found, need 18+. Installing..."
    brew install node@20
  fi
else
  warn "Node.js not found. Installing..."
  brew install node@20
fi
ok "Node.js $(node -v)"

# ── 4. Check Yarn ────────────────────────────────────────────────────────
if ! command -v yarn &>/dev/null; then
  info "Installing Yarn..."
  npm install -g yarn
fi
ok "Yarn $(yarn -v)"

# ── 5. Check & Start MongoDB ────────────────────────────────────────────
if ! command -v mongod &>/dev/null && ! brew list mongodb-community &>/dev/null 2>&1; then
  info "Installing MongoDB..."
  brew tap mongodb/brew
  brew install mongodb-community
fi
ok "MongoDB installed"

# Start MongoDB if not already running
if ! pgrep -x mongod &>/dev/null; then
  info "Starting MongoDB..."
  brew services start mongodb-community
  sleep 2
  if ! pgrep -x mongod &>/dev/null; then
    fail "MongoDB failed to start. Try: brew services restart mongodb-community"
  fi
fi
ok "MongoDB running"

# ── 6. Check .env files ─────────────────────────────────────────────────
if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  if [[ -f "$BACKEND_DIR/.env.example" ]]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    warn "Created backend/.env from .env.example — please fill in your API keys!"
    echo ""
    echo -e "  ${YELLOW}Edit $BACKEND_DIR/.env and add:${NC}"
    echo "    OPENAI_API_KEY=sk-..."
    echo "    ANTHROPIC_API_KEY=sk-ant-..."
    echo ""
    fail "Please configure backend/.env and re-run this script."
  else
    fail "backend/.env not found. Create it with OPENAI_API_KEY, ANTHROPIC_API_KEY, MONGO_URL, DB_NAME."
  fi
fi
ok "backend/.env exists"

if [[ ! -f "$FRONTEND_DIR/.env" ]]; then
  echo "REACT_APP_BACKEND_URL=http://localhost:8001" > "$FRONTEND_DIR/.env"
  ok "Created frontend/.env (localhost:8001)"
else
  ok "frontend/.env exists"
fi

# ── 7. Install Backend Dependencies ─────────────────────────────────────
info "Installing backend dependencies..."
cd "$BACKEND_DIR"

# Create venv if not exists
if [[ ! -d "venv" ]]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Install Playwright browser for browse/monitor tools
if ! python3 -c "from playwright.sync_api import sync_playwright" &>/dev/null; then
  info "Installing Playwright Chromium (first time only)..."
  playwright install chromium
fi
ok "Backend dependencies"

# ── 8. Install Frontend Dependencies ─────────────────────────────────────
info "Installing frontend dependencies..."
cd "$FRONTEND_DIR"
yarn install --silent 2>/dev/null
ok "Frontend dependencies"

# ── 9. Stop any existing instances ───────────────────────────────────────
cd "$ROOT_DIR"
if [[ -f "$PID_DIR/backend.pid" ]]; then
  OLD_PID=$(cat "$PID_DIR/backend.pid")
  kill "$OLD_PID" 2>/dev/null && info "Stopped old backend (PID $OLD_PID)" || true
  rm -f "$PID_DIR/backend.pid"
fi
if [[ -f "$PID_DIR/frontend.pid" ]]; then
  OLD_PID=$(cat "$PID_DIR/frontend.pid")
  kill "$OLD_PID" 2>/dev/null && info "Stopped old frontend (PID $OLD_PID)" || true
  rm -f "$PID_DIR/frontend.pid"
fi

# ── 10. Start Backend ───────────────────────────────────────────────────
info "Starting backend..."
cd "$BACKEND_DIR"
source venv/bin/activate
nohup python3 -m uvicorn server:app --host 0.0.0.0 --port 8001 --reload \
  > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PID_DIR/backend.pid"
ok "Backend started (PID $BACKEND_PID) — logs: .logs/backend.log"

# ── 11. Start Frontend ──────────────────────────────────────────────────
info "Starting frontend..."
cd "$FRONTEND_DIR"
nohup yarn start > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$PID_DIR/frontend.pid"
ok "Frontend started (PID $FRONTEND_PID) — logs: .logs/frontend.log"

# ── 12. Wait for services ───────────────────────────────────────────────
cd "$ROOT_DIR"
info "Waiting for services to start..."
sleep 3

# Check backend health
for i in {1..10}; do
  if curl -s http://localhost:8001/api/health &>/dev/null; then
    ok "Backend healthy"
    break
  fi
  if [[ $i -eq 10 ]]; then
    warn "Backend not responding yet — check .logs/backend.log"
  fi
  sleep 1
done

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  OverClaw Gateway — Running${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Dashboard:  ${CYAN}http://localhost:3000${NC}"
echo -e "  Chat:       ${CYAN}http://localhost:3000/chat${NC}"
echo -e "  API:        ${CYAN}http://localhost:8001/api/health${NC}"
echo ""
echo -e "  Logs:       tail -f .logs/backend.log"
echo -e "              tail -f .logs/frontend.log"
echo -e "  Stop:       ${YELLOW}./stop.sh${NC}"
echo ""
