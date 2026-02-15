# OverClaw — Product Requirements Document

## Problem Statement
Build a streamlined work assistant (inspired by OpenClaw, rebranded as OverClaw) with a top-down orchestration architecture. A primary "Orchestrator" agent delegates tasks to specialist agents (Gmail, browser, developer, research, system). The developer agent can create its own tools and manage files within a dedicated, persistent workspace at `/app/workspace`.

## Architecture
- **Backend**: FastAPI + WebSocket JSON-RPC + MongoDB + Slack Socket Mode
- **Frontend**: React chat-centric UI + admin dashboard
- **Agents**: Orchestrator → Specialist delegation (OpenAI GPT-4o)
- **Workspace**: Persistent `/app/workspace/projects/` for agent-created projects

## What's Been Implemented

### Core Platform
- Orchestrator agent with specialist delegation (browser, gmail, research, system, developer)
- WebSocket JSON-RPC protocol for real-time communication
- MongoDB for config, sessions, agents, skills, memory, tasks, notifications
- Slack Socket Mode integration with health check loop
- Admin dashboard with Overview, Agents, Skills, Memory, Tasks, Notifications, Gmail, Slack, Config pages

### Project Dashboard (Feb 15, 2026) — Central Workspace View
Replaced the old tab-based Workspace Explorer (Files/Processes/Custom Tools) with a mini-Heroku dashboard:
- **Project cards grid**: Each project shows name, type badge (Python/Node), entry point, last modified, file count
- **Live status**: Green pulsing dot = running, gray = stopped. Cross-references process registry in real-time (polls every 5s)
- **Quick actions per card**: Files, Run, Stop, Preview (with port), Setup (install deps)
- **Drill-down**: Clicking a project opens `ProjectDetail` with integrated file browser + header controls (Run/Stop/Preview/Logs)
- **Terminal view**: Live-streaming process logs accessible from running project detail
- **Custom tools**: Collapsible section at bottom (only visible when tools exist)
- **Backend RPC**: `workspace.projects` scans `/app/workspace/projects/`, detects type, cross-references `_processes` dict

### Run Project & Install Deps
- **"Run Project"**: Auto-detects project type, suggests command, optional port override (injects PORT env var)
- **"Install Deps"**: Creates venv + pip install for Python, npm install for Node
- **Port detection**: Scans source code for port patterns including `os.environ.get('PORT', N)`

### Process Persistence
- Metadata persisted to `/app/workspace/.processes.json` on start/stop/exit
- On server restart, `recover_processes()` re-discovers alive PIDs, re-attaches to UI
- Recovered processes stoppable via direct PID kill

### Developer Agent Prompt
- Correct relative paths: explicit WRONG/RIGHT examples to prevent `/workspace/workspace/` duplication
- Always create `requirements.txt` for Python projects
- Always use relative URLs in HTML/JS (no leading `/`) for reverse proxy compatibility
- Always read port from `PORT` env var with fallback

### Reverse Proxy
- `/api/preview/{port}/` exposes running apps with trailing-slash redirect for relative URL support

## Pending Issues
- **P2**: Webchat not in sync with Slack conversations (session_id mismatch)

## Completed (Feb 16, 2026) — Banner Image
- Generated OverClaw banner image (red crayfish mascot, black background, bold OVER/CLAW typography) inspired by OpenClaw's banner style
- Cropped to remove dead space (896px→466px tall), saved to `/app/assets/overclaw-banner.png`
- Updated README.md with centered banner referencing local asset path

## Completed (Feb 16, 2026) — Relationship Memory + README Review
- New module: `gateway/relationship_memory.py` — passively extracts people (name, role, team, relationship, context) from conversations
- Stores in MongoDB `relationships` collection with upsert semantics, keeps last 5 context notes per person
- Relationship context injected into orchestrator system prompt alongside user profile and memories
- New admin panel: `/admin/people` — "Discovered Relationships" view with cards grouped by relationship type (manager, report, peer, colleague, etc.)
- Color-coded cards with mention counts, last-seen times, and latest context
- Added `relationships.list` RPC method for the admin panel
- Updated sidebar navigation with "People" entry (Users icon)
- README updated: setup wizard mentions, user profiling & relationship map in capabilities table, People in admin dashboard table, new files in project structure, architecture diagram updated, env vars section clarified

## Completed (Feb 16, 2026) — Webchat/Slack Sync (P1) + Slack Regression Prep (P2)
- Backend now broadcasts `chat.event` to all WebSocket clients when Slack messages arrive and when the agent responds to Slack
- ChatView listens for `chat.event` via `onEvent`/`offEvent` and triggers immediate message refresh (no waiting for 2s poll)
- SessionSidebar distinguishes Slack sessions from webchat sessions: green `#` icon + "Slack" label vs blue chat icon
- Slack session IDs parsed for friendly display (channel suffix instead of raw `slack:C06ABCD:U01XYZ`)
- Cross-channel viewing works: clicking a Slack session in webchat shows full conversation history

## Completed (Feb 16, 2026) — Onboarding Setup Wizard
- Web-based setup wizard shown on first launch when API keys are missing or placeholder
- Multi-step flow: Welcome → LLM Keys (Anthropic/OpenAI) → Gateway Security Token → Optional Integrations (Gmail, Slack)
- Each field has clear descriptions explaining what it is and why it's needed, with links to provider dashboards
- Keys stored in MongoDB `setup_secrets` collection (persists across Docker container restarts)
- Keys loaded into `os.environ` at startup via `load_secrets_to_env()` for immediate effect
- Gateway token saved to localStorage for WebSocket auth; page reloads after wizard completes
- Backend endpoints: `GET /api/setup/status`, `POST /api/setup/save`
- New files: `backend/gateway/setup.py`, `frontend/src/components/setup/SetupWizard.js`

## Completed (Feb 16, 2026) — User Profile (Passive Extraction)
- New module: `gateway/user_profile.py` — passively extracts personal facts from user messages using Anthropic Claude Haiku (fire-and-forget, background task)
- Facts stored in MongoDB `user_profiles` collection with upsert semantics (new facts merge, same keys update)
- Profile context injected into orchestrator's system prompt before each turn
- Categories: name, role, company, communication style, recurring events, projects, tools, timezone, people
- Admin RPC method `profile.get` for debugging
- No UI needed — fully automatic and seamless

## Completed (Feb 15, 2026) — Open Source Prep
- Comprehensive README.md with motivation, architecture diagram, OpenClaw comparison table, setup instructions (Docker/macOS/manual), usage guide, security considerations
- **Security audit**: removed `backend/.env` and `frontend/.env` from git tracking (contained real API keys); cleaned up `.gitignore` (removed duplicates, malformed entries); updated `.env.example` with all current vars
- **Code fix**: bare `except:` → `except Exception:` in `browser_use.py`

## Backlog
- P2: Guide user through local setup (install_local.sh, run_local.sh)
- P3: Full regression test of Slack integration
- P3: Interactive browser agent on KVM site (on hold)
