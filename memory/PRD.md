# OverClaw — PRD

## Problem Statement
Build a streamlined work assistant, "OverClaw", with an orchestration architecture where a primary agent delegates tasks to specialists. The project should be open-source-ready with intelligence features for learning about the user and their work context.

## Core Architecture
- **Backend**: FastAPI + MongoDB
- **Frontend**: React
- **Agent**: LLM-powered orchestrator with specialist delegation
- **Channels**: Webchat, Slack
- **Integrations**: Gmail, Microsoft Outlook (scaffolded), Slack

## What's Been Implemented

### Core Intelligence
- Passive User Profile extraction from conversations
- Relationship Memory — auto-discovers org chart from conversations and emails
- Email Memory — RAG pipeline that indexes email content for searchable context
- Multi-pass deduplication for people (name, email, accent normalization)
- Proactive Context Awareness — agent auto cross-references email/calendar for time-sensitive events

### Scheduled Tasks
- **Email Triage Task** (5 min interval): 3-tier email classification
  - Category A (Important): Read + index + Slack notify
  - Category B (Notifications): Read + index silently
  - Category C (Promotional): Skip entirely
- `slack_notify` tool for proactive Slack messaging (auto-targets last active conversation)

### Configuration & Management
- Onboarding Wizard (`/admin/setup`)
- Credentials Editor (`/admin/config`)
- Brain Export/Import (`/admin/brain`)
- People Management (`/admin/people`) with merge, delete, inline email editing
- Tasks UI (`/admin/tasks`)

### Integrations
- Gmail: Fully functional
- Microsoft Outlook: Scaffolded, untested
- Slack: Connected with proactive notification support

### Content Generation
- Custom HTML proposal endpoint (`/api/proposals/proposal-cvs-overclaw.html`)

## Key API Endpoints
- `POST /api/brain/export` / `POST /api/brain/import`
- `POST /api/people/merge` / `DELETE /api/people/{id}` / `PATCH /api/people/{id}`
- `GET /api/proposals/proposal-cvs-overclaw.html`
- RPC: `people.list`, `people.merge`, `people.delete`
- RPC: `workspace.cleanup_processes` (new — prune dead process entries)

## DB Schema
- **relationships**: `{ name, name_key, email_address, role, team, relationship, mention_count, context_history, aliases, last_seen }`
- **settings**: `{ key, value }` — includes `slack_last_active_channel`
- **tasks**: `{ id, name, prompt, interval_seconds, enabled, ... }`
- **setup_secrets**: `{ _id: "main", openai_api_key, anthropic_api_key, gateway_token, ... }`

## Completed — Conversation Context Fix (Feb 2026)
- **Root Cause**: `agent.py` was reconstructing LLM history using only `role` and `content`, completely dropping `tool_calls` data. This meant the LLM had no memory of what tools it used or what they returned in previous turns.
- **Fix**: When building `llm_messages` from history, assistant messages with `tool_calls` now include a `[Tools used: ...]` summary with tool names, args, and results. The LLM can now correctly answer follow-up questions about its own actions.
- **Impact**: Fixes the exact bug where "what kind of snag?" about a failed browser_use tool got an unrelated response about email/Slack notifications.

## Completed — Mindmap Feature (Feb 2026)
- **Mindmap Page** (`/admin/mindmap`): Interactive force-directed graph visualization of user's cognitive landscape
- **LLM-Powered Clustering**: Auto-generates topic nodes (work streams, projects, efforts) from memories, relationships, and conversation data
- **People as Participants**: People appear as secondary nodes connected to the topics they're involved in
- **Importance Feedback**: Users can mark topic importance (high/medium/low) — persisted to DB and reflected visually with ring colors
- **Data-testid Coverage**: All interactive elements have test IDs for automation

## Completed — P0 Stability Fixes (Feb 2026)
- **Unified Secret Loading**: `setup.py` refactored with `_ENV_ONLY_FIELDS` to prevent `gateway_token` from being silently overridden by DB values
- **Auth Logic Simplified**: `.env` is now the single source of truth for `GATEWAY_TOKEN`; DB values for this field are skipped during startup loading
- **Process Manager Resilience**: Added `_is_pid_alive()` liveness checks, `cleanup_dead_processes()` for registry pruning, auto-cleanup of zombie entries when starting same-name processes
- **DB_NAME Fallback Fix**: Removed hardcoded `"overclaw"` fallback from `slack_channel.py` and `slack_notify.py`; they now use `os.environ["DB_NAME"]`
- **PyMongo Audit**: Confirmed all `_db` checks use `is None` (no broken `if not _db` patterns remain)

## P1 — Upcoming
- Microsoft Outlook E2E testing (blocked on Azure creds)
- Microsoft Teams integration
- Background tasks DB secrets architectural fix (standalone script entry points)

## P2 — Backlog
- Webchat/Slack sync verification
- Local setup scripts (`install_local.sh`, `run_local.sh`) verification
- Demo GIF/recording for README
- GitHub social preview image
- Interactive browser agent fix (KVM site)
