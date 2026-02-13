# OpenClaw — Deep Architectural Analysis

## For: Building a Controlled Corporate Work Assistant

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Subsystem Deep Dives](#3-subsystem-deep-dives)
   - 3.1 [Gateway (Control Plane)](#31-gateway-control-plane--26860-loc)
   - 3.2 [Agent Runtime](#32-agent-runtime--48277-loc)
   - 3.3 [Auto-Reply Engine](#33-auto-reply-engine--22435-loc)
   - 3.4 [Channel Abstraction](#34-channel-abstraction--9373-loc)
   - 3.5 [Plugin System](#35-plugin-system--5861-loc)
   - 3.6 [Extensions (Channel Plugins)](#36-extensions-channel-plugins--68909-loc)
   - 3.7 [Configuration System](#37-configuration-system--15887-loc)
   - 3.8 [CLI Surface](#38-cli-surface--21335-loc)
   - 3.9 [Web UI (Control UI + WebChat)](#39-web-ui-control-ui--webchat--25997-loc)
   - 3.10 [Memory / RAG Subsystem](#310-memory--rag-subsystem--7236-loc)
   - 3.11 [Browser Control](#311-browser-control--11012-loc)
   - 3.12 [Media Understanding Pipeline](#312-media-understanding-pipeline--3536-loc)
   - 3.13 [Routing & Sessions](#313-routing--sessions--1063-loc)
   - 3.14 [Hooks System](#314-hooks-system--3599-loc)
   - 3.15 [TTS / Voice](#315-tts--voice--1583-loc)
   - 3.16 [Mobile Apps (iOS / Android / macOS)](#316-mobile-apps-ios--android--macos)
   - 3.17 [Skills Platform](#317-skills-platform)
   - 3.18 [Security Layer](#318-security-layer)
4. [Key Design Patterns](#4-key-design-patterns)
5. [What's Bloat vs. What's Essential](#5-whats-bloat-vs-whats-essential)
6. [Step-by-Step Build Plan: Corporate Work Assistant](#6-step-by-step-build-plan-corporate-work-assistant)
7. [Phase Dependency Graph](#7-phase-dependency-graph)
8. [Blueprint Comparison Matrix](#8-blueprint-comparison-matrix)

---

## 1. Executive Summary

**OpenClaw** is a ~270k LOC TypeScript monorepo that implements a **personal AI assistant** with a local-first architecture. Its core insight is the **Gateway pattern**: a single WebSocket control plane that sits between messaging channels (WhatsApp, Telegram, Slack, Discord, etc.) and an AI agent runtime, routing messages bidirectionally.

### The Architecture in One Sentence

> A **WebSocket gateway** receives messages from **channel adapters**, resolves them through a **routing layer** to an **agent session**, runs the agent with **tools** in a **sandboxed environment**, and delivers replies back through the originating channel — all configured via a **single JSON file** and managed via **CLI, Web UI, or companion apps**.

### Key Stats

| Subsystem | Non-test LOC | Purpose |
|-----------|-------------|---------|
| Extensions | 68,909 | Channel plugins (Telegram, Discord, Slack, etc.) |
| Agents | 48,277 | AI agent runtime, tools, model management |
| Gateway | 26,860 | WebSocket control plane |
| Web UI | 25,997 | Lit-based Control UI + WebChat |
| Auto-Reply | 22,435 | Inbound message → agent → outbound reply pipeline |
| CLI | 21,335 | Commander.js CLI with 30+ subcommands |
| Config | 15,887 | Zod schema-validated JSON config |
| Browser | 11,012 | Playwright-based browser automation tool |
| Channels | 9,373 | Channel abstraction layer |
| Memory | 7,236 | sqlite-vec RAG with embeddings |
| Plugins | 5,861 | Plugin runtime, loader, hooks |
| Hooks | 3,599 | Lifecycle hook system |
| Media | 3,536 | Image/audio/video processing pipeline |
| TTS | 1,583 | Text-to-speech (ElevenLabs, Edge TTS) |
| Routing | 646 | Channel → agent → session key resolution |
| Sessions | 417 | Session metadata, send policy |

---

## 2. High-Level Architecture

```
                    ┌──────────────────────────────────┐
                    │         Messaging Channels        │
                    │  WhatsApp │ Telegram │ Slack │ …  │
                    └──────────────┬───────────────────┘
                                   │ Inbound messages
                                   ▼
┌──────────────────────────────────────────────────────────┐
│                     GATEWAY (WS Control Plane)            │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │   HTTP/WS    │  │  Protocol    │  │   Auth Layer    │ │
│  │   Server     │  │  (JSON-RPC)  │  │  (token/pass)   │ │
│  └──────┬──────┘  └──────┬───────┘  └─────────────────┘ │
│         │                │                                │
│  ┌──────▼────────────────▼──────────────────────────┐    │
│  │              Server Methods (RPC handlers)        │    │
│  │  chat.send │ sessions.patch │ config.get │ …      │    │
│  └──────────────────────┬───────────────────────────┘    │
│                         │                                 │
│  ┌──────────────────────▼───────────────────────────┐    │
│  │           Channel Manager + Registry              │    │
│  │  Loads channel plugins, manages connections       │    │
│  └──────────────────────┬───────────────────────────┘    │
│                         │                                 │
│  ┌──────────────────────▼───────────────────────────┐    │
│  │           Runtime State + Health Cache             │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                    AUTO-REPLY ENGINE                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │  Envelope    │  │  Command    │  │  Routing         │  │
│  │  (normalize) │  │  Detection  │  │  (agent/session) │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
│         │                │                    │           │
│         └────────────────▼────────────────────┘           │
│                          │                                │
│  ┌───────────────────────▼──────────────────────────┐    │
│  │              Reply Runner                         │    │
│  │  Queue → Directive Parse → Agent Turn → Dispatch  │    │
│  └───────────────────────┬──────────────────────────┘    │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                    AGENT RUNTIME (Pi)                      │
│  ┌─────────────────┐  ┌─────────────────────────────┐   │
│  │  Model Selection │  │  Auth Profile Rotation       │   │
│  │  + Failover      │  │  (OAuth, API keys, chutes)   │   │
│  └────────┬────────┘  └─────────────┬───────────────┘   │
│           │                          │                    │
│  ┌────────▼──────────────────────────▼──────────────┐   │
│  │         Embedded Pi Agent Runner                  │   │
│  │  System prompt → Tool calls → Block streaming     │   │
│  └────────────────────────┬─────────────────────────┘   │
│                           │                              │
│  ┌────────────────────────▼─────────────────────────┐   │
│  │                   TOOLS                           │   │
│  │  bash │ browser │ web_fetch │ web_search │ canvas │   │
│  │  cron │ message │ sessions_* │ memory │ nodes    │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │         SANDBOX (Docker per-session)              │   │
│  │  Tool isolation for non-main sessions             │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘

                    ┌──────────────────────────────────┐
                    │        PERSISTENCE LAYER          │
                    │  ~/.openclaw/                     │
                    │  ├── openclaw.json  (config)      │
                    │  ├── sessions/      (JSONL logs)  │
                    │  ├── credentials/   (OAuth)       │
                    │  ├── workspace/     (skills)      │
                    │  └── memory/        (sqlite-vec)  │
                    └──────────────────────────────────┘
```

### Data Flow (Single Message)

```
1. WhatsApp msg arrives via Baileys WebSocket connection
2. WhatsApp channel adapter normalizes it into an Envelope
3. Envelope hits Auto-Reply engine
4. Auto-Reply checks: is it a /command? is it in an allowed group? DM policy?
5. Routing resolves: channel + peer → agentId + sessionKey
6. Message queued (debounce for fast-typing)
7. Agent runner loads session history (JSONL file)
8. Pi embedded runner calls LLM API with system prompt + history + tools
9. LLM streams back: text blocks + tool calls
10. Tool calls executed (bash, browser, web_search, etc.)
11. Response chunked per channel limits (2000 chars for Discord, 4096 for Telegram)
12. Chunks sent back through channel adapter → WhatsApp
13. Session history appended to JSONL file
14. Optional: memory flush (embeddings stored for RAG)
```

---

## 3. Subsystem Deep Dives

### 3.1 Gateway (Control Plane) — 26,860 LOC

**What it does**: The gateway is the beating heart. It's an Express + WebSocket server that acts as a message bus.

**Key files**:
- `server.impl.ts` — Main `startGatewayServer()` function (663 LOC), wires everything together
- `server-methods.ts` — Maps RPC method names to handlers
- `server-methods/` — Individual RPC handler files (chat, sessions, config, agents, etc.)
- `protocol/` — JSON-RPC protocol schema (TypeBox + AJV validation)
- `server-ws-runtime.ts` — WebSocket connection lifecycle
- `server-channels.ts` — Channel manager that loads/starts/stops channel plugins
- `server-chat.ts` — Agent event handling (incoming chat → agent)
- `server-cron.ts` — Cron job scheduler
- `server-plugins.ts` — Plugin lifecycle management

**Protocol**: Custom JSON-RPC over WebSocket. Each method has a typed params/result schema defined with TypeBox:
```typescript
// Example RPC method: chat.send
{ method: "chat.send", params: { sessionKey, text, attachments? } }
// → triggers agent run, streams back ChatEvent messages
```

**Key patterns**:
- **Method registry**: All RPC methods registered in `server-methods-list.ts` with handler + schema pairs
- **Broadcast**: Events (chat, health, config changes) broadcast to all connected WS clients
- **Health cache**: Periodic health snapshots with versioning for efficient polling
- **Config reload**: Hot-reloading of `openclaw.json` without gateway restart

**Corporate relevance**: The gateway pattern is excellent for enterprise — it's a single control point with auth, audit, and health checks. You'd want this as your core.

---

### 3.2 Agent Runtime — 48,277 LOC

**What it does**: The largest subsystem. Manages AI model interaction, tool execution, session persistence, prompt engineering, and sandboxing.

**Key areas**:

#### Model Management (`model-*.ts`, `models-config.ts`)
- Model catalog with aliases (`anthropic/claude-opus-4-6`, `openai/gpt-5.2`)
- Model selection logic (per-session overrides, directive-based switching)
- Auth profile rotation: multiple API keys/OAuth sessions, failover between them
- Support for: Anthropic, OpenAI, Google, Bedrock, OpenRouter, local Ollama

#### Pi Embedded Runner (`pi-embedded-runner/`)
The actual agent loop:
```
1. Build system prompt (AGENTS.md + SOUL.md + TOOLS.md + skills)
2. Load session history from JSONL
3. Sanitize history for target model (Google needs different turn ordering)
4. Call LLM API with streaming
5. Process stream: text blocks → tool calls → text blocks
6. Execute tool calls (with policy checks)
7. Persist to session transcript
```

#### Tools (`agents/tools/`)
- `bash-tools.ts` — Shell execution with PTY support, background processes
- `browser-tool.ts` — Playwright browser automation
- `web-fetch.ts` / `web-search.ts` — Web content retrieval
- `canvas-tool.ts` — Visual workspace (A2UI)
- `cron-tool.ts` — Schedule recurring tasks
- `message-tool.ts` — Send messages to channels
- `sessions-send-tool.ts` — Cross-session communication
- `memory-tool.ts` — RAG search across memory
- `image-tool.ts` — Image generation
- `discord-actions.ts` / `slack-actions.ts` / `telegram-actions.ts` — Channel-specific actions

#### Sandbox (`agents/sandbox/`)
Docker-based isolation for non-main sessions:
- Per-session containers
- Tool allowlist/denylist
- Workspace mounting
- Automatic pruning

#### Skills (`agents/skills/`)
Prompt injection system:
- Bundled skills (shipped with OpenClaw)
- Managed skills (from ClawHub registry)
- Workspace skills (`~/.openclaw/workspace/skills/<name>/SKILL.md`)
- Skills are markdown files injected into system prompt

**Corporate relevance**: This is the core you need, but heavily simplified. For a corporate assistant:
- Keep model management + failover (essential for reliability)
- Keep tool execution with policy enforcement (security)
- Drop sandbox complexity initially (use simpler permission model)
- Keep skills system (great for customizing behavior per team/role)

---

### 3.3 Auto-Reply Engine — 22,435 LOC

**What it does**: The middleware between inbound messages and the agent. It's the "business logic" layer.

**Key pipeline**:
```
Inbound Message
    │
    ▼
Envelope normalization (src/auto-reply/envelope.ts)
    │
    ▼
Command detection (/status, /reset, /think, /model, etc.)
    │  → If command: execute immediately, return response
    │
    ▼
Group activation check (mention-only? always?)
    │
    ▼
DM pairing check (is sender approved?)
    │
    ▼
Directive parsing (@opus, /think high, etc.)
    │
    ▼
Queue (debounce rapid messages)
    │
    ▼
Agent runner (reply/agent-runner.ts)
    │  → System prompt construction
    │  → LLM call with tools
    │  → Block streaming + chunking
    │
    ▼
Reply dispatch (route to correct channel + format)
```

**Key concepts**:
- **Directives**: Inline model/thinking/verbose switches (`@opus Ship this`, `/think high`)
- **Block streaming**: Long responses split into paragraphs, sent as separate messages
- **Reply threading**: Responses threaded to original message (platform-specific)
- **Queue modes**: Serial (one at a time) or concurrent per session
- **Followup runs**: Agent can trigger follow-up turns after tool execution

**Corporate relevance**: Good pattern, but simplify. You need:
- Command detection (for admin controls)
- Queue/debounce (prevents flooding)
- Reply routing (essential for multi-channel)
- Drop directives complexity (use config instead)

---

### 3.4 Channel Abstraction — 9,373 LOC

**What it does**: Defines the contract that all messaging channels must implement.

**The ChannelPlugin interface** (`channels/plugins/types.plugin.ts`):
```typescript
type ChannelPlugin = {
  id: ChannelId;
  meta: ChannelMeta;           // Display name, icon, etc.
  capabilities: ChannelCapabilities;  // Supports threading? reactions? etc.
  config: ChannelConfigAdapter;       // Read config, resolve accounts
  setup?: ChannelSetupAdapter;        // Start/stop the channel
  pairing?: ChannelPairingAdapter;    // DM approval flow
  security?: ChannelSecurityAdapter;  // Allowlists, DM policy
  groups?: ChannelGroupAdapter;       // Group message handling
  mentions?: ChannelMentionAdapter;   // @mention detection
  outbound?: ChannelOutboundAdapter;  // Send messages out
  status?: ChannelStatusAdapter;      // Health/status checks
  gateway?: ChannelGatewayAdapter;    // WS method handlers
  streaming?: ChannelStreamingAdapter;  // Streaming support
  threading?: ChannelThreadingAdapter;  // Thread/reply support
  messaging?: ChannelMessagingAdapter;  // Message formatting
  // ... 15+ adapter interfaces
};
```

**Key sub-layers**:
- **Registry** (`registry.ts`) — Lists all known channel IDs
- **Allowlists** (`allowlists/`) — Per-channel sender approval
- **Typing indicators** (`typing.ts`) — Cross-channel typing status
- **Conversation labels** (`conversation-label.ts`) — Consistent naming
- **Mention gating** (`mention-gating.ts`) — Group activation rules

**Corporate relevance**: This is a **great abstraction** to borrow. The adapter pattern means you can start with 1-2 channels (Slack + WebChat) and add more later without touching core logic. Keep this pattern but simplify the interface — you probably need 5-6 adapters, not 15+.

---

### 3.5 Plugin System — 5,861 LOC

**What it does**: Runtime plugin loading, lifecycle management, and service registration.

**Architecture**:
```
plugins/
├── discovery.ts    — Finds plugins in extensions/ and node_modules
├── loader.ts       — Loads plugin modules via jiti (TypeScript JIT)
├── install.ts      — npm install for plugin dependencies
├── runtime.ts      — Plugin runtime context (logger, config access)
├── registry.ts     — Global plugin registry
├── hooks.ts        — Plugin hook system
├── tools.ts        — Plugin-provided agent tools
├── services.ts     — Long-running plugin services
└── http-registry.ts — Plugin HTTP route registration
```

**Plugin contract** (`plugins/types.ts`):
```typescript
type OpenClawPluginApi = {
  runtime: PluginRuntime;
  registerChannel(opts: { plugin: ChannelPlugin }): void;
  registerTool(tool: AnyAgentTool): void;
  registerHook(event: string, handler: Function): void;
  registerHttpRoute(path: string, handler: Function): void;
  registerService(service: OpenClawPluginService): void;
  registerProvider(provider: ProviderAuthContext): void;
};
```

**Corporate relevance**: Plugin architecture is excellent for enterprise. It lets teams extend the assistant without modifying core code. Keep this pattern but make it simpler (no jiti — use standard ESM imports or a simpler loader).

---

### 3.6 Extensions (Channel Plugins) — 68,909 LOC

**What it does**: Each messaging channel is implemented as a plugin/extension.

**Built-in channels** (in `src/`): WhatsApp (Baileys), Telegram (grammY), Slack (Bolt), Discord (discord.js), Signal (signal-cli), iMessage (legacy)

**Extension channels** (in `extensions/`): BlueBubbles, Microsoft Teams, Matrix, Google Chat, Mattermost, IRC, Line, Nostr, Zalo, Feishu, Twitch, Tlon, Nextcloud Talk, Voice Call

**Extension structure**:
```
extensions/slack/
├── package.json              — Plugin metadata
├── openclaw.plugin.json      — Plugin manifest (id, channels, configSchema)
├── index.ts                  — Plugin entry: register(api) → api.registerChannel(...)
└── src/
    ├── channel.ts            — ChannelPlugin implementation
    └── runtime.ts            — Runtime context
```

**Corporate relevance**: You only need Slack + Microsoft Teams + WebChat for corporate. The extension structure means each is isolated and testable. Borrow the pattern, implement 2-3 channels.

---

### 3.7 Configuration System — 15,887 LOC

**What it does**: Single-file JSON configuration with runtime validation, migration, and hot-reload.

**Config file**: `~/.openclaw/openclaw.json`

**Key components**:
- `schema.ts` + `zod-schema.ts` — Full config schema using Zod v4
- `config.ts` — Load, validate, migrate config
- `types.*.ts` — TypeScript types for each config section (agents, channels, gateway, tools, etc.)
- `legacy.migrations.ts` — Automatic migration from older config versions
- `env-vars.ts` — Environment variable overrides
- `sessions/` — Session persistence (JSONL transcripts)

**Config structure** (simplified):
```json5
{
  "agent": {
    "model": "anthropic/claude-opus-4-6",
    "workspace": "~/.openclaw/workspace"
  },
  "gateway": {
    "port": 18789,
    "bind": "loopback",
    "auth": { "mode": "token", "token": "..." }
  },
  "channels": {
    "telegram": { "botToken": "..." },
    "slack": { "botToken": "...", "appToken": "..." },
    "discord": { "token": "..." }
  },
  "tools": {
    "browser": { "enabled": true },
    "bash": { "enabled": true }
  },
  "agents": {
    "defaults": {
      "sandbox": { "mode": "non-main" }
    }
  }
}
```

**Corporate relevance**: Essential pattern. A validated JSON config with schema is exactly right for enterprise (auditable, version-controllable). Simplify the schema to your needs — OpenClaw has 100+ config keys, you'll need ~20.

---

### 3.8 CLI Surface — 21,335 LOC

**What it does**: Commander.js-based CLI with 30+ subcommands.

**Key commands**:
```
openclaw onboard          — Interactive setup wizard
openclaw gateway          — Start the gateway server
openclaw agent            — Direct agent interaction
openclaw message send     — Send a message
openclaw channels status  — Check channel health
openclaw config set       — Modify config
openclaw doctor           — Health checks + migrations
openclaw tui              — Terminal UI (Pi TUI)
openclaw nodes            — Manage device nodes
openclaw browser          — Browser control
openclaw cron             — Manage scheduled tasks
```

**Pattern**: Uses `createDefaultDeps()` for dependency injection throughout CLI commands.

**Corporate relevance**: Good for ops/admin. Keep `gateway`, `config`, `doctor`, `agent`. Drop device-specific commands (nodes, browser management, TUI).

---

### 3.9 Web UI (Control UI + WebChat) — 25,997 LOC

**What it does**: Lit-based (Web Components) web interface served directly from the Gateway.

**Components**:
- **Control UI** — Dashboard showing gateway health, sessions, channels, config editor
- **WebChat** — Full chat interface communicating via Gateway WebSocket

**Tech stack**: Lit 3.x, no build framework (bundled by the gateway).

**Corporate relevance**: WebChat is very useful. Control UI is nice-to-have. Consider replacing with React if that's your team's stack, but the pattern of serving UI from the gateway is good.

---

### 3.10 Memory / RAG Subsystem — 7,236 LOC

**What it does**: Long-term memory via embeddings stored in sqlite-vec.

**Architecture**:
```
Session Transcripts (JSONL)
    │
    ▼ (periodic sync)
Embedding Pipeline
    │  ├── OpenAI embeddings
    │  ├── Google Gemini embeddings
    │  ├── Voyage embeddings
    │  └── Local llama embeddings
    │
    ▼
sqlite-vec (vector database)
    │
    ▼
Memory Search Tool (hybrid: vector + keyword)
```

**Key files**:
- `manager.ts` — Main MemoryManager: sync, search, reindex
- `embeddings.ts` — Embedding provider abstraction
- `sqlite-vec.ts` — SQLite with vector extension
- `hybrid.ts` — Hybrid search (vector similarity + BM25-style keyword)
- `session-files.ts` — Extract memory entries from session transcripts

**Corporate relevance**: Important for a work assistant. Keeps context across conversations. The sqlite-vec approach is good for local-first. For corporate, you might want a centralized vector DB instead.

---

### 3.11 Browser Control — 11,012 LOC

**What it does**: Playwright-based browser automation. The agent can navigate, click, fill forms, take screenshots.

**Corporate relevance**: Powerful but risky for enterprise. Consider it a Phase 4+ feature with heavy guardrails.

---

### 3.12 Media Understanding Pipeline — 3,536 LOC

**What it does**: Processes images, audio, and video attachments.

**Providers**: Anthropic (vision), Google (vision + audio + video), OpenAI (vision + audio), Groq (audio), Deepgram (audio), MiniMax (audio).

**Pipeline**: Attachment → format detection → resize/transcode → provider-specific API → text transcription/description → injected into agent context.

**Corporate relevance**: Useful. Keep image understanding (screenshots, documents). Audio transcription is nice-to-have.

---

### 3.13 Routing & Sessions — 1,063 LOC

**What it does**: Maps incoming messages to agent sessions.

**Key concept — Session Key**:
```
channel:accountId:agentId:peerKind:peerId
e.g.: "telegram:default:main:dm:+1234567890"
      "slack:default:main:group:C012345"
```

**Routing resolution** (`resolve-route.ts`):
```typescript
type ResolveAgentRouteInput = {
  cfg: OpenClawConfig;
  channel: string;
  accountId?: string;
  peer?: { kind: "dm" | "group"; id: string };
  guildId?: string;    // Discord-specific
  teamId?: string;     // Teams-specific
};

// Resolution priority:
// 1. Explicit peer binding (config maps specific user/group to agent)
// 2. Guild/team binding
// 3. Account binding
// 4. Channel binding
// 5. Default agent
```

**Corporate relevance**: Essential pattern. This is how you route different Slack channels to different agent personas. Keep it, but simplify bindings.

---

### 3.14 Hooks System — 3,599 LOC

**What it does**: Lifecycle hooks that plugins/extensions can register.

**Hook events**: `before-tool-call`, `after-tool-call`, `message-received`, `session-start`, `session-end`, `compaction`, `gateway-start`, `gateway-stop`.

**Bundled hooks**: `boot-md` (inject bootstrap content), `command-logger` (log commands), `session-memory` (memory sync trigger).

**Corporate relevance**: Good for audit logging, compliance hooks. Keep the pattern.

---

### 3.15 TTS / Voice — 1,583 LOC

**What it does**: Text-to-speech via ElevenLabs or Edge TTS. Voice Wake for always-on listening.

**Corporate relevance**: Skip for now. Phase 5+ feature.

---

### 3.16 Mobile Apps (iOS / Android / macOS)

**iOS** (`apps/ios/`): SwiftUI app using the Observation framework. Pairs as a "node" to the gateway. Exposes camera, screen recording, canvas, voice wake.

**Android** (`apps/android/`): Kotlin + Jetpack Compose. Same node pairing pattern.

**macOS** (`apps/macos/`, `Swabble/`): Menu bar app for gateway control, voice wake, Canvas host.

**Corporate relevance**: Skip entirely for initial phases. WebChat + Slack integration covers corporate needs.

---

### 3.17 Skills Platform

**What it does**: Markdown-based prompt extensions.

**Skill structure**:
```
skills/github/
├── SKILL.md         — The prompt content (injected into system prompt)
└── config.json      — Skill metadata, required env vars
```

**Examples of bundled skills**: `github`, `slack`, `discord`, `coding-agent`, `obsidian`, `notion`, `trello`, `weather`, `spotify-player`, `1password`.

**How it works**: Skills are discovered → filtered by config → their SKILL.md content is concatenated into the system prompt before each agent turn.

**Corporate relevance**: Excellent for enterprise. Teams can write skills that customize the assistant's behavior for their domain (e.g., "jira-skill", "confluence-skill", "ci-cd-skill"). Keep this pattern.

---

### 3.18 Security Layer

**Key security patterns in OpenClaw**:

1. **DM Pairing**: Unknown senders must be approved via pairing code
2. **Allowlists**: Per-channel sender allowlists
3. **Tool Policy**: Allowlist/denylist of tools per session type
4. **Sandbox**: Docker isolation for non-main sessions
5. **Gateway Auth**: Token or password for Gateway access
6. **Secret scanning**: Pre-commit hooks for secret detection
7. **SSRF protection**: URL validation for web fetch/media tools
8. **External content sanitization**: Strip dangerous content from untrusted input

**Corporate relevance**: Security is critical for enterprise. You need:
- Authentication (SSO/OIDC instead of token)
- Authorization (RBAC, not just allowlists)
- Audit logging (every interaction logged)
- Tool policy (strict allowlists)
- Data classification (prevent sensitive data leakage)

---

## 4. Key Design Patterns

### 4.1 Adapter Pattern (Channels)
Every channel implements the same interface. Adding a new channel means implementing adapters, not modifying core logic. This is the most reusable pattern in the codebase.

### 4.2 JSON-RPC over WebSocket
The gateway uses a custom JSON-RPC protocol with typed schemas. This gives you: strong typing, easy introspection, and clean separation of concerns.

### 4.3 Session-Per-Conversation
Each conversation (DM, group, channel) gets its own session with isolated history. Sessions are persisted as JSONL files (append-only, easy to debug).

### 4.4 Dependency Injection via `createDefaultDeps()`
CLI and server code uses a DI pattern where all external dependencies (fs, config, runtime) are injected. Makes testing easy.

### 4.5 Config-Driven Everything
Almost every behavior is controlled via `openclaw.json`. No hardcoded behavior. This is perfect for enterprise where ops teams need to tune behavior without code changes.

### 4.6 Plugin + Extension Architecture
Clean separation between core (gateway + agent) and extensions (channels, tools). Extensions are npm packages with a standard contract.

### 4.7 Block Streaming with Channel-Aware Chunking
Long responses are split into message-sized chunks per channel limits. Each channel knows its own constraints (Discord: 2000 chars, Telegram: 4096, etc.).

### 4.8 Auth Profile Rotation
Multiple API keys/OAuth sessions with automatic failover. Resilient against rate limits and quota exhaustion.

---

## 5. What's Bloat vs. What's Essential

### Essential for a Corporate Work Assistant
| Component | Why |
|-----------|-----|
| Gateway (WS control plane) | Central control, auth, health |
| Channel abstraction | Multi-channel support |
| Agent runtime (simplified) | Core LLM interaction |
| Tool execution with policy | Controlled capabilities |
| Config system | Ops-friendly, auditable |
| Session management | Conversation state |
| Skills platform | Customizable behavior |
| Memory/RAG | Cross-conversation context |
| WebChat | Browser-based access |
| Hooks | Audit logging, compliance |
| CLI (subset) | Admin operations |

### Bloat for Corporate (can skip)
| Component | Why skip |
|-----------|----------|
| 15+ channel plugins | Start with Slack + WebChat + Teams |
| macOS/iOS/Android apps | Not needed for corporate |
| Browser control | High risk, low initial value |
| Voice/TTS/Voice Wake | Niche use case |
| Canvas/A2UI | Specialized visual workspace |
| Device pairing/nodes | Consumer feature |
| Tailscale integration | Use corporate VPN instead |
| iMessage/WhatsApp/Signal | Personal messaging, not corporate |
| ClawHub skill registry | Build internal registry instead |

---

## 6. Step-by-Step Build Plan: Corporate Work Assistant

### Phase 0: Foundation (Skeleton)
**Goal**: Runnable gateway with no channels, no agent. Just the bones.

**Build**:
- Express + WebSocket server with JSON-RPC protocol
- Token-based auth middleware
- Health endpoint (`/health`)
- Config loader (Zod-validated JSON)
- CLI entry point: `assistant gateway --port 18789`
- Subsystem logger (structured JSON logs)

**Test**: Gateway starts, accepts WS connections, responds to `health.get`.

**OpenClaw reference**: `src/gateway/server.impl.ts`, `src/gateway/protocol/`, `src/gateway/auth.ts`, `src/config/config.ts`

---

### Phase 1: Agent Runtime (Core Loop)
**Goal**: Send a message via WS, get an AI response back.

**Build**:
- LLM provider abstraction (start with OpenAI + Anthropic)
- System prompt construction (static AGENTS.md-style)
- Session persistence (JSONL append-only files)
- `chat.send` RPC method → agent turn → `chat.event` stream back
- Basic model selection (config-driven)
- Context window guard (trim old messages if too long)

**Test**: Connect via WS, send "Hello", get streamed response.

**OpenClaw reference**: `src/agents/pi-embedded-runner/`, `src/agents/model-selection.ts`, `src/config/sessions/`

---

### Phase 2: Tool Framework
**Goal**: Agent can execute tools (start with `web_search` and a simple `execute_command`).

**Build**:
- Tool definition interface (name, description, input schema, handler)
- Tool policy engine (allowlist per session type)
- Tool result formatting
- 2-3 starter tools:
  - `web_search` — fetch web content
  - `execute_command` — run approved shell commands
  - `read_file` / `write_file` — workspace file access

**Test**: Ask agent to "search the web for X" → tool call → result in response.

**OpenClaw reference**: `src/agents/tools/`, `src/agents/pi-tools.ts`, `src/agents/tool-policy.ts`

---

### Phase 3: WebChat UI
**Goal**: Browser-based chat interface.

**Build**:
- Simple React (or Lit) chat component
- WebSocket connection to gateway
- Message display with markdown rendering
- Input with send button
- Session selection (sidebar)
- Served from gateway HTTP server

**Test**: Open browser, chat with assistant.

**OpenClaw reference**: `ui/src/`

---

### Phase 4: First Channel — Slack
**Goal**: Assistant responds in Slack DMs and channels.

**Build**:
- Channel adapter interface (simplified from OpenClaw's 15+ adapters)
- Slack implementation using @slack/bolt
- Inbound: message → normalize → route → agent → reply
- Outbound: chunk + format for Slack
- Thread support
- Mention-based activation in channels

**Test**: Message bot in Slack, get response.

**OpenClaw reference**: `extensions/slack/`, `src/channels/plugins/types.plugin.ts`

---

### Phase 5: Routing & Multi-Agent
**Goal**: Different Slack channels route to different agent personas.

**Build**:
- Routing table: channel + workspace + channel_id → agent config
- Per-agent: different system prompts, tool allowlists, model preferences
- Agent config in main config file
- Session isolation per agent

**Test**: #engineering uses coding agent, #hr uses HR policy agent.

**OpenClaw reference**: `src/routing/`, `src/agents/agent-scope.ts`

---

### Phase 6: Skills Platform
**Goal**: Teams can customize agent behavior via markdown files.

**Build**:
- Skill loader: scan directory for SKILL.md files
- Skill config: required env vars, dependencies
- Skill injection into system prompt
- CLI: `assistant skills list|enable|disable`
- Starter skills: `jira`, `github`, `confluence`

**Test**: Enable "jira" skill → agent can interact with Jira.

**OpenClaw reference**: `src/agents/skills/`, `skills/`

---

### Phase 7: Memory / RAG
**Goal**: Assistant remembers past conversations and can search them.

**Build**:
- Embedding pipeline (OpenAI `text-embedding-3-small`)
- Vector storage (sqlite-vec or pgvector)
- Memory sync: after each conversation, extract + embed key facts
- Memory search tool: agent can search past conversations
- Automatic context injection: relevant memories added to system prompt

**Test**: Discuss a project → new conversation → "What did we decide about X?" → correct answer.

**OpenClaw reference**: `src/memory/`

---

### Phase 8: Microsoft Teams Channel
**Goal**: Same assistant in Teams.

**Build**:
- Teams channel adapter using Bot Framework
- Teams-specific formatting (Adaptive Cards)
- Teams auth (Azure AD app registration)

**OpenClaw reference**: `extensions/msteams/`

---

### Phase 9: Admin & Observability
**Goal**: Production-ready admin controls.

**Build**:
- Admin CLI: `assistant doctor`, `assistant config`, `assistant sessions`
- Web dashboard: active sessions, usage stats, health
- Structured logging (JSON) with correlation IDs
- Usage tracking (tokens, cost per user/team)
- Audit log (every interaction logged with who/what/when)

**OpenClaw reference**: `src/cli/`, `src/gateway/server-methods/usage.ts`

---

### Phase 10: Security Hardening
**Goal**: Enterprise-grade security.

**Build**:
- OIDC/SSO authentication (replace token auth)
- RBAC: admin, user, viewer roles
- Tool execution approval workflow (human-in-the-loop for dangerous ops)
- Data classification: PII detection, sensitive data redaction
- Rate limiting per user
- Webhook signature verification

**OpenClaw reference**: `src/security/`, `src/gateway/exec-approval-manager.ts`

---

## 7. Phase Dependency Graph

```
Phase 0: Foundation ─────────────────────────────────────┐
    │                                                     │
    ▼                                                     │
Phase 1: Agent Runtime ──────────────────────────────┐   │
    │                                                 │   │
    ├──────────────────┐                             │   │
    ▼                  ▼                             │   │
Phase 2: Tools    Phase 3: WebChat                   │   │
    │                  │                             │   │
    ├──────────────────┤                             │   │
    ▼                  │                             │   │
Phase 4: Slack ────────┘                             │   │
    │                                                 │   │
    ▼                                                 │   │
Phase 5: Routing & Multi-Agent                       │   │
    │                                                 │   │
    ├──────────────────┐                             │   │
    ▼                  ▼                             │   │
Phase 6: Skills   Phase 7: Memory/RAG                │   │
    │                  │                             │   │
    └──────────────────┤                             │   │
                       ▼                             │   │
                 Phase 8: Teams                      │   │
                       │                             │   │
                       ▼                             │   │
                 Phase 9: Admin & Observability ◄────┘   │
                       │                                  │
                       ▼                                  │
                 Phase 10: Security Hardening ◄───────────┘
```

### Estimated Effort Per Phase

| Phase | Effort | Can demo after? |
|-------|--------|-----------------|
| 0: Foundation | 2-3 days | Yes (health endpoint) |
| 1: Agent Runtime | 3-5 days | Yes (WS chat) |
| 2: Tools | 2-3 days | Yes (agent uses tools) |
| 3: WebChat | 2-3 days | Yes (browser chat) |
| 4: Slack | 2-3 days | Yes (Slack bot) |
| 5: Multi-Agent | 1-2 days | Yes (different bots) |
| 6: Skills | 2-3 days | Yes (custom behavior) |
| 7: Memory/RAG | 3-4 days | Yes (remembers context) |
| 8: Teams | 2-3 days | Yes (Teams bot) |
| 9: Admin | 3-4 days | Yes (dashboard) |
| 10: Security | 3-5 days | Yes (SSO login) |

**Total: ~25-38 working days for a production-ready corporate assistant.**

---

## 8. Blueprint Comparison Matrix

This matrix maps each build phase to the exact OpenClaw subsystems and files you should study before implementing. It shows what OpenClaw does, what you'd build instead, and what complexity you're shedding.

### Phase 0: Foundation (Gateway Skeleton)

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **HTTP + WS Server** | Express 5 + `ws` library. `src/gateway/server.impl.ts` (663 LOC) wires 20+ subsystems at boot. `src/gateway/server/http-listen.ts` handles HTTP. `src/gateway/server/ws-connection.ts` manages WS lifecycle. | Express + `ws`. Single file ~150 LOC. Wire: auth, health, RPC handler. | Tailscale exposure, Bonjour/mDNS discovery, Canvas host, TLS self-cert, restart sentinel |
| **Protocol** | Custom JSON-RPC with TypeBox schemas + AJV validation. `src/gateway/protocol/schema.ts` defines 60+ methods. `src/gateway/protocol/index.ts` exports all param/result types. `src/gateway/server-methods-list.ts` registers handlers. | Same JSON-RPC pattern but with ~8 methods: `health.get`, `chat.send`, `chat.abort`, `sessions.list`, `sessions.patch`, `config.get`, `config.set`, `connect`. Use Zod instead of TypeBox. | 50+ RPC methods (agents.*, cron.*, nodes.*, browser.*, skills.*, wizard.*, etc.) |
| **Auth** | `src/gateway/auth.ts` — token or password auth on WS upgrade + HTTP. `src/gateway/device-auth.ts` — device pairing auth. `src/gateway/origin-check.ts` — CORS origin validation. | Token auth only. Single middleware. ~40 LOC. | Device auth, password mode, Tailscale identity headers, origin allowlisting |
| **Config** | `src/config/config.ts` — load/validate/migrate. `src/config/schema.ts` + `src/config/zod-schema.ts` — 100+ key schema. `src/config/io.ts` — read/write. `src/config/legacy.migrations.ts` — 3 migration files. `src/config/env-vars.ts` — env override. `src/config/types.*.ts` — 20+ type files. | Single Zod schema, ~20 keys. Load from JSON, env override, validate, hot-reload on file change. ~200 LOC total. | Legacy migrations, env substitution engine, Nix mode, 80+ config keys, config patch protocol, merge-config, field metadata, UI hints |
| **Logging** | `src/logging/subsystem.ts` — tslog-based subsystem loggers with child contexts. `src/logging/diagnostic.ts` — diagnostic heartbeat. | `pino` or `tslog` with subsystem prefixes. ~30 LOC setup. | Diagnostic heartbeat, OpenTelemetry extension, verbose log levels |
| **Health** | `src/gateway/server/health-state.ts` — cached health snapshots with versioning. `src/gateway/probe.ts` — deep health probe. | Simple `/health` endpoint returning `{ status, uptime, version }`. ~20 LOC. | Health versioning, presence versioning, deep channel probes, memory/disk stats |

**Study order**: `server.impl.ts` (skim the boot sequence) → `protocol/schema.ts` (understand method registration) → `auth.ts` (auth pattern) → `config/config.ts` (config loading)

**Complexity reduction**: ~70% less code. OpenClaw Gateway is ~26,860 LOC. Your Phase 0 skeleton: ~500 LOC.

---

### Phase 1: Agent Runtime (Core Loop)

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **LLM Providers** | `src/agents/models-config.ts` — provider discovery + config. `src/agents/models-config.providers.ts` — 10+ providers (Anthropic, OpenAI, Google, Bedrock, OpenRouter, Ollama, GitHub Copilot, Chutes, Venice, Together). `src/agents/auth-profiles/` — OAuth token rotation, cooldowns, usage tracking. `src/agents/model-auth.ts` — auth mode resolution. | 2 providers: OpenAI + Anthropic. Direct SDK usage. API key from config. ~100 LOC per provider. | 8+ providers, OAuth token rotation, auth profiles, cooldowns, Bedrock/OpenRouter/Copilot, provider health scoring |
| **Agent Loop** | `src/agents/pi-embedded-runner/run.ts` — main agent turn. `src/agents/pi-embedded-runner/system-prompt.ts` — prompt construction from templates + skills + context. `src/agents/pi-embedded-runner/history.ts` — session history loading. `src/agents/pi-embedded-runner/model.ts` — runtime model resolution. `src/agents/pi-embedded-subscribe.ts` — stream subscription + block chunking. | Single `runAgentTurn(sessionId, message)` function. Build prompt, call LLM, stream response, persist. ~300 LOC. | Overflow compaction retries, Google turn sanitization, cache TTL, lane concurrency, extension hooks, CLI runner mode |
| **Session Persistence** | `src/config/sessions/transcript.ts` — JSONL append. `src/config/sessions/store.ts` — session metadata store with pruning. `src/config/sessions/paths.ts` — file path resolution. `src/agents/session-file-repair.ts` — corrupt file recovery. `src/agents/session-write-lock.ts` — concurrent write protection. | JSONL append-only files. One file per session. ~80 LOC for read/write/trim. | Write locks, file repair, metadata store, pruning, slug generation, transcript events |
| **Model Selection** | `src/agents/model-selection.ts` — per-session override, per-agent default, global fallback. `src/agents/model-fallback.ts` — automatic failover on errors. `src/agents/model-catalog.ts` — catalog of known models with capabilities. `src/agents/model-compat.ts` — cross-model compatibility. | Config-driven: `{ defaultModel, agents: { <id>: { model } } }`. No failover initially. ~40 LOC. | Model catalog, capability detection, failover chain, fuzzy matching, directive-based switching |
| **Context Management** | `src/agents/context-window-guard.ts` — token counting + trim. `src/agents/compaction.ts` — LLM-based conversation summarization. `src/agents/pi-extensions/context-pruning.ts` — aggressive pruning. | Simple: count messages, drop oldest when > N. ~30 LOC. | LLM compaction, token-precise counting, per-model limits, compaction retries |
| **Streaming** | `src/agents/pi-embedded-subscribe.ts` — stream processing with block detection. `src/agents/pi-embedded-block-chunker.ts` — paragraph-aware chunking. `src/auto-reply/reply/block-reply-pipeline.ts` — coalescing + timing. | Forward SSE chunks from LLM SDK to WS client. ~50 LOC. | Block detection, paragraph splitting, fence-block reopening, coalescing timer, reply tags |

**Study order**: `pi-embedded-runner/run.ts` (core loop) → `pi-embedded-runner/system-prompt.ts` (prompt building) → `pi-embedded-subscribe.ts` (stream handling) → `config/sessions/transcript.ts` (persistence)

**Complexity reduction**: ~80% less. OpenClaw Agent is ~48,277 LOC. Your Phase 1: ~600 LOC.

---

### Phase 2: Tool Framework

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **Tool Interface** | `src/agents/pi-tools.schema.ts` — tool definition schema. `src/agents/pi-tools.ts` — tool registry, ~40 tools registered. `src/agents/pi-tool-definition-adapter.ts` — adapt tool schemas per LLM provider. `src/agents/pi-tools.types.ts` — TypeScript types. | `{ name, description, inputSchema: ZodSchema, handler: (input) => Promise<string> }`. ~30 LOC interface. | Provider-specific schema adaptation, tool call ID management, SDK tool splitting |
| **Tool Policy** | `src/agents/tool-policy.ts` — allowlist/denylist per session type + agent + sandbox. `src/agents/tool-policy.conformance.ts` — policy validation. `src/agents/sandbox/tool-policy.ts` — sandbox-specific policy. `src/agents/pi-tools.policy.ts` — runtime policy enforcement. | Simple allowlist: `{ tools: { allow: ["web_search", "read_file"] } }` per agent. ~50 LOC. | Sandbox policy, conformance checking, plugin-only allowlists, dynamic policy mutation |
| **Web Search** | `src/agents/tools/web-search.ts` — Brave/Perplexity/Google search. `src/agents/tools/web-fetch.ts` — URL fetching with Readability. `src/agents/tools/web-fetch-utils.ts` — SSRF protection. `src/agents/tools/web-shared.ts` — shared web helpers. | Single `web_search` tool using one provider (e.g., Brave or Perplexity). ~80 LOC. | Multi-provider search, Readability extraction, SSRF allowlist, Firecrawl integration |
| **Command Execution** | `src/agents/bash-tools.exec.ts` — PTY-based execution with timeout. `src/agents/bash-tools.process.ts` — background process management. `src/agents/bash-process-registry.ts` — process tracking. `src/agents/bash-tools.shared.ts` — shared helpers. | Simple `child_process.exec()` with timeout + output capture. Allowlisted commands only. ~60 LOC. | PTY support, background processes, process registry, send-keys, approval IDs |
| **File Operations** | `src/agents/pi-tools.read.ts` — file read with size limits. Workspace path resolution. | `read_file` / `write_file` with path validation (stay within workspace). ~40 LOC. | Glob patterns, multi-file read, workspace path security checks |

**Study order**: `pi-tools.ts` (registry pattern) → `tools/web-search.ts` (tool implementation example) → `tool-policy.ts` (policy pattern) → `bash-tools.exec.ts` (exec pattern)

**Complexity reduction**: ~85% less. OpenClaw has 20+ tools across ~5,000 LOC. Your Phase 2: ~300 LOC for 3 tools.

---

### Phase 3: WebChat UI

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **Framework** | `ui/src/` — Lit 3.x Web Components. `ui/src/ui/app.ts` — main app controller. `ui/src/ui/app-render.ts` — render logic. `ui/src/ui/app-chat.ts` — chat controller. `ui/src/ui/chat/` — chat message components. | React (your team's stack). Single-page chat app. | Lit dependency, Web Components, custom element lifecycle |
| **WS Connection** | `ui/src/ui/gateway.ts` — WS client with reconnect, auth, event routing. | Simple WS client with reconnect + JSON-RPC. ~80 LOC. | Device identity, settings sync, polling fallback |
| **Chat Rendering** | `ui/src/ui/markdown.ts` — markdown-it rendering. `ui/src/ui/chat/` — message bubbles, tool output, streaming indicators. `ui/src/ui/app-scroll.ts` — scroll management. | React components: `<ChatMessage>`, `<ToolOutput>`, `<StreamingIndicator>`. ~200 LOC. | Focus mode, theme transitions, tool display JSON, screenshot comparison |
| **Config UI** | `ui/src/ui/components/` — config editor, forms, navigation. `ui/src/ui/controllers/` — state management. `ui/src/ui/views/` — full page views. | Skip entirely for Phase 3. Admin via CLI. | Full config editor, multi-view navigation, session management UI |

**Study order**: `ui/src/ui/gateway.ts` (WS client) → `ui/src/ui/app-chat.ts` (chat logic) → `ui/src/ui/markdown.ts` (rendering)

**Complexity reduction**: ~90% less. OpenClaw UI is ~25,997 LOC. Your Phase 3 WebChat: ~500 LOC.

---

### Phase 4: Slack Channel

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **Channel Interface** | `src/channels/plugins/types.plugin.ts` — 15+ adapter interfaces (`ChannelPlugin` type). `src/channels/plugins/types.core.ts` — core types. `src/channels/plugins/types.adapters.ts` — adapter contracts. | Simplified: `{ id, setup, teardown, onMessage, sendMessage, capabilities }`. 5-6 adapters max. ~60 LOC interface. | 10+ adapter interfaces (pairing, heartbeat, resolver, directory, elevated, streaming, etc.) |
| **Slack Implementation** | `extensions/slack/src/channel.ts` — full Slack channel plugin. `extensions/slack/src/runtime.ts` — Slack runtime context. `src/channels/plugins/slack.actions.ts` — Slack-specific agent actions. Uses `@slack/bolt`. | Slack adapter: listen for messages, send replies, handle threads. ~200 LOC. | Slack actions tool, app-level tokens, slash commands, interactive components |
| **Message Normalization** | `src/auto-reply/envelope.ts` — channel-agnostic envelope. `src/channels/plugins/normalize/` — per-channel normalization. `src/channels/sender-identity.ts` — sender resolution. | Simple `{ channel, sender, text, threadId?, attachments? }` envelope. ~30 LOC. | Sender identity resolution, conversation labels, location payloads |
| **Reply Routing** | `src/auto-reply/reply/route-reply.ts` — route responses back. `src/auto-reply/chunk.ts` — channel-aware chunking. `src/channels/plugins/outbound/` — outbound formatting. | Chunk by channel limit (Slack: 3000 chars), send via Slack SDK. ~60 LOC. | Multi-channel fan-out, reply tags, block reply coalescing |
| **Mention/Activation** | `src/channels/mention-gating.ts` — @mention detection. `src/auto-reply/group-activation.ts` — activation modes. | Simple: respond in DMs always, in channels only when @mentioned. ~30 LOC. | Activation mode toggling, reply-to-thread detection, custom mention patterns |

**Study order**: `channels/plugins/types.plugin.ts` (interface) → `extensions/slack/` (implementation) → `auto-reply/envelope.ts` (normalization) → `auto-reply/chunk.ts` (chunking)

**Complexity reduction**: ~75% less. OpenClaw Slack + channel abstraction: ~3,000 LOC. Your Phase 4: ~400 LOC.

---

### Phase 5: Routing & Multi-Agent

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **Route Resolution** | `src/routing/resolve-route.ts` — 5-level priority resolution (peer → guild → account → channel → default). `src/routing/bindings.ts` — config-driven binding table. `src/routing/session-key.ts` — composite session key construction. | Simple lookup table: `{ "slack:C012345": "engineering-agent", "slack:*": "default-agent" }`. ~80 LOC. | Guild/team bindings, parent peer inheritance, account-level routing |
| **Agent Scope** | `src/agents/agent-scope.ts` — per-agent workspace, sessions dir, identity. `src/agents/agent-paths.ts` — path resolution. `src/config/types.agents.ts` — multi-agent config schema. | Agent config: `{ id, model, systemPrompt, tools, skills }`. Agents share workspace. ~60 LOC. | Per-agent workspaces, agent-specific sandbox config, agent creation/deletion RPC |
| **Session Isolation** | `src/gateway/server-session-key.ts` — session key for each run. `src/gateway/sessions-resolve.ts` — resolve session from route. | Session key = `agentId:channelId:peerId`. Separate JSONL per session. Already built in Phase 1. | Wizard sessions, session patches, presence tracking |

**Study order**: `routing/resolve-route.ts` (route logic) → `routing/session-key.ts` (key format) → `agents/agent-scope.ts` (agent isolation)

**Complexity reduction**: ~70% less. OpenClaw Routing+Agents config: ~2,000 LOC. Your Phase 5: ~200 LOC.

---

### Phase 6: Skills Platform

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **Skill Loading** | `src/agents/skills/workspace.ts` — scan workspace for skills. `src/agents/skills/bundled-dir.ts` — bundled skills. `src/agents/skills/frontmatter.ts` — YAML frontmatter parsing. `src/agents/skills/serialize.ts` — skill → prompt text. `src/agents/skills/config.ts` — skill config resolution. | Scan `skills/` directory for `SKILL.md` files. Parse optional YAML frontmatter for metadata. ~100 LOC. | Bundled vs. managed vs. workspace tiers, remote skill registry (ClawHub), skill install gating |
| **Prompt Injection** | `src/agents/skills.ts` — `buildWorkspaceSkillsPrompt()` concatenates skill content into system prompt. `src/agents/skills/refresh.ts` — hot-reload on file change. | Concatenate enabled skills into system prompt. Simple `skills.forEach(s => prompt += s.content)`. ~20 LOC. | Skill deduplication, allowlist filtering, managed skill sync, skill description summarization |
| **Skill Management** | `src/agents/skills-install.ts` — install from ClawHub. `src/agents/skills-status.ts` — skill status reporting. `src/cli/skills-cli.ts` — CLI for skill management. | CLI: `assistant skills list\|enable\|disable`. Config-driven enable/disable. ~80 LOC. | ClawHub registry, remote install, plugin-provided skills, skill change listeners |

**Study order**: `agents/skills.ts` (main logic) → `agents/skills/workspace.ts` (loading) → `skills/github/SKILL.md` (example skill)

**Complexity reduction**: ~80% less. OpenClaw Skills: ~3,500 LOC. Your Phase 6: ~250 LOC.

---

### Phase 7: Memory / RAG

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **Embeddings** | `src/memory/embeddings.ts` — provider abstraction. `src/memory/embeddings-openai.ts`, `embeddings-gemini.ts`, `embeddings-voyage.ts` — 3 providers. `src/memory/batch-openai.ts` — batched embedding calls. `src/memory/embedding-model-limits.ts` — per-model token limits. | Single provider: OpenAI `text-embedding-3-small`. Direct SDK call. ~50 LOC. | Multi-provider, batching, token limits, local llama embeddings |
| **Vector Store** | `src/memory/sqlite-vec.ts` — sqlite-vec integration. `src/memory/sqlite.ts` — SQLite connection management. `src/memory/hybrid.ts` — hybrid search (vector + keyword). | sqlite-vec (same as OpenClaw) or pgvector if you prefer Postgres. ~100 LOC. | Hybrid search (start with vector-only), atomic reindex, cache keys |
| **Memory Manager** | `src/memory/manager.ts` — sync, search, reindex. `src/memory/manager-search.ts` — search execution. `src/memory/session-files.ts` — extract memories from transcripts. `src/memory/sync-session-files.ts` — periodic sync. | Simple: after each conversation, extract key facts → embed → store. Search on demand. ~150 LOC. | Periodic sync scheduler, reindex, batch processing, fingerprint-based dedup |
| **Memory Tool** | `src/agents/tools/memory-tool.ts` — agent-facing search tool with citation formatting. | `memory_search` tool: query → vector search → return top N results. ~40 LOC. | Citation formatting, error handling, QMD query parser |

**Study order**: `memory/manager.ts` (architecture) → `memory/sqlite-vec.ts` (storage) → `memory/embeddings.ts` (embedding abstraction) → `agents/tools/memory-tool.ts` (tool interface)

**Complexity reduction**: ~75% less. OpenClaw Memory: ~7,236 LOC. Your Phase 7: ~400 LOC.

---

### Phase 8: Microsoft Teams Channel

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **Teams Adapter** | `extensions/msteams/src/channel.ts` — full Teams channel plugin using Bot Framework. `extensions/msteams/src/runtime.ts` — Teams runtime. | Teams adapter implementing your simplified channel interface. Bot Framework SDK. ~250 LOC. | Complex threading, Adaptive Cards (start with plain text), proactive messaging |
| **Auth** | Azure AD app registration, Bot Framework connector auth. | Same — this is non-negotiable for Teams. | — |

**Study order**: `extensions/msteams/` (full implementation) → your Slack adapter (reuse patterns)

**Complexity reduction**: ~50% less (Teams is inherently complex). OpenClaw Teams: ~1,500 LOC. Your Phase 8: ~300 LOC.

---

### Phase 9: Admin & Observability

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **Usage Tracking** | `src/gateway/server-methods/usage.ts` — per-session token/cost tracking. `src/agents/usage.ts` — usage calculation. `src/utils/usage-format.ts` — cost estimation. | Per-user/team token counting + cost estimation. Store in DB. ~150 LOC. | Per-auth-profile tracking, session-level granularity, usage footer formatting |
| **Admin CLI** | `src/cli/` — 30+ subcommands across 20+ files. `src/cli/program/` — command registration framework. | 5 commands: `gateway`, `config`, `doctor`, `sessions`, `skills`. ~300 LOC. | 25+ niche commands (browser, nodes, cron, pairing, update, etc.) |
| **Dashboard** | `ui/src/ui/views/` — full control UI with config editor, session viewer, channel status. | Simple React dashboard: active sessions, usage chart, health status. ~400 LOC. | Config editor UI, full session viewer, channel management UI |
| **Doctor/Health** | `src/commands/doctor/` — migration checks, config validation, channel probing. | Simple health checks: config valid? LLM reachable? Channels connected? ~100 LOC. | Legacy migration detection, Nix mode checks, 20+ diagnostic checks |

**Study order**: `gateway/server-methods/usage.ts` (usage pattern) → `cli/program/` (CLI framework) → `commands/doctor/` (health checks)

**Complexity reduction**: ~80% less. OpenClaw Admin: ~10,000 LOC. Your Phase 9: ~1,000 LOC.

---

### Phase 10: Security Hardening

| Aspect | OpenClaw | Your Equivalent | What to Drop |
|--------|----------|-----------------|-------------|
| **Authentication** | `src/gateway/auth.ts` — token/password. `src/gateway/device-auth.ts` — device pairing. | OIDC/SSO via corporate IdP (Okta, Azure AD). ~200 LOC. | Token/password auth (replaced by SSO), device pairing |
| **Authorization** | `src/channels/allowlists/` — per-channel allowlists. `src/auto-reply/reply/commands-allowlist.ts` — command access control. | RBAC: admin (full), user (chat + limited tools), viewer (read-only). ~150 LOC. | Channel-level allowlists (replaced by RBAC) |
| **Tool Approval** | `src/gateway/exec-approval-manager.ts` — approval queue. `src/gateway/server-methods/exec-approval.ts` — approval RPC methods. `src/auto-reply/reply/commands-approve.ts` — approve command. | Human-in-the-loop for dangerous tools (e.g., `execute_command`). Approval via Slack DM to admin. ~200 LOC. | Approval manager complexity (use simpler queue) |
| **Audit** | `src/hooks/bundled/command-logger/` — command logging hook. Transcript persistence. | Every interaction logged: who, what, when, tool calls, responses. Structured JSON. ~100 LOC. | — (you'll want more than OpenClaw here) |
| **Content Safety** | `src/security/external-content.ts` — sanitize untrusted input. `src/security/audit.ts` — security audit checks. `src/security/skill-scanner.ts` — skill content scanning. | PII detection in outbound responses. Input sanitization. ~100 LOC. | Skill scanning, SSRF protection (simpler URL allowlist) |

**Study order**: `gateway/auth.ts` (auth pattern) → `gateway/exec-approval-manager.ts` (approval pattern) → `security/` (security checks)

**Complexity reduction**: ~60% less code, but **more corporate-appropriate** (SSO > tokens, RBAC > allowlists). OpenClaw Security: ~3,000 LOC. Your Phase 10: ~800 LOC.

---

### Summary: Your Codebase vs. OpenClaw

| Phase | OpenClaw LOC (approx.) | Your LOC (approx.) | Reduction | Key Insight |
|-------|----------------------|-------------------|-----------|-------------|
| 0: Foundation | 26,860 (full Gateway) | ~500 | 98% | Drop discovery, Tailscale, Canvas host, 50+ RPC methods |
| 1: Agent Runtime | 48,277 (full Agents) | ~600 | 99% | Drop 8 providers, sandbox, CLI runners, compaction |
| 2: Tools | ~5,000 (20+ tools) | ~300 | 94% | 3 tools instead of 20+, no PTY, no browser |
| 3: WebChat | 25,997 (full UI) | ~500 | 98% | Chat only, no control UI, React instead of Lit |
| 4: Slack | ~3,000 (Slack + channels) | ~400 | 87% | 5 adapters not 15, no pairing, no actions tool |
| 5: Multi-Agent | ~2,000 (routing + agents) | ~200 | 90% | Simple lookup table, no guild/team bindings |
| 6: Skills | ~3,500 (skills system) | ~250 | 93% | No ClawHub, no managed skills, no install gating |
| 7: Memory | 7,236 (full memory) | ~400 | 94% | 1 embedding provider, no hybrid search initially |
| 8: Teams | ~1,500 (Teams ext) | ~300 | 80% | Teams is inherently complex, less to cut |
| 9: Admin | ~10,000 (CLI + dashboard) | ~1,000 | 90% | 5 CLI commands not 30, minimal dashboard |
| 10: Security | ~3,000 (security) | ~800 | 73% | SSO replaces tokens, RBAC replaces allowlists |
| **TOTAL** | **~270,000** | **~5,250** | **98%** | **Corporate-focused, zero bloat** |

The total for a fully-featured corporate work assistant: **~5,250 LOC** — about 2% of OpenClaw's codebase, covering 100% of what matters for enterprise adoption.

---

*Analysis generated from OpenClaw repository (commit: openclaw-main, ~270k LOC, 5,268 files)*
