# OverClaw — PRD

## Problem Statement
Build a streamlined work assistant ("OverClaw") inspired by the openclaw repository. The project has an orchestration architecture where a primary agent delegates tasks to specialists. The project should be open-source-ready.

## Architecture
- **Backend:** FastAPI + MongoDB
- **Frontend:** React
- **Core:** Orchestrator agent delegates to specialist tools (browser, code executor, email, etc.)
- **Deployment:** Docker + docker-compose

## What's Been Implemented

### Core
- Orchestrator agent with tool-calling loop (OpenAI + Anthropic)
- Session management, chat history
- Long-term memory / RAG with embeddings (cosine similarity)

### Intelligence Features
- **Passive User Profile:** Extracts user facts from conversations, injects into context
- **Relationship Memory:** Discovers people and org chart from conversations
- **Email Memory (Feb 2026):** Auto-indexes emails into RAG when the agent reads them. Feeds email content into Profile and Relationship extractors. Works for both Gmail and Outlook.
- **Brain Export/Import (Feb 2026):** Portable knowledge transfer between deployments. Exports memories, user profile, and relationships as a single JSON file. Smart merge on import (deduplication, fact merging, re-embedding).

### Integrations
- Gmail (OAuth, read/search/send)
- Outlook/Microsoft 365 (OAuth scaffolding, read/search/send — untested e2e)
- Slack (Socket Mode, real-time sync with webchat)

### Admin / Setup
- Onboarding Wizard (API key setup via UI, stored in MongoDB)
- People admin view (discovered relationships)
- Outlook admin panel
- Brain panel (export/import)

### Open Source Prep
- README with banner, feature docs
- Docker build fixes, clean requirements.txt
- yarn.lock tracked
- CVS Health proposal document (HTML, served at /api/proposals/)

## Pending Issues
1. **P0:** Outlook integration e2e testing
2. **P1:** Webchat/Slack sync verification (recurring)
3. **P2:** Full Slack regression test

## Upcoming Tasks
- Microsoft Teams integration
- Verify local setup scripts (install_local.sh, run_local.sh)

## Backlog
- "Already configured" indicators in setup wizard
- Demo GIF for README
- GitHub social preview image
- Interactive browser agent fix on KVM site
- Pytest regression tests for backend

## Key Files
- `backend/gateway/brain.py` — Brain Export/Import logic
- `backend/gateway/email_memory.py` — Email Memory (RAG + extractors)
- `backend/gateway/memory.py` — RAG/Memory system
- `backend/gateway/user_profile.py` — Passive user profile
- `backend/gateway/relationship_memory.py` — Relationship discovery
- `backend/gateway/tools/gmail.py` — Gmail agent tool
- `backend/gateway/tools/outlook.py` — Outlook agent tool
- `backend/gateway/agent.py` — Agent runtime
- `backend/gateway/setup.py` — Onboarding wizard backend
- `backend/server.py` — FastAPI routes
- `frontend/src/components/dashboard/BrainPanel.js` — Brain UI
- `backend/static/proposal-cvs-overclaw.html` — CVS proposal
