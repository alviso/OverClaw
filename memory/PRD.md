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

## DB Schema
- **relationships**: `{ name, name_key, email_address, role, team, relationship, mention_count, context_history, aliases, last_seen }`
- **settings**: `{ key, value }` — includes `slack_last_active_channel`
- **tasks**: `{ id, name, prompt, interval_seconds, enabled, ... }`

## P0 — In Progress
- Monitor email triage task accuracy across cycles

## P1 — Upcoming
- Microsoft Outlook e2e testing (blocked on Azure creds)
- Microsoft Teams integration
- Background tasks DB secrets architectural fix

## P2 — Backlog
- Webchat/Slack sync verification
- Local setup scripts verification
- Demo GIF/recording for README
- Consolidate deduplication logic
- GitHub social preview image
