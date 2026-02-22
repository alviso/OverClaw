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
- **Email Triage Task** (5 min interval): 3-tier email classification with improved prompt v3
  - Tier A (Action Required): Read full email, extract specific action + deadline, Slack notify
  - Tier B (FYI): Mention briefly in Slack summary
  - Tier C (Skip): Marketing/spam/low-priority — ignored entirely
  - Format: Leads with ACTION, not context. Concise Slack-ready bullet points.
  - **Feedback loop**: Appends 👍/👎 reaction prompt, tracks responses, auto-tunes prompt

### Triage Feedback System (Feb 2026)
- **Reaction Tracking**: After each triage Slack message, appends "React 👍 or 👎 to rate this summary"
- **Feedback Storage**: `triage_messages` MongoDB collection tracks sent messages and reactions
- **Auto-Tuning**: Before each triage run, injects feedback context into the prompt
- **RPC endpoints**: `triage.feedback_stats`, `triage.recent_feedback`

### Slack/Webchat Quality Parity Fix (Feb 2026)
- **Root Cause**: Orchestrator had `web_search` in tools_allowed, did shallow searches instead of delegating to research specialist
- **Fix**: Removed `web_search` from orchestrator tools (declarative set, not additive)
- **Versioned Prompts**: `ORCHESTRATOR_PROMPT_VERSION=3` ensures prompt improvements propagate to existing installs
- **!debug Command**: Users can type `!debug` in Slack to inspect active agent config (tools, model, prompt version)
- **Diagnostic Logging**: `run_turn` now logs session/agent/tools for every request

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
- Slack: Connected with proactive notification support + reaction feedback + !debug

## Key API Endpoints
- `POST /api/brain/export` / `POST /api/brain/import`
- `POST /api/people/merge` / `DELETE /api/people/{id}` / `PATCH /api/people/{id}`
- RPC: `people.list`, `people.merge`, `people.delete`
- RPC: `workspace.cleanup_processes`
- RPC: `mindmap.generate`, `mindmap.get`, `mindmap.set_importance`
- RPC: `debug.logs`, `debug.clear`, `debug.test`
- RPC: `triage.feedback_stats`, `triage.recent_feedback`

## DB Schema
- **relationships**: `{ name, name_key, email_address, role, team, relationship, mention_count, context_history, aliases, last_seen }`
- **settings**: `{ key, value }` — includes `slack_last_active_channel`
- **tasks**: `{ id, name, prompt, prompt_version, interval_seconds, enabled, ... }`
- **setup_secrets**: `{ _id: "main", openai_api_key, anthropic_api_key, gateway_token, ... }`
- **debug_logs**: `{ timestamp, level, name, pathname, lineno, msg, exc_text }`
- **triage_messages**: `{ channel, message_ts, summary_preview, sent_at, feedback, feedback_reaction, feedback_user, feedback_at }`
- **gateway_config**: `{ agent: { tools_allowed, system_prompt, prompt_version, model } }`

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
