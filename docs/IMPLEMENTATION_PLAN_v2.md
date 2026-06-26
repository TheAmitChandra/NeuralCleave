# CortexFlow v2 — Personal AI Assistant Implementation Plan

**Date:** 2026-06-07  
**Goal:** Rebuild CortexFlow as a superior version of OpenClaw — a personal AI assistant that works across all major messaging platforms, with better memory, smarter LLM routing, voice, and a first-class web UI.  
**Reference:** OpenClaw (https://github.com/openclaw/openclaw) — 377k stars, TypeScript/Node.js monorepo  
**Enterprise code:** Mirrored to https://github.com/TheAmitChandra/CortexFlow-Enterprise  

---

## 1. Vision

> **"One intelligent AI, everywhere you communicate — smarter memory, better routing, and voice that actually works."**

CortexFlow v2 is a **local-first personal AI assistant gateway** that:
- Connects a single AI agent to all major messaging platforms (WhatsApp, Telegram, Discord, Slack, Email, and more)
- Provides hierarchical multi-tier memory (short-term → semantic → persistent) — not just a flat vector store
- Routes each task to the optimal LLM provider (Claude, Gemini, GPT-4, local Ollama) automatically
- Works offline-capable with a local Ollama fallback
- Ships with a polished web UI + Tauri desktop app
- Runs as a local daemon (privacy-first, no cloud required) OR cloud-hosted

**How it beats OpenClaw:**

| Dimension | OpenClaw | CortexFlow v2 |
|---|---|---|
| Memory | LanceDB only (flat vector) | 3-tier: Redis TTL + Qdrant semantic + SQLite long-term |
| LLM routing | Manual model config | Auto task-aware routing: Claude for reasoning, Gemini Flash for speed, Ollama for privacy |
| Voice | macOS/iOS wake-word only | Cross-platform STT (Whisper) + TTS (ElevenLabs / Kokoro / system) |
| Channel adapters | 25+ (Node.js) | 10 priority channels (Python, richer AI hooks) |
| Web UI | Static WebChat widget | Full Next.js dashboard: memory explorer, conversation history, metrics |
| Desktop app | Platform-native Swift/Kotlin | Tauri (cross-platform: Windows, macOS, Linux) |
| Plugin API | In-process, no sandboxing | Sandboxed subprocess plugins with typed Python SDK |
| Config | Complex YAML (~50 keys) | Simple TOML with smart defaults (works in 3 lines) |
| Observability | stdout logs only | Structured logs + Prometheus metrics + trace IDs |
| Hallucination | None | Reflection engine: quality scorer + self-correction loop |

---

## 2. Architecture Decision

### Stack

| Layer | Technology | Why |
|---|---|---|
| **Gateway daemon** | Python 3.12 + FastAPI + WebSocket | AI ecosystem native; reuse existing code |
| **Channel adapters** | Python async (per-channel package) | Unified language, better AI hooks |
| **LLM routing** | Existing ModelRouter (adapted from enterprise) | Already built, task-aware |
| **Memory** | Redis + Qdrant + SQLite (drop Neo4j/PostgreSQL for personal use) | Simpler stack, still 3-tier |
| **Web UI** | Next.js 14 (adapted from enterprise) | Already built |
| **Desktop app** | Tauri v2 (wraps Next.js web UI) | Single codebase, cross-platform |
| **Voice STT** | faster-whisper (local) | Free, private, fast |
| **Voice TTS** | ElevenLabs API + Kokoro (local fallback) | Cloud quality + offline fallback |
| **Config** | TOML + pydantic-settings | Type-safe, simpler than YAML |
| **Tests** | pytest + pytest-asyncio | Existing test suite |

### Why Python over TypeScript (OpenClaw's choice)

1. Python has the best AI/ML library ecosystem (transformers, sentence-transformers, faster-whisper, etc.)
2. The existing codebase is Python — reuse instead of rewrite
3. Channel adapters in Python can embed mini LLM calls per message (e.g., smart summarization before storing to memory)
4. Easier integration with local models (Ollama Python SDK, llama-cpp-python, etc.)

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    CortexFlow v2 Gateway                        │
│                  (FastAPI + WebSocket daemon)                   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │  Channel     │  │  Session     │  │   Model Router      │  │
│  │  Manager     │  │  Manager     │  │  (task-aware LLM)   │  │
│  │              │  │              │  │  Claude / Gemini /  │  │
│  │ WhatsApp     │  │ Per-channel  │  │  DeepSeek / Ollama  │  │
│  │ Telegram     │  │ isolation    │  │                     │  │
│  │ Discord      │  │              │  └─────────────────────┘  │
│  │ Slack        │  └──────────────┘                           │
│  │ Email        │                  ┌─────────────────────────┐ │
│  │ SMS          │  ┌──────────────┐│  Memory Pipeline        │ │
│  │ Matrix       │  │  Cognitive   ││  ┌──────────────────┐  │ │
│  │ IRC          │  │  Pipeline    ││  │ Redis (TTL/ctx)  │  │ │
│  │ + more       │  │  plan→exec   ││  │ Qdrant (vector)  │  │ │
│  └──────────────┘  │  →validate   ││  │ SQLite (persist) │  │ │
│                    │  →reflect    ││  └──────────────────┘  │ │
│  ┌──────────────┐  └──────────────┘└─────────────────────────┘ │
│  │  Voice       │                                               │
│  │  STT:Whisper │  ┌──────────────────────────────────────┐    │
│  │  TTS:Kokoro  │  │  Plugin System (subprocess-sandboxed)│    │
│  └──────────────┘  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
         ↑  WebSocket API (ws://127.0.0.1:7432)
┌────────┴──────────────────────┐
│  Clients                      │
│  - Next.js Web UI             │
│  - Tauri Desktop App          │
│  - CLI tool (cortex)          │
│  - REST API (external apps)   │
└───────────────────────────────┘
```

---

## 3. What to Keep from Existing CortexFlow (Enterprise)

The enterprise codebase has significant reusable infrastructure. **Do NOT rewrite what works.**

| Module | Keep? | Changes needed |
|---|---|---|
| `app/core/model_router/` | ✅ Keep all | Remove enterprise token budget enforcement; keep routing + fallback |
| `app/core/memory/retrieval.py` | ✅ Keep | Replace PostgreSQL with SQLite; drop Neo4j graph tier |
| `app/core/memory/short_term.py` | ✅ Keep | No changes |
| `app/core/memory/episodic.py` | ✅ Keep | No changes |
| `app/core/memory/long_term.py` | 🔄 Adapt | SQLite instead of PostgreSQL + SQLAlchemy |
| `app/core/reflection/engine.py` | ✅ Keep | Simplify — remove enterprise escalation, keep quality + retry |
| `app/core/observability/` | ✅ Keep all | Add per-channel metrics labels |
| `app/core/agent_runtime/agent.py` | 🔄 Adapt | Simplify states; add channel_id context |
| `app/core/security/zero_trust.py` | ❌ Remove | Too complex for personal use; replace with simple API key auth |
| `app/core/governance/` | ❌ Remove | Enterprise-only |
| `app/core/security/audit.py` | 🔄 Simplify | Keep basic audit log; remove SHA-256 tamper detection |
| `app/workers/celery_app.py` | ❌ Remove | Celery is overkill for single-user; use asyncio tasks |
| `app/api/v1/approvals.py` | ❌ Remove | Personal use doesn't need approval workflows |
| `frontend/src/app/(dashboard)/` | ✅ Keep | Adapt pages for personal use |
| `deploy/docker-compose.yml` | 🔄 Simplify | Remove Neo4j, Celery; add Qdrant |

---

## 4. What to Build New

### 4.1 Channel Adapters

Each adapter is a standalone Python async class in `cortexflow/channels/`:

**Priority 1 (build first — biggest user impact):**
1. **Telegram** — python-telegram-bot v21 (async) — easiest to integrate
2. **Discord** — discord.py — large developer audience
3. **Slack** — slack-sdk — enterprise crossover users
4. **WhatsApp** — whatsapp-web.py or Baileys via subprocess — largest user base
5. **Email** — aiosmtplib + aioimaplib (IMAP polling + SMTP send)

**Priority 2:**
6. **SMS** — Twilio Python SDK
7. **Matrix** — matrix-nio (async)
8. **IRC** — pydle or raw asyncio socket
9. **Signal** — signal-cli wrapper
10. **Webhook** — Generic HTTP POST receiver (for custom integrations)

**Adapter Interface:**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class InboundMessage:
    channel: str           # "telegram" | "discord" | etc.
    sender_id: str         # platform user ID
    sender_name: str
    text: str | None
    attachments: list[Attachment]
    thread_id: str | None
    timestamp: float

class ChannelAdapter(ABC):
    channel_id: str        # "telegram" | "discord" | etc.

    @abstractmethod
    async def connect(self, config: dict) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def send(self, target: str, text: str, reply_to: str | None = None) -> None: ...

    @abstractmethod
    async def on_message(self, handler: Callable[[InboundMessage], Awaitable[None]]) -> None: ...

    def get_config_schema(self) -> dict: ...  # JSON Schema for config UI
```

### 4.2 Voice Layer

**STT (Speech → Text):**
- `faster-whisper` — runs locally, no API needed, GPU optional
- Auto-detect language
- Stream transcription (real-time chunks as user speaks)
- WebSocket endpoint: `ws://host/voice/stream`

**TTS (Text → Speech):**
- **Cloud**: ElevenLabs API (high quality, configurable voice)
- **Local fallback**: Kokoro-82M (open-source, surprisingly good, no API key)
- **System fallback**: OS TTS (pyttsx3 on Windows, say on macOS)
- Auto-select based on config + network availability

**Wake Word (stretch goal):**
- OpenWakeWord (open-source, runs locally) — cross-platform unlike OpenClaw's macOS-only

### 4.3 Tauri Desktop App

- Wraps the existing Next.js web UI in a Tauri v2 shell
- System tray icon with notification badges per channel
- Native notifications when messages arrive
- Hotkey: `Ctrl+Shift+Space` to open/focus
- Single binary distribution (no Node.js required)
- Auto-updater

### 4.4 CLI Tool (`cortex`)

```
cortex start              # start gateway daemon
cortex stop               # stop daemon
cortex status             # show connected channels + active sessions
cortex message "text"     # send message to primary agent
cortex channels list      # show connected channels
cortex channels add telegram  # guided channel setup
cortex memory search "query"  # search conversation memory
cortex update             # update CortexFlow
```

Built with `click` + `rich` for colored terminal output.

### 4.5 Simplified Config (TOML)

```toml
# ~/.cortexflow/config.toml

[agent]
name = "My Assistant"
model = "auto"            # auto = task-aware routing

[models]
primary = "claude-opus-4-8"      # Anthropic API
fallback = "gemini-2.0-flash"    # Google API
fast = "gemini-2.0-flash"        # Speed-optimized tasks
local = "ollama/llama3.2"        # Privacy mode / offline

[memory]
short_term_ttl = 3600     # Redis TTL seconds
long_term_days = 90       # SQLite retention

[voice]
stt = "whisper"           # whisper | none
tts = "elevenlabs"        # elevenlabs | kokoro | system | none
tts_voice = "Rachel"      # ElevenLabs voice name

[channels.telegram]
enabled = true
bot_token = "ENV:TELEGRAM_BOT_TOKEN"

[channels.discord]
enabled = true
bot_token = "ENV:DISCORD_BOT_TOKEN"

[channels.slack]
enabled = false

[channels.email]
enabled = false
imap_host = "imap.gmail.com"
smtp_host = "smtp.gmail.com"
username = "ENV:EMAIL_USER"
password = "ENV:EMAIL_PASSWORD"

[gateway]
port = 7432
bind = "127.0.0.1"

[ui]
web_port = 3000
```

### 4.6 Workspace Files (inspired by OpenClaw)

`~/.cortexflow/workspace/`:
- `SOUL.md` — Agent personality, tone, response style
- `TOOLS.md` — Custom tool definitions (plain English)
- `MEMORY.md` — Long-term memory instructions (what to remember, what to forget)
- `RULES.md` — Explicit rules (never do X, always do Y)

These are injected into every LLM prompt as system context.

---

## 5. Phase-by-Phase Roadmap

### Phase 0 — Cleanup & Foundation (Week 1)

Goal: Strip the existing codebase of enterprise-only components, establish the new directory layout.

**Tasks:**
- [x] Delete enterprise-only modules: `governance/`, `workers/celery_app.py`, `security/zero_trust.py`, `security/sandbox.py`, `api/v1/approvals.py`
- [x] Rename `app/` → `cortexflow/` (cleaner package name)
- [x] Replace `requirements.txt` dependencies: remove `celery`, `neo4j`, `asyncpg`; add `faster-whisper`, `python-telegram-bot`, `discord.py`, `aiosmtplib`, `click`, `rich`, `tomli`
- [x] Replace PostgreSQL with SQLite (aiosqlite + SQLAlchemy) for long-term memory
- [x] Replace JWT/RBAC auth with simple API key auth (single user, single key)
- [x] Update Docker Compose: drop Neo4j + Celery worker; add Qdrant + keep Redis
- [x] Create new project layout (see below)
- [x] Update README to reflect personal assistant direction

**New Directory Layout:**
```
cortexflow/
├── gateway/              # FastAPI WebSocket gateway + REST API
│   ├── main.py           # App entry point
│   ├── websocket.py      # WS connection manager
│   └── routes/
├── channels/             # Channel adapter implementations
│   ├── base.py           # ChannelAdapter ABC
│   ├── telegram.py
│   ├── discord.py
│   ├── slack.py
│   ├── whatsapp.py
│   └── email_.py
├── agent/                # Agent runtime (simplified from enterprise)
│   ├── runtime.py        # AgentRuntime
│   ├── pipeline.py       # plan → execute → reflect
│   └── session.py        # Per-channel session management
├── memory/               # 3-tier memory
│   ├── retrieval.py      # MemoryRetrievalPipeline (adapted)
│   ├── short_term.py     # Redis
│   ├── semantic.py       # Qdrant
│   └── long_term.py      # SQLite
├── models/               # LLM routing (adapted from enterprise)
│   ├── router.py
│   ├── claude.py
│   ├── gemini.py
│   ├── deepseek.py
│   └── ollama.py
├── voice/                # Voice layer
│   ├── stt.py            # faster-whisper wrapper
│   └── tts.py            # ElevenLabs + Kokoro + system
├── reflection/           # Quality + self-correction (simplified)
│   └── engine.py
├── observability/        # Logging + metrics (from enterprise)
│   ├── logs.py
│   └── metrics.py
├── config.py             # TOML config parser (pydantic-settings)
└── cli.py                # cortex CLI tool (click)

frontend/                 # Next.js UI (adapted from enterprise)
src-tauri/                # Tauri desktop shell (new)
```

---

### Phase 1 — Core Gateway + First Channels (Week 2-3)

Goal: Working gateway daemon with Telegram + Discord channels, basic memory, basic web UI.

**Tasks:**

**Gateway:**
- [x] FastAPI app with WebSocket endpoint (`ws://127.0.0.1:7432`)
- [x] WebSocket message protocol (JSON frames: `{type, session_id, payload}`)
- [x] Channel Manager (register/deregister adapters, route inbound messages)
- [x] Session Manager (per-channel session isolation, history tracking)
- [x] Config loader (TOML → pydantic settings)
- [x] `cortex start` CLI command

**Channel Adapters:**
- [x] `TelegramAdapter` — `python-telegram-bot` v21 async
  - Receive: text, images, voice notes, documents
  - Send: text, markdown, inline keyboard buttons
  - Commands: `/start`, `/reset`, `/memory`, `/status`
- [x] `DiscordAdapter` — `discord.py`
  - Receive: messages in channels + DMs
  - Send: text, embeds, reactions
  - Slash commands: `/reset`, `/memory`, `/model`

**Agent:**
- [x] `AgentRuntime` (simplified from enterprise) — no Celery, pure asyncio
- [x] Per-session context assembly from memory
- [x] Task routing to model router
- [x] Response streaming back to channel adapter

**Memory:**
- [x] Redis short-term (5 min TTL for active context)
- [x] Qdrant semantic search (using existing enterprise code)
- [x] SQLite long-term (aiosqlite, simple schema: content, importance, created_at)
- [x] `MemoryRetrievalPipeline` adapted from enterprise (3-tier instead of 4)

**Web UI:**
- [x] Adapt existing Next.js dashboard
- [x] Remove enterprise pages (approvals, security policy editor)
- [x] Add: Conversation history (per-channel), Memory explorer, Channel status

---

### Phase 2 — More Channels + Voice (Week 4-5)

Goal: Full channel coverage (top 5) + working voice STT/TTS.

**Tasks:**

**Channel Adapters:**
- [x] `SlackAdapter` — slack-sdk
  - App mentions + DMs + slash commands
  - RTM or Events API (webhook mode)
- [x] `WhatsAppAdapter` — whatsapp-web.py
  - QR code auth flow
  - Text + image + audio messages
  - Group chat support
- [x] `EmailAdapter` — aiosmtplib + aioimaplib
  - IMAP polling (configurable interval, default 60s)
  - SMTP send with threading (In-Reply-To header)
  - Subject line parsing for context

**Voice:**
- [x] `WhisperSTT` — faster-whisper integration
  - WebSocket endpoint for streaming transcription
  - Auto-detect language
  - Support input from Telegram voice notes + Discord voice
- [x] `ElevenLabsTTS` — ElevenLabs Python SDK
  - Stream audio chunks for low-latency playback
  - Configurable voice per session
- [x] `KokoroTTS` — Local fallback
  - No API key required
  - Runs on CPU

**Cognitive improvements:**
- [x] Reflection engine — quality scorer + self-correction
  - If quality < 70: regenerate with different prompt
  - If hallucination detected: add sources to context and retry
- [x] Message summarization — summarize long conversations before injecting to context (token budget)
- [x] Auto-tagging — extract entities/topics from messages, store as memory tags

---

### Phase 3 — Tauri Desktop + CLI + Plugin System (Week 6-7)

Goal: Native desktop app + full CLI + extensibility.

**Tasks:**

**Tauri Desktop App:**
- [ ] `src-tauri/` project setup
- [ ] Wraps Next.js web UI (existing port 3000)
- [ ] System tray with channel notification badges
- [ ] Native desktop notifications (per new message)
- [ ] Hotkey: Ctrl+Shift+Space to focus
- [ ] Auto-start on login option
- [ ] Single installer (Windows `.msi`, macOS `.dmg`, Linux `.AppImage`)

**CLI (`cortex`):**
- [x] `cortex start [--background]` — start daemon
- [x] `cortex stop` — stop daemon
- [x] `cortex status` — show channels, memory stats, model in use
- [x] `cortex message "text"` — send to primary agent
- [x] `cortex channels list/add/remove` — channel management
- [x] `cortex memory search "query"` — search memory
- [x] `cortex memory clear` — reset all memory
- [x] `cortex config edit` — open config in $EDITOR
- [x] `cortex update` — self-update

**Plugin System (sandboxed):**
- [x] Plugin interface spec (`cortexflow/plugins/base.py`)
- [x] Plugins run as subprocess (not in-process) — isolated from gateway
- [x] Plugin SDK: `pip install cortexflow-sdk` (standalone package in `cortexflow-sdk/`, not yet published to PyPI)
- [x] Plugin types: Channel, Tool, Memory, TTS, STT, LLM Provider
- [x] Plugin registry: `cortex plugin add <package>` installs from PyPI
- [x] Example plugins: GitHub Events, Notion integration, Google Calendar (`examples/plugins/`)

---

### Phase 4 — OpenClaw Feature Parity + Superiority (Week 8-10)

Goal: Match OpenClaw's channel breadth, exceed its quality.

**Tasks:**

**Additional Channels (Priority 2):**
- [x] `SMSAdapter` — Twilio SDK
- [x] `MatrixAdapter` — matrix-nio
- [x] `IRCAdapter` — pydle
- [x] `SignalAdapter` — signal-cli subprocess wrapper
- [x] `MastodonAdapter` — Mastodon.py
- [x] `WebhookAdapter` — generic HTTP receiver (POST → message)

**Superior Memory:**
- [x] Memory importance scoring (1.0 scale, auto-updated on access)
- [x] `prune_low_importance()` scheduled daily (already implemented!)
- [x] Cross-session memory sharing (one memory pool across all channels)
- [ ] Memory timeline view in web UI
- [ ] Manual memory editing (web UI: edit/delete individual memories)

**Superior LLM Routing:**
- [x] Auto model selection based on message complexity (short → Gemini Flash, long/complex → Claude Opus)
- [x] Privacy mode: all traffic via Ollama (no external API calls)
- [x] Per-channel model override (e.g., Telegram always uses fast model)
- [ ] Token usage dashboard in web UI

**Superior Voice:**
- [x] Wake word detection (OpenWakeWord — open-source, cross-platform)
- [x] Voice note support: Telegram/Discord voice messages → transcribed → processed → response as voice
- [x] TTS voice cloning (ElevenLabs custom voice upload)

**Smart Compression:**
- [x] Conversation compaction (like Claude's `/compact` command)
- [x] Automatic summarization when context window > 50% full
- [x] Archive old conversations with searchable summaries

---

### Phase 5 — Polish + Distribution (Week 11-12)

Goal: Production-quality release, installer, documentation.

**Tasks:**
- [ ] One-command install: `pip install cortexflow` + `cortex init`
- [x] Guided first-run wizard (channel setup, model config, voice test)
- [ ] Comprehensive README + docs site (mkdocs)
- [x] GitHub Actions CI (lint + test + build Tauri app + push to GHCR)
- [ ] Docker image: `ghcr.io/theamitchandra/cortexflow:latest`
- [x] Re-enable CI/CD with new workflows
- [ ] Performance benchmarks vs OpenClaw

---

## 6. How CortexFlow v2 Beats OpenClaw — Dimension by Dimension

### Memory (CortexFlow wins decisively)

| | OpenClaw | CortexFlow v2 |
|---|---|---|
| Storage | LanceDB (vector only) | Redis (TTL context) + Qdrant (semantic) + SQLite (persistent) |
| Retrieval | Vector similarity search | Ranked pipeline: recent context → semantic → long-term |
| Deduplication | None | Content-hash dedup at storage time |
| Importance | None | Auto-scored (0.0–1.0), pruned below 0.2 |
| Token management | Manual compaction commands | Auto-compact when > 50% context window |
| UI | None | Memory explorer: search, edit, delete, timeline |

### LLM Routing (CortexFlow wins)

| | OpenClaw | CortexFlow v2 |
|---|---|---|
| Model selection | Single configured model | Auto task-aware: Claude for reasoning, Gemini Flash for speed, Ollama for privacy |
| Fallback | None | Automatic: primary → fast → local → degraded |
| Per-channel override | Manual agent config | `[channels.telegram]` model override in TOML |
| Token budget | None | Soft limits with logging (no hard block — personal use) |
| Privacy mode | No | Yes — `model = "ollama/llama3.2"` in config, zero external calls |

### Voice (CortexFlow ties/wins)

| | OpenClaw | CortexFlow v2 |
|---|---|---|
| STT | No dedicated (platform-level only) | faster-whisper (local, free, GPU-optional) |
| TTS | ElevenLabs + system | ElevenLabs + Kokoro (local) + system |
| Wake word | macOS/iOS only (built-in) | OpenWakeWord (cross-platform, open-source) |
| Voice notes | Pass-through only | Telegram/Discord voice notes → STT → process → TTS response |

### Web UI (CortexFlow wins)

| | OpenClaw | CortexFlow v2 |
|---|---|---|
| Interface | Static WebChat widget | Full Next.js dashboard |
| Memory UI | None | Explorer: search, edit, timeline |
| Channel status | None | Live status per channel with reconnect controls |
| Model usage | None | Token usage + cost estimate per session |
| Conversation history | Per-session only | Cross-channel unified history with search |

### Configuration (CortexFlow wins)

| | OpenClaw | CortexFlow v2 |
|---|---|---|
| Format | YAML (complex, 50+ keys) | TOML (simple, type-validated) |
| Schema validation | None | Pydantic v2 — errors with line numbers |
| Defaults | Must configure most things | Works with 3 lines: model + 1 channel token |
| Secret handling | `${ENV_VAR}` interpolation | `"ENV:VAR_NAME"` interpolation (same idea, clearer) |
| IDE support | No schema | JSON Schema exported for IDE autocomplete |

### Observability (CortexFlow wins)

| | OpenClaw | CortexFlow v2 |
|---|---|---|
| Logs | Stdout (unstructured) | structlog JSON with trace IDs |
| Metrics | None | Prometheus: message count, latency, memory usage, channel health |
| UI | None | Metrics dashboard in web UI |
| Debug mode | `--verbose` flag | `LOG_LEVEL=debug` + web UI log stream |

### Plugin Security (CortexFlow wins)

| | OpenClaw | CortexFlow v2 |
|---|---|---|
| Plugin isolation | In-process (full trust) | Subprocess (isolated) |
| Permissions | None | Declared capabilities: `["network", "filesystem:read"]` |
| Package validation | Install policy | PyPI package + declared manifest |
| Sandboxing | Optional Docker for sessions | Always subprocess for plugins |

---

## 7. OpenClaw Features to Not Copy

Some OpenClaw choices are deliberate tradeoffs. We skip these:

- **TypeScript/Node.js** — Python is better for AI. We stay Python.
- **20 channel adapters on day 1** — Quality > quantity. We do 5 well first.
- **Swift/Kotlin native apps** — Tauri gives cross-platform with one codebase.
- **ClawHub** — Plugin marketplace adds complexity. Start with PyPI install.
- **Multi-node edge architecture** — Single user doesn't need distributed nodes.
- **ACP framework** — Access Control Policy is enterprise-level complexity. Simple API key is enough.

---

## 8. Feature Parity Checklist vs OpenClaw

Track progress toward full OpenClaw feature parity:

### Core Architecture
- [x] Gateway daemon (WebSocket server)
- [x] CLI tool
- [x] Session isolation per channel
- [x] Multi-agent routing (different channels → different models)
- [x] Plugin/extension system

### Channel Adapters
- [x] Telegram
- [x] Discord
- [x] Slack
- [x] WhatsApp
- [x] Email
- [x] SMS (Twilio)
- [x] Matrix
- [x] IRC
- [x] Signal
- [x] Webhook (generic)
- [x] Mastodon
- [x] Microsoft Teams (stretch)
- [x] Mattermost (stretch)
- [x] Nextcloud Talk (stretch)

### AI & LLM
- [x] Claude (Anthropic)
- [x] Gemini (Google)
- [x] GPT-4 (OpenAI)
- [x] Ollama (local)
- [x] Task-aware routing (beyond OpenClaw)
- [x] Extended thinking / reasoning mode

### Memory
- [x] Conversation history
- [x] Semantic search
- [x] Workspace files (SOUL.md, TOOLS.md, MEMORY.md)
- [x] Memory compaction / summarization
- [x] Cross-session shared memory (beyond OpenClaw)
- [x] Memory UI (beyond OpenClaw)

### Voice
- [x] TTS (ElevenLabs)
- [x] TTS (local Kokoro)
- [x] STT (Whisper)
- [x] Voice note processing
- [x] Wake word (OpenWakeWord)

### UI
- [x] Web UI (basic chat)
- [x] Web UI (memory explorer) — beyond OpenClaw
- [ ] Web UI (channel status) — beyond OpenClaw
- [ ] Desktop app (Tauri)
- [ ] Mobile web (responsive)

### Commands
- [x] `/reset` — clear session history
- [x] `/memory` — show recent memories
- [x] `/model` — switch LLM model
- [x] `/status` — show system status
- [x] `/compact` — summarize and compress history
- [x] `/voice on|off` — toggle voice responses

---

## 9. First Implementation Sprint (Start Here)

When ready to start building, tackle in this exact order:

1. **Phase 0 cleanup** — strip enterprise code, set up new directory layout
2. **Config loader** — TOML parser with pydantic, `cortex init` wizard
3. **Gateway WebSocket** — simple message routing, no channels yet
4. **TelegramAdapter** — first real channel (easiest, largest reach)
5. **Memory pipeline** — Redis + Qdrant + SQLite (adapt from enterprise)
6. **Model router** — adapt from enterprise, simplified
7. **DiscordAdapter** — second channel
8. **Web UI** — adapt existing Next.js, remove enterprise pages
9. **Voice STT/TTS** — Whisper + ElevenLabs
10. **CLI tool** — `cortex` with basic commands

Each of these maps to one branch + one PR. The one-file-one-commit rule from `SKILL.md` still applies within each branch.

---

*Plan authored after deep comparative analysis of OpenClaw (https://github.com/openclaw/openclaw) and full study of the existing CortexFlow enterprise codebase. OpenClaw is a TypeScript/Node.js monorepo with 377k stars, 57k+ commits, and 25+ channel adapters. CortexFlow v2 aims to surpass it on memory quality, LLM routing intelligence, voice breadth, and web UI — while matching or exceeding channel coverage.*
