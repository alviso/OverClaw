<p align="center">
  <img src="assets/overclaw-banner.png" alt="OverClaw Banner" width="100%"/>
</p>

# OverClaw

A workplace AI assistant built from the ground up, inspired by [OpenClaw](https://github.com/openclaw/openclaw)'s architecture. OverClaw uses a multi-agent system — one orchestrator delegating to specialist agents — to handle the tasks that eat up your team's day: triaging email, researching competitors, drafting reports, building internal tools, and keeping Slack organized. Built for teams that want an always-on coworker, not another chatbot.

## Demo

<!-- Replace with your recording: a short clip of the chat delegating to the developer agent and the project appearing in the Workspace dashboard -->
![Demo](demo.gif)

*Coming soon — screen recording of the orchestrator delegating a "build me a todo app" request to the developer agent, with live project preview.*

---

## Motivation

OpenClaw is a ~270k LOC TypeScript monorepo implementing a personal AI assistant with an elegant **Gateway pattern**: a WebSocket control plane sitting between messaging channels and an agent runtime. It's impressive, but it's also complex — channel plugins alone account for 69k LOC.

This project asks: **what would it look like to reimplement the core architecture from scratch, in Python, optimized for a small team's workplace use?**

The goals were:

1. **Preserve the architecture** — the Gateway pattern, channel abstraction, routing, tool policy, and multi-agent delegation are genuinely good ideas
2. **Cut the bloat** — no mobile apps, no 15 channel plugins, no CLI surface; just the subsystems that matter for a workplace assistant
3. **Add developer capabilities** — the agent can create software projects, manage processes, and even write its own tools at runtime
4. **Stay deployable** — one `docker compose up` or one `./start.sh` on a Mac

The result is a ~5k LOC Python/React application that covers the same architectural surface as OpenClaw's core, with a few additions (workspace, process management, runtime tool creation) that OpenClaw doesn't have.

---

## What It Can Do

| Capability | How |
|---|---|
| **Web browsing** | Playwright-powered interactive browser (navigate, click, fill forms, screenshot) |
| **Email** | Gmail OAuth integration — search, read, summarize threads |
| **Research** | Web search + page scraping + HTTP requests |
| **Code & deploy** | Write projects, install deps, run them as managed processes with live preview |
| **Self-extending** | Create new tools at runtime (Python code → registered tool) |
| **Memory** | Long-term RAG with OpenAI embeddings, cosine similarity search |
| **User profiling** | Passively learns your name, role, preferences, and communication style from conversations |
| **Relationship map** | Automatically discovers people you mention and builds a network of names, roles, and context |
| **Scheduled tasks** | Cron-like agent turns with change-detection notifications |
| **Slack** | Socket Mode bidirectional messaging |
| **Monitoring** | URL monitoring with screenshot diffing and alerting |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│  ┌───────────┐  ┌──────────────────────────────────────────────┐ │
│  │  WebChat   │  │           Admin Dashboard                    │ │
│  │  (/, /chat)│  │  /admin: Overview · Agents · Workspace ·    │ │
│  │            │  │  Skills · Memory · Tasks · Gmail · Slack     │ │
│  └─────┬─────┘  └──────────────────┬───────────────────────────┘ │
│        │       WebSocket JSON-RPC  │                             │
└────────┼───────────────────────────┼─────────────────────────────┘
         │                           │
┌────────┴───────────────────────────┴─────────────────────────────┐
│                    Gateway (FastAPI + WebSocket)                   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Method Router                             │ │
│  │  health.get · config.set · chat.send · workspace.projects   │ │
│  │  sessions.list · agents.* · skills.* · tasks.* · ...        │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                              │                                    │
│  ┌───────────────────────────┴──────────────────────────────────┐│
│  │                     Agent Runtime                             ││
│  │                                                               ││
│  │  ┌─────────────┐    delegate     ┌────────────────────────┐  ││
│  │  │ Orchestrator │──────────────→  │    Specialist Agents   │  ││
│  │  │              │                 │                        │  ││
│  │  │  Plans,      │  ┌──────────┐   │  browser   — Playwright│  ││
│  │  │  delegates,  │  │ Routing  │   │  gmail     — OAuth API │  ││
│  │  │  synthesizes │  │ Layer    │   │  research  — Web search│  ││
│  │  │              │  └──────────┘   │  system    — Shell/FS  │  ││
│  │  └──────────────┘                 │  developer — Code/Run  │  ││
│  │                                   └────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────┐ ││
│  │  │                    Tool Framework                         │ ││
│  │  │  20+ tools · per-agent allowlists · OpenAI & Anthropic   │ ││
│  │  │  format adapters · runtime tool creation via exec()       │ ││
│  │  └──────────────────────────────────────────────────────────┘ ││
│  └───────────────────────────────────────────────────────────────┘│
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌────────────────┐  │
│  │ Scheduler│  │  Memory  │  │ Channels  │  │ Workspace Mgr  │  │
│  │ (cron)   │  │  (RAG)   │  │ (Slack)   │  │ (projects,     │  │
│  │          │  │          │  │           │  │  processes,     │  │
│  │          │  │          │  │           │  │  reverse proxy) │  │
│  └──────────┘  └──────────┘  └───────────┘  └────────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                     MongoDB                                   │ │
│  │  sessions · chat_messages · agents · skills · memories ·      │ │
│  │  tasks · notifications · gateway_config · gmail_tokens        │ │
│  └──────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

**Gateway pattern (from OpenClaw).** A single WebSocket connection carries all control-plane traffic using JSON-RPC 2.0. The frontend calls `rpc("chat.send", { text })` the same way it calls `rpc("workspace.projects")` — one transport, one auth model, one reconnection handler.

**Top-down orchestration.** The orchestrator agent is the only agent that talks to the user. It decides which specialist to delegate to, passes full context (specialists have no conversation history), and synthesizes the result. This prevents tool sprawl in a single prompt and keeps each specialist focused.

**Tool allowlists.** Each agent has an explicit `tools_allowed` list. The browser agent can't write files; the developer agent can't browse the web. This is OpenClaw's tool-policy concept, simplified to a flat allowlist per agent.

**Runtime tool creation.** The developer agent can write Python code that gets `exec()`'d and registered as a new tool. This is intentionally powerful — it means the system can extend itself. Tool definitions are persisted in MongoDB and reloaded on restart.

**Process persistence.** Running workspace processes are tracked in a JSON sidecar file. On server restart, the system re-discovers alive PIDs and reattaches them to the UI — no orphaned processes.

**Reverse proxy.** Workspace web apps are exposed via `/api/preview/{port}/` rather than requiring direct port access. The developer agent is prompted to use relative URLs so apps work transparently behind this proxy.

---

## Project Structure

```
├── backend/
│   ├── server.py                      # FastAPI app, startup, WebSocket handler, reverse proxy
│   ├── gateway/
│   │   ├── agent.py                   # AgentRunner: LLM provider abstraction, tool-calling loops
│   │   ├── agents_config.py           # Orchestrator + specialist agent definitions
│   │   ├── auth.py                    # Token-based gateway authentication
│   │   ├── config_schema.py           # Pydantic config model (validated, stored in MongoDB)
│   │   ├── memory.py                  # Embedding-based long-term memory (RAG)
│   │   ├── user_profile.py            # Passive user preference extraction
│   │   ├── relationship_memory.py     # People/relationship discovery from conversations
│   │   ├── setup.py                   # First-run setup wizard backend
│   │   ├── methods.py                 # JSON-RPC method registry and handlers
│   │   ├── notifications.py           # Notification manager (WebSocket + persistence)
│   │   ├── protocol.py                # JSON-RPC 2.0 message helpers
│   │   ├── routing.py                 # Session → agent routing (pattern matching)
│   │   ├── scheduler.py               # Background task scheduler (cron-like)
│   │   ├── skills.py                  # Skill injection into agent prompts
│   │   ├── ws_manager.py              # WebSocket connection tracking
│   │   ├── gmail.py                   # Gmail OAuth flow + API wrapper
│   │   ├── channels/
│   │   │   └── slack_channel.py       # Slack Socket Mode adapter
│   │   └── tools/
│   │       ├── __init__.py            # Tool base class, registry, policy engine
│   │       ├── browser_use.py         # Interactive browser (playwright + browser-use)
│   │       ├── create_tool.py         # Runtime tool creation (meta-tool)
│   │       ├── delegate.py            # Agent-to-agent delegation
│   │       ├── developer_tools.py     # File ops, process management for workspace
│   │       ├── execute_command.py      # Shell command execution
│   │       ├── file_ops.py            # Read/write/list/patch files
│   │       ├── gmail.py               # Gmail search/read tool
│   │       ├── http_request.py        # Generic HTTP client tool
│   │       ├── memory_search.py       # Memory query tool
│   │       ├── monitor.py             # URL monitoring with screenshot diffing
│   │       ├── process_manager.py     # Process lifecycle + persistence
│   │       ├── vision.py              # Image analysis (GPT-4o vision)
│   │       ├── audio_transcribe.py    # Audio transcription (Whisper)
│   │       ├── document_parse.py      # PDF/DOCX parsing
│   │       └── web_search.py          # DuckDuckGo web search
│   └── requirements.txt
│
├── frontend/
│   └── src/
│       ├── App.js                     # Router: / (chat), /admin/* (dashboard)
│       ├── hooks/useGatewayWs.js      # WebSocket hook (connect, auth, rpc, reconnect)
│       ├── pages/ChatPage.js          # Chat interface
│       └── components/
│           ├── chat/                  # ChatView, SessionSidebar
│           ├── dashboard/             # All admin panels (15 components)
│           │   ├── WorkspacePanel.js  # Project dashboard (mini-Heroku)
│           │   ├── AgentManager.js    # Agent CRUD
│           │   ├── MemoryPanel.js     # Memory browser
│           │   └── ...
│           └── layout/                # DashboardLayout (sidebar + header)
│
├── workspace/                         # Agent-created projects live here (gitignored)
├── docker-compose.yml                 # MongoDB + app (production)
├── Dockerfile                         # Multi-stage: frontend build → Python + nginx
├── start.sh                           # Local dev setup (macOS): installs everything, starts services
└── stop.sh                            # Stops local services
```

---

## How It Maps to OpenClaw

| OpenClaw Subsystem | LOC | OverClaw Equivalent | Notes |
|---|---|---|---|
| Gateway (control plane) | 26,860 | `server.py` + `methods.py` + `protocol.py` + `ws_manager.py` | Same JSON-RPC-over-WebSocket pattern, ~600 LOC |
| Agent Runtime | 48,277 | `agent.py` (~460 LOC) | OpenAI + Anthropic with native tool calling. No model manager abstraction — just a provider map |
| Channel Abstraction | 9,373 | `channels/slack_channel.py` (~200 LOC) | One channel vs. OpenClaw's 8. Same interface pattern |
| Extensions (channel plugins) | 68,909 | — | Cut entirely. Slack only |
| Tool System | (in Agents) | `tools/` (~2k LOC, 20 tools) | Same concept: registry + per-agent policy. Added `create_tool` for self-extension |
| Memory / RAG | 7,236 | `memory.py` (~215 LOC) | OpenAI embeddings + cosine similarity in MongoDB vs. sqlite-vec |
| Routing & Sessions | 1,063 | `routing.py` (~40 LOC) | Same fnmatch pattern matching, simplified from 5-level priority |
| Skills Platform | (in Plugins) | `skills.py` | Prompt-injected capabilities, stored in MongoDB |
| Config System | 15,887 | `config_schema.py` | Pydantic model vs. Zod schema. Same concept |
| CLI | 21,335 | — | Cut. Dashboard-only management |
| Web UI | 25,997 | `frontend/` (~3k LOC) | React + Tailwind + shadcn/ui vs. Lit components |
| Browser Control | 11,012 | `browser_use.py` (~550 LOC) | Uses `browser-use` library instead of raw Playwright scripting |
| **Total** | **~270k** | **~5k** | |

---

## Setup

### Option 1: Docker Compose (recommended)

```bash
git clone https://github.com/your-username/overclaw.git && cd overclaw
docker compose up -d
```

Open [http://localhost:3000](http://localhost:3000). On first launch, a **setup wizard** walks you through entering your API keys (Anthropic, OpenAI, gateway token). Keys are stored in the database and persist across container restarts — no need to edit `.env` files.

Alternatively, you can pre-configure keys before building:

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your keys
docker compose up -d
```

### Option 2: Local Development (macOS)

```bash
git clone https://github.com/your-username/overclaw.git && cd overclaw

# Configure API keys
cp backend/.env.example backend/.env
# Edit backend/.env — add OPENAI_API_KEY and ANTHROPIC_API_KEY

./start.sh
```

The script handles everything: Homebrew, Python 3.11+, Node 20, Yarn, MongoDB, virtualenv, pip, yarn install, Playwright Chromium. It's idempotent — safe to run multiple times.

```bash
./stop.sh          # Stop services (MongoDB stays running)
tail -f .logs/backend.log   # Backend logs
tail -f .logs/frontend.log  # Frontend logs
```

### Option 3: Manual Setup

```bash
# Terminal 1: MongoDB
mongod --dbpath /tmp/mongo-data

# Terminal 2: Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env  # Edit with your keys
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Terminal 3: Frontend
cd frontend
echo "REACT_APP_BACKEND_URL=http://localhost:8001" > .env
yarn install && yarn start
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key (GPT-4o for agents, embeddings for memory) |
| `ANTHROPIC_API_KEY` | No | Anthropic API key (enables Claude model selection) |
| `MONGO_URL` | Yes | MongoDB connection string |
| `DB_NAME` | Yes | Database name (default: `overclaw`) |
| `GATEWAY_TOKEN` | No | Auth token for WebSocket connections (open if unset) |
| `GOOGLE_CLIENT_ID` | No | For Gmail OAuth integration |
| `GOOGLE_CLIENT_SECRET` | No | For Gmail OAuth integration |

Slack tokens are configured via the dashboard wizard at `/admin/slack` — not in `.env`.

---

## Usage

### Chat (`/`)

The main interface. Type a message and the orchestrator decides how to handle it:

- *"Search for recent news about..."* → delegates to the research agent
- *"Check my email for..."* → delegates to the Gmail agent  
- *"Build me a todo app"* → delegates to the developer agent, which writes code, installs deps, and starts it
- *"Go to example.com and..."* → delegates to the browser agent

### Admin Dashboard (`/admin`)

| Page | What it does |
|---|---|
| **Overview** | System health, connected clients, channel status, recent activity |
| **Agents** | View/edit specialist agents, their prompts, models, and tool allowlists |
| **Workspace** | Project dashboard — see all agent-created projects, run/stop/preview them |
| **Skills** | Inject custom instructions into agent prompts (like OpenClaw's skills) |
| **Memory** | Browse long-term memory entries, search by similarity |
| **People** | View discovered relationships — names, roles, teams, and context from conversations |
| **Tasks** | Create scheduled agent tasks (e.g., "check this URL every 30s") |
| **Notifications** | View alerts from scheduled tasks and monitors |
| **Gmail** | Connect/disconnect Gmail OAuth |
| **Slack** | Configure Slack Socket Mode tokens |
| **Config** | View gateway configuration, switch LLM models |

### Workspace Projects

When the developer agent builds something, it appears in the Workspace dashboard:

1. Agent creates project files under `workspace/projects/<name>/`
2. Project card appears in the dashboard with detected type (Python/Node), entry point, file count
3. Click **Install Deps** to create a virtualenv and install `requirements.txt`
4. Click **Run** to start the project (with optional port override)
5. Click **Preview** to open it via the reverse proxy at `/api/preview/{port}/`
6. Running projects show live log streaming

---

## Security Considerations

This is a **personal/workplace tool**, not a public SaaS. The security model reflects that:

- **`exec()` for tool creation**: The developer agent can write arbitrary Python that gets executed. This is the point — it's a power-user feature. Don't expose the gateway to untrusted users.
- **Shell access**: The `execute_command` tool runs shell commands. Same caveat.
- **Gateway token**: Set `GATEWAY_TOKEN` in `.env` to require authentication on WebSocket connections. Without it, the gateway is open.
- **No user system**: There's one operator. If you need multi-tenancy, this isn't the right tool.
- **API keys**: All secrets live in `backend/.env`, which is gitignored. The `.env.example` contains only placeholders.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Motor (async MongoDB), WebSocket |
| Frontend | React 19, Tailwind CSS, shadcn/ui, react-router |
| Database | MongoDB 7 |
| LLM | OpenAI GPT-4o (default), Anthropic Claude (configurable per agent) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Browser | Playwright + `browser-use` library |
| Slack | `slack-bolt` (Socket Mode) |
| Deployment | Docker (nginx + uvicorn) or native macOS |

---

## License

MIT
