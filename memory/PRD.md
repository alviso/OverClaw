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
- **Email Triage Task** (5 min interval): 3-tier email classification with improved prompt v2
  - Tier A (Action Required): Read full email, extract specific action + deadline, Slack notify
  - Tier B (FYI): Mention briefly in Slack summary
  - Tier C (Skip): Marketing/spam/low-priority — ignored entirely
  - Format: Leads with ACTION, not context. Concise Slack-ready bullet points.
- `slack_notify` tool for proactive Slack messaging (auto-targets last active conversation)

### Configuration & Management
- Onboarding Wizard (`/admin/setup`)
- Credentials Editor (`/admin/config`)
- Brain Export/Import (`/admin/brain`)
- People Management (`/admin/people`) with merge, delete, inline email editing
- Tasks UI (`/admin/tasks`)
- Live Debug Logs (`/admin/logs`)
- Mindmap Visualization (`/admin/mindmap`)

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
- RPC: `workspace.cleanup_processes`
- RPC: `mindmap.generate`, `mindmap.get`, `mindmap.set_importance`
- RPC: `debug.logs`, `debug.clear`, `debug.test`

## DB Schema
- **relationships**: `{ name, name_key, email_address, role, team, relationship, mention_count, context_history, aliases, last_seen }`
- **settings**: `{ key, value }` — includes `slack_last_active_channel`
- **tasks**: `{ id, name, prompt, prompt_version, interval_seconds, enabled, ... }`
- **setup_secrets**: `{ _id: "main", openai_api_key, anthropic_api_key, gateway_token, ... }`
- **debug_logs**: `{ timestamp, level, name, pathname, lineno, msg, exc_text }`

## Completed — Email Triage Prompt Improvement (Feb 2026)
- **Root Cause**: The email triage task prompt was too generic, giving the LLM freedom to produce verbose, non-actionable summaries that missed key actions and repeated known context.
- **Fix**: Created `backend/gateway/email_triage.py` with a structured 4-step prompt:
  1. Fetch recent unread emails
  2. Classify into Tier A (Action Required), B (FYI), C (Skip)
  3. Read Tier A emails in full and extract specific actions + deadlines
  4. Compose ONE concise Slack notification with action-first formatting
- **Versioned prompt**: `prompt_version=2` allows future updates while preserving user settings
- **Seeded on startup**: `server.py` calls `seed_email_triage_task(db)` to create/update the task idempotently

## P1 — Upcoming
- Microsoft Outlook E2E testing (blocked on Azure creds)
- Microsoft Teams integration
- Fix `browser_use` tool (missing `uvx` dependency)

## P2 — Backlog
- Webchat/Slack sync verification
- Local setup scripts verification
- Demo GIF/recording for README
- GitHub social preview image
- Interactive browser agent fix (KVM site)
