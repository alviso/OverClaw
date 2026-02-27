# OverClaw — Product Requirements Document

## Original Problem Statement
Build a streamlined work assistant "OverClaw" inspired by OpenClaw. An orchestration architecture where a primary agent delegates tasks to specialists, with integrations for Gmail, Slack, Outlook, screen sharing with OCR, and persistent searchable memory.

## Architecture
- **Backend**: FastAPI + MongoDB + WebSocket (JSON-RPC)
- **Frontend**: React + Tailwind + Shadcn
- **AI**: OpenAI + Anthropic (multi-model support)
- **Memory**: FAISS vector index + MongoDB text search (hybrid)
- **Deployment**: Docker (local) + Emergent Preview

## What's Been Implemented

### Core
- Orchestrator agent with specialist delegation
- Multi-model support: GPT-5.2, GPT-5.2 Pro, GPT-5 Mini, GPT-4.1, GPT-4.1 Mini, GPT-4o, Claude Opus 4.6, Claude Sonnet 4.6, Claude Sonnet 4.5, Claude Haiku 4.5
- WebSocket gateway with JSON-RPC protocol
- Agent self-identification (model name injected into system prompt)

### Memory System (Feb 27, 2026 — Major Upgrade)
- **FAISS vector index**: Replaces brute-force cosine similarity. Sub-millisecond search.
- **Hybrid search**: 70% vector similarity (FAISS) + 30% keyword match (MongoDB text index)
- **Per-agent isolation**: Specialist agents only see their own memories. Orchestrator sees all.
- **Intelligent fact extraction**: Claude Haiku 4.5 extracts discrete facts (type: fact/decision/action_item/preference) from conversations
- **Reprocessing**: API endpoint (`memory.reprocess`) converts raw Q&A memories into discrete facts. Idempotent. Works in Docker and preview.
- **UI stats panel**: Shows total memories, FAISS index size, raw Q&A count, extracted facts, hybrid weights, by-agent breakdown, reprocess button

### Integrations
- Gmail (OAuth 2.0) — functional
- Slack (bolt) — functional
- Microsoft Outlook (Graph API) — untested
- Screen sharing with Tesseract OCR
- Web search (Scrapling)

### Automation
- Scheduled email triage with Slack summaries
- User feedback mechanism (thumbs up/down)

## Prioritized Backlog

### P0
- (none currently)

### P1
- Microsoft Outlook end-to-end testing (requires user Azure setup)
- Microsoft Teams integration
- WebSocket timeout for long-running agent tasks (keep-alive/ping-pong)

### P2
- `browser_use` tool fix (missing `uvx` dependency)
- Verify Webchat / Slack sync
- Remove demo mindmap (hardcoded data + `/demo/mindmap` route)

### P3
- Verify local setup scripts (`install_local.sh`, `run_local.sh`)
- Create demo recording/GIF for README
- Create GitHub social preview image
- Docker build simplification

## Key Technical Notes
- MongoDB 7.0 Community (no native $vectorSearch — using FAISS instead)
- Docker build: two-step pip install (requirements.txt then scrapling[fetchers])
- FAISS index rebuilt on startup from MongoDB; in-memory during runtime
- Fact extraction uses Haiku 4.5 (cheapest Anthropic model) to minimize cost
- Memory deduplication: new facts checked against existing (0.92 similarity threshold)
