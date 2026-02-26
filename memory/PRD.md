# OverClaw — Product Requirements Document

## Original Problem Statement
Build a streamlined work assistant "OverClaw" inspired by the openclaw repository. The project uses an orchestration architecture where a primary agent delegates tasks to specialists. Key integrations include Gmail, Slack, Microsoft Outlook (untested), and a screen-sharing capability for the webchat UI.

## Architecture
- **Backend**: FastAPI + MongoDB
- **Frontend**: React
- **Agent**: Orchestrator delegates to specialists (research, etc.)
- **Integrations**: Gmail, Slack, Outlook (untested), Scrapling (web scraping)
- **Screen Sharing**: Browser-native getDisplayMedia API, auto-capture PNG on send, background memory storage with Tesseract OCR

## What's Been Implemented

### Core Intelligence
- Orchestrator agent with delegation to specialist agents
- Email RAG pipeline, memory_search tool
- Conversation history and tool call propagation

### Integrations
- Gmail and Slack functional
- Scrapling-based web scraping (replaced Playwright)
- Microsoft Outlook coded but untested

### Automated Tasks
- Email triage with Slack summaries
- User feedback mechanism (thumbs up/down reactions)

### Screen Sharing + OCR (Feb 2026)
- Screen sharing via getDisplayMedia API in webchat
- Auto-capture lossless PNG on message send
- Background analysis and persistent memory storage
- **Tesseract OCR integration** (P0 fix): 2x LANCZOS upscaling + grayscale preprocessing
  - OCR text passed to LLM alongside image for multi-modal analysis
  - OCR text appended to stored memories for searchability
  - Fixes misread of `ext_mikova@mattoni.cz` as `ext_mkoval@mattoni.cz`

### UI/UX
- Webchat, admin panels (config/logs), mindmap page
- Screen sharing preview and controls

## Prioritized Backlog

### P1
- Microsoft Teams integration
- Full E2E testing of Microsoft Outlook integration (blocked on user Azure setup)

### P2
- Webchat WebSocket timeout fix (long-running tasks >30s)
- Verify Webchat/Slack sync (omni-channel)
- Fix `browser_use` tool (missing `uvx` dependency)

### P3
- Verify local setup scripts (install_local.sh, run_local.sh)
- Remove demo mindmap route and hardcoded data

### Future
- Demo recording/GIF for README
- GitHub social preview image
- Interactive browser agent on KVM site

## Known Issues
- `browser_use` tool: non-functional (missing uvx dependency, workaround: disabled)
- Webchat client: WebSocket disconnects on tasks >30s
- Microsoft Outlook: coded but never tested with real account
