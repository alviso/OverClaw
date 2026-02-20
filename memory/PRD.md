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
- **Relationship Memory:** Discovers people and org chart from conversations AND emails
  - Smart fuzzy name matching (accent normalization, "Last, First" handling, subset detection)
  - Email-based extraction from SENT emails only (user's responded emails)
  - Structured parsing of To/CC headers (free, no LLM cost)
  - LLM extraction for roles, teams, relationships from email body
  - Deduplication by email address, name_key, AND fuzzy name matching
  - Prevents false merges (e.g., siblings with same surname)
- **Email Memory (Feb 2026):** Auto-indexes emails into RAG with embeddings when the agent reads them
- **Brain Export/Import (Feb 2026):** Portable knowledge transfer between deployments

### Integrations
- Gmail (OAuth, read/search/send) — connected, working
- Outlook/Microsoft 365 (OAuth scaffolding — blocked on Azure app access)
- Slack (Socket Mode, real-time sync with webchat)

### Admin / Setup
- Onboarding Wizard (API key setup via UI, stored in MongoDB)
- **Credentials Editor** — update API keys from admin Config page
- People admin view (discovered relationships with email addresses)
- Outlook admin panel
- Brain panel (export/import)

### Open Source Prep
- README with banner, feature docs
- Docker build fixes, clean requirements.txt
- CVS Health proposal document

## Pending Issues
1. Outlook integration e2e (blocked on Azure app access)
2. Full Slack regression test

## Upcoming Tasks
- Microsoft Teams integration
- Verify local setup scripts

## Backlog
- "Already configured" indicators in setup wizard
- Demo GIF for README
- Pytest regression tests for backend

## Key Files
- `backend/gateway/email_memory.py` — Email Memory + fuzzy name matching + people extraction
- `backend/gateway/relationship_memory.py` — Relationship discovery (conversation + email)
- `backend/gateway/brain.py` — Brain Export/Import
- `backend/gateway/memory.py` — RAG/Memory system
- `backend/gateway/user_profile.py` — Passive user profile
- `backend/gateway/gmail.py` — Gmail OAuth + API
- `backend/gateway/setup.py` — Onboarding wizard + DB-backed secrets
- `backend/server.py` — FastAPI routes
- `frontend/src/components/dashboard/BrainPanel.js` — Brain UI
- `frontend/src/components/dashboard/CredentialsEditor.js` — Credentials UI
- `frontend/src/components/dashboard/RelationshipsPanel.js` — People UI
