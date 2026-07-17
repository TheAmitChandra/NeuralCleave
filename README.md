<div align="center">

<img src="cortexflow.png" alt="CortexFlow-AI" width="100%" />

<br/>

# CortexFlow-AI

### Your Personal AI Assistant — Smarter, Faster, and Fully Yours

<br/>

[![License: BUSL 1.1](https://img.shields.io/badge/License-BUSL%201.1-blue.svg?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

<br/>

[![Stars](https://img.shields.io/github/stars/TheAmitChandra/CortexFlow-AI?style=flat-square)](https://github.com/TheAmitChandra/CortexFlow-AI/stargazers)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](CONTRIBUTING.md)

<br/>

> **One AI assistant. Every channel. Smarter memory. No lock-in.**

<br/>

[Website](https://theamitchandra.github.io/CortexFlow-AI/) · [Get Started](#-quick-start) · [Desktop App](#-desktop-app) · [Architecture](#-architecture) · [Channels](#-channel-adapters-32) · [Voice](#-voice) · [CLI](#-cli) · [Roadmap](#-roadmap)

</div>

---

## What is CortexFlow-AI?

CortexFlow-AI is a **personal AI assistant gateway** that connects you to the best AI models across every platform you already use — Telegram, Discord, Slack, WhatsApp, Email — all from one unified backend that knows who you are and remembers everything.

Unlike competing tools, CortexFlow-AI is:

- **Python-first** — better AI/ML ecosystem, embed model calls anywhere
- **Memory-native** — 3-tier memory (Redis + Qdrant + SQLite) with per-agent namespace isolation
- **Model-agnostic** — routes each request to the optimal provider (16 providers) with automatic fallback
- **Voice-ready** — built-in local STT (faster-whisper) and TTS (ElevenLabs / Kokoro / system)
- **Local-first** — works fully offline with Ollama; no cloud dependency required
- **Desktop-native** — Tauri v2 app for Windows, macOS, and Linux with embedded terminal panel

```
You (any channel) → CortexFlow-AI Gateway → Smart Memory Retrieval → Best Available Model → Reply
```

> The enterprise version of this project (multi-tenant RBAC, Kubernetes, governance) lives at [CortexFlow-Enterprise](https://github.com/TheAmitChandra/CortexFlow-Enterprise).

---

## Why Better Than the Competition?

| Feature | Competitors | CortexFlow-AI |
|---|:---:|:---:|
| Language | TypeScript | Python (better AI/ML) |
| Memory | Flat file / LanceDB | Redis + Qdrant + SQLite (3-tier) |
| Per-agent memory isolation | ❌ | LRU namespace per agent node |
| LLM providers | 4–8 | **16** (Claude, Gemini, GPT-4o, DeepSeek, Mistral, Grok, Cohere, Groq, Together, Perplexity, Replicate, Fireworks, Anyscale, Ollama, OpenRouter, LM Studio) |
| Local/offline mode | ❌ | Ollama + LM Studio (full offline) |
| Voice (STT + TTS) | ❌ | faster-whisper + ElevenLabs/Kokoro |
| Desktop app | ❌ | Tauri v2 (Windows / macOS / Linux) |
| Embedded terminal | ❌ | `/ws/terminal` + xterm.js panel |
| Agent orchestrator | ❌ | `AgentOrchestrator` (multi-node, priority routing) |
| Canvas (reasoning graph) | ❌ | Live visual agent graph |
| PWA (installable) | ❌ | Progressive Web App support |
| Channels | ~6 | **32** |
| Config format | YAML | TOML (simpler, typed) |
| ENV secret resolution | Manual | `ENV:VAR_NAME` in TOML |
| Web UI | ❌ | Next.js (chat + memory + orchestrator + canvas + terminal) |
| CLI | ❌ | `cortex` (click + rich) |
| Tests | ~200 | **4 900+** |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     You (any surface)                            │
│  Telegram · Discord · Slack · WhatsApp · Email · Web · CLI      │
│  (32 channels total — see full list below)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │ messages / voice / files
┌────────────────────────────▼────────────────────────────────────┐
│           WebSocket Gateway  (FastAPI + uvicorn)                 │
│           ws://127.0.0.1:7432/ws       (chat)                   │
│           ws://127.0.0.1:7432/ws/terminal  (CMD panel)          │
│           http://127.0.0.1:7432/api/v1/*   (REST)               │
└──────────┬──────────────────────────────────────────────────────┘
           │
    ┌──────▼─────────────────────────────────────────────────┐
    │             Agent Orchestrator                           │
    │  Multi-node priority routing · per-node memory ns       │
    │  AgentNode[code] / AgentNode[review] / AgentNode[...]   │
    └──────┬──────────────────┬───────────────────────────────┘
           │                  │
  ┌────────▼──────┐  ┌────────▼────────────────────────────┐
  │  3-Tier Memory│  │   Task-Aware Model Router (16 LLMs)  │
  │               │  │                                       │
  │  Short: Redis │  │  complex_reasoning → Claude Opus 4.8 │
  │  Semantic: Q. │  │  code_generation   → DeepSeek Coder  │
  │  Long: SQLite │  │  general/fast      → Gemini 2.5 Flash│
  │               │  │  offline           → Ollama           │
  └───────────────┘  └───────────────────────────────────────┘
           │
  ┌────────▼──────────────────────────────────────────────────┐
  │                   Voice Layer                               │
  │  STT: faster-whisper (local, tiny → large-v3)              │
  │  TTS: ElevenLabs → Kokoro → pyttsx3 (fallback chain)      │
  └────────────────────────────────────────────────────────────┘
```

---

## Desktop App

CortexFlow-AI ships a **native desktop app** built with [Tauri v2](https://v2.tauri.app) — a Next.js dashboard wrapped in a lightweight Rust shell.

### Features

| Feature | Description |
|---|---|
| **Terminal panel** | Run any shell command — or `cortex` CLI commands — without leaving the app |
| **Chat** | Stream replies from any configured AI model |
| **Memory explorer** | Browse, search, edit, and delete long-term memory entries |
| **Orchestrator** | View agent nodes, routing rules, and per-node memory namespace stats |
| **Canvas** | Live visual agent reasoning graph |
| **Skills** | Browse and manage installed skill hub packages |
| **Channels** | Connect and monitor all 32 channel adapters |
| **Observability** | Real-time metrics, token usage, and latency charts |
| **System tray** | Global hotkey (Ctrl+Shift+Space) to open/hide; native notifications |
| **Single instance** | One app, auto-focus if already open |
| **Auto-start** | Optional startup at login |

### Install the desktop app

**Windows**

Download `CortexFlow-AI_2.1.0_x64-setup.exe` from [Releases](https://github.com/TheAmitChandra/CortexFlow-AI/releases) and run it.

For power users who also want the `cortex` CLI in their terminal:

```bat
scripts\install-cli.bat
```

**macOS**

Download `CortexFlow-AI_2.1.0_universal.dmg` from [Releases](https://github.com/TheAmitChandra/CortexFlow-AI/releases), open it, and drag to Applications.

```bash
bash scripts/install-cli.sh
```

**Linux (Debian/Ubuntu)**

```bash
sudo dpkg -i CortexFlow-AI_2.1.0_amd64.deb
bash scripts/install-cli.sh
```

Or install the AppImage:

```bash
chmod +x CortexFlow-AI_2.1.0_amd64.AppImage
./CortexFlow-AI_2.1.0_amd64.AppImage
```

---

## Project Structure

```
CortexFlow-AI/
├── cortexflow_ai/
│   ├── __init__.py           ← version (2.1.0)
│   ├── config.py             ← TOML config loader (ENV:VAR_NAME secrets)
│   ├── cli.py                ← `cortex` CLI entry point
│   ├── gateway/
│   │   ├── main.py           ← FastAPI app factory + uvicorn runner
│   │   ├── websocket.py      ← WebSocket session manager + /ws endpoint
│   │   ├── terminal.py       ← /ws/terminal — embedded CMD panel endpoint
│   │   └── routes.py         ← REST API (/api/v1/*)
│   ├── channels/             ← 32 adapters behind one ChannelAdapter ABC
│   │   ├── base.py           ← ChannelAdapter ABC, InboundMessage, Attachment
│   │   ├── telegram.py, discord_.py, slack.py, whatsapp.py, email_.py, sms.py,
│   │   │   matrix.py, irc.py, signal_.py, webhook.py, mastodon_.py, teams.py,
│   │   │   mattermost.py, nextcloud.py, rss.py, twitter_.py, linkedin_.py,
│   │   │   youtube_.py, reddit_.py, github_.py, jira_.py, notion_.py,
│   │   │   line_.py, viber_.py, wechat_.py, kik_.py, skype_.py,
│   │   │   facebook_.py, instagram_.py, snapchat_.py, tiktok_.py, twitch_.py
│   ├── agent/
│   │   ├── runtime.py        ← AgentRuntime — wires channels/memory/voice/router
│   │   ├── pipeline.py       ← CognitivePipeline (intent → memory → generate)
│   │   └── session.py        ← SessionManager, rolling conversation history
│   ├── memory/
│   │   ├── retrieval.py      ← MemoryRetrievalPipeline (3-tier, cross-session)
│   │   ├── long_term.py      ← SQLite long-term store (tags, importance)
│   │   ├── tagging.py        ← heuristic auto-tagging
│   │   ├── compactor.py      ← in-session conversation compaction
│   │   └── archiver.py       ← inactive-session summary archiving
│   ├── models/
│   │   ├── router.py         ← ModelRouter — task routing + fallback chain (16 providers)
│   │   ├── deepseek.py, openai_.py, mistral_.py, groq_.py, together_.py,
│   │   │   cohere_.py, perplexity_.py, replicate_.py, fireworks_.py, grok_.py
│   ├── orchestrator/
│   │   ├── orchestrator.py   ← AgentOrchestrator — multi-node priority routing
│   │   ├── node.py           ← AgentNodeConfig + AgentNode
│   │   ├── memory.py         ← MemoryNamespaceStore + MemoryNamespaceManager
│   │   └── task.py           ← AgentTask
│   ├── canvas/
│   │   ├── renderer.py       ← CanvasRenderer — live reasoning graph
│   │   └── routes.py         ← /api/v1/canvas/* + SSR canvas page
│   ├── pwa/routes.py         ← Progressive Web App manifest + service worker routes
│   ├── voice/
│   │   ├── stt.py            ← WhisperSTT (faster-whisper)
│   │   ├── tts.py            ← TTSEngine (ElevenLabs / Kokoro / pyttsx3) + cloning
│   │   └── wake_word.py      ← OpenWakeWord
│   ├── reflection/engine.py  ← quality scoring + self-correction
│   ├── plugins/, tools/      ← sandboxed plugin system + built-in tools
│   └── commands/handler.py   ← /reset /memory /model /status /compact /voice
├── tests/unit/               ← 4 900+ tests, all passing
├── frontend/                 ← Next.js web UI (Tauri desktop shell)
│   ├── src/app/(dashboard)/
│   │   ├── dashboard/        ← live stats overview
│   │   ├── chat/             ← streaming AI chat
│   │   ├── memory/           ← memory browser + editor
│   │   ├── channels/         ← channel status + connect
│   │   ├── orchestrator/     ← agent nodes + memory namespace stats
│   │   ├── skills/           ← installed skill hub packages
│   │   ├── canvas/           ← live reasoning graph
│   │   ├── terminal/         ← embedded CMD panel (xterm.js)
│   │   ├── observability/    ← metrics + latency charts
│   │   └── settings/         ← LLM keys, gateway URL
│   └── src-tauri/            ← Tauri v2 Rust shell
├── scripts/
│   ├── bundle_backend.ps1    ← Windows: PyInstaller → .exe sidecar
│   ├── bundle_backend_mac.sh ← macOS: PyInstaller → universal binary
│   ├── bundle_backend_linux.sh ← Linux: PyInstaller → ELF binary
│   ├── install-cli.bat       ← Windows: install `cortex` CLI from PyPI
│   └── install-cli.sh        ← macOS/Linux: install `cortex` CLI from PyPI
├── docs/
│   ├── SKILL.md                     ← full implementation knowledge base
│   ├── COMPETITIVE_ANALYSIS_OPENCLAW.md ← feature-by-feature comparison
│   └── IMPLEMENTATION_PLAN_v2.md    ← phase-by-phase build roadmap
└── pyproject.toml            ← `cortex` entry point + pytest/ruff config
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- Git

### 1. Install

Published on PyPI — no clone required:

```bash
pip install cortexflow-ai
```

Or from source, for development:

```bash
git clone https://github.com/TheAmitChandra/CortexFlow-AI.git
cd CortexFlow-AI

pip install -r requirements-v2.txt
pip install -e .
```

### 2. Initialise config

```bash
cortex config init
```

This creates `~/.cortexflow/config.toml`. Edit it:

```toml
[agent]
name = "My Assistant"

[models]
anthropic_api_key = "ENV:ANTHROPIC_API_KEY"
gemini_api_key    = "ENV:GEMINI_API_KEY"

[channels.telegram]
enabled   = true
bot_token = "ENV:TELEGRAM_BOT_TOKEN"

[voice]
tts_engine = "elevenlabs"
elevenlabs_api_key = "ENV:ELEVENLABS_API_KEY"
```

Set your environment variables:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=AIza...
export TELEGRAM_BOT_TOKEN=123456:ABC...
```

### 3. Start the gateway

```bash
cortex start
```

### 4. Chat from the terminal

```bash
cortex chat
```

### Or run with Docker

A multi-stage image is published publicly to GHCR — no `pip install`, no Python setup:

```bash
docker pull ghcr.io/theamitchandra/cortexflow-ai:latest

docker run -d \
  --name cortexflow-ai \
  -p 7432:7432 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e TELEGRAM_BOT_TOKEN=123456:ABC... \
  -v cortexflow-data:/root/.cortexflow \
  ghcr.io/theamitchandra/cortexflow-ai:latest

curl http://localhost:7432/health
```

The container's entrypoint is `cortex start --bind 0.0.0.0`; mount `/root/.cortexflow` as a volume to persist config and the SQLite memory store across restarts.

---

## Channel Adapters (32)

CortexFlow-AI normalises every platform into a single `InboundMessage` format:

```python
@dataclass
class InboundMessage:
    channel: str        # "telegram" | "discord" | "slack" | ...
    sender_id: str
    sender_name: str
    text: str | None
    attachments: list[Attachment]
    thread_id: str | None
    reply_to_id: str | None
    timestamp: float
    raw: dict           # full platform payload
```

| Channel | Status | Package |
|---|---|---|
| Telegram | Implemented | `python-telegram-bot>=21.0` |
| Discord | Implemented | `discord.py>=2.4` |
| Slack | Implemented | `slack-sdk` |
| WhatsApp | Implemented | WhatsApp Cloud API (httpx) |
| Email | Implemented | IMAP/SMTP (aiosmtplib) |
| SMS | Implemented | Twilio |
| Matrix | Implemented | `matrix-nio` |
| IRC | Implemented | raw asyncio socket |
| Signal | Implemented | `signal-cli` subprocess |
| Webhook | Implemented | generic HTTP receiver |
| Mastodon | Implemented | `Mastodon.py` |
| Microsoft Teams | Implemented | Bot Framework |
| Mattermost | Implemented | webhook + REST |
| Nextcloud Talk | Implemented | REST API |
| RSS | Implemented | `feedparser` |
| Twitter/X | Implemented | Twitter API v2 |
| LinkedIn | Implemented | LinkedIn Messaging API |
| YouTube | Implemented | YouTube Data API |
| Reddit | Implemented | PRAW |
| GitHub | Implemented | GitHub webhooks |
| Jira | Implemented | Jira REST API |
| Notion | Implemented | Notion API |
| LINE | Implemented | LINE Messaging API |
| Viber | Implemented | Viber REST API |
| WeChat | Implemented | WeChat Official Account API |
| Kik | Implemented | Kik Bot API |
| Skype | Implemented | Skype Bot Framework |
| Facebook | Implemented | Messenger Platform |
| Instagram | Implemented | Instagram Graph API |
| Snapchat | Implemented | Snapchat Kit |
| TikTok | Implemented | TikTok API |
| Twitch | Implemented | Twitch EventSub |
| Web UI | Implemented | Next.js + WebSocket |
| Desktop | Implemented | Tauri v2 (Windows / macOS / Linux) |

---

## Memory

The 3-tier retrieval pipeline assembles context before every response:

```
Query
  │
  ├── Short-term (Redis)  → score 1.0 — active session keys (TTL 1h)
  ├── Semantic  (Qdrant)  → score = ANN similarity — vector search
  └── Long-term (SQLite)  → score = importance × 0.6 — ranked history
        │
        ▼
  Content-hash deduplication
        │
        ▼
  Score-ranked, capped at top_k
        │
        ▼
  RetrievalContext → prompt blocks
```

All tiers degrade gracefully — if Redis/Qdrant is unavailable, the pipeline continues with what's available.

### Per-node memory isolation

The `AgentOrchestrator` gives each agent node its own private `MemoryNamespaceStore` (ordered LRU key-value store, configurable `max_entries`, default 1000). Nodes are auto-isolated to their own name by default; a shared `memory_namespace` on `AgentNodeConfig` lets any set of nodes share a pool.

```python
from cortexflow_ai.orchestrator import AgentOrchestrator
from cortexflow_ai.orchestrator.node import AgentNodeConfig

orch = AgentOrchestrator()
orch.register(AgentNodeConfig(name="code"))
orch.register(AgentNodeConfig(name="review", memory_namespace="code"))  # shared pool

# Write to "code" namespace — isolated from every other node
orch.memory_for_node("code").put("context", "Python 3.12 project")

# REST endpoints:
# GET    /api/v1/orchestrator/nodes/{name}/memory  → stats for that node's namespace
# DELETE /api/v1/orchestrator/nodes/{name}/memory  → clear the namespace
# GET    /api/v1/orchestrator/namespaces           → full namespace → node mapping
```

---

## Model Routing (16 Providers)

Each request is routed to the optimal provider based on task type, with automatic fallback:

| Task Type | Primary | Fallback 1 | Fallback 2 | Fallback 3 |
|---|---|---|---|---|
| `complex_reasoning` | Claude Opus 4.8 | GPT-4o | Gemini 2.5 Pro | Ollama |
| `code_generation` | DeepSeek Coder | Claude Sonnet | GPT-4o | Gemini 2.5 Flash |
| `code_review` | DeepSeek Coder | GPT-4o | Gemini 2.5 Flash | Ollama |
| `summarization` | Gemini 2.5 Flash | GPT-4o-mini | Ollama | — |
| `intent_extraction` | Gemini 2.5 Flash | GPT-4o-mini | Ollama | — |
| `task_decomposition` | Claude Sonnet | GPT-4o | Gemini 2.5 Pro | Ollama |
| `reflection` | Gemini 2.5 Flash | GPT-4o-mini | Ollama | — |
| `validation` | Gemini 2.5 Flash | GPT-4o-mini | Ollama | — |
| `cheap_inference` | Ollama | GPT-4o-mini | Gemini 2.5 Flash | — |
| `general` | Gemini 2.5 Flash | GPT-4o-mini | Ollama | — |

```python
from cortexflow_ai.models.router import ModelRouter

router = ModelRouter(
    anthropic_api_key="...",
    gemini_api_key="...",
    openai_api_key="...",      # optional — enables GPT-4o in fallback chain
)
result = await router.generate(
    "Explain this stack trace...",
    task_type="code_review",
)
print(result.text)   # answered by DeepSeek Coder (or fallback)
print(result.model)  # the actual model used

# Claude extended thinking mode:
result = await router.generate(
    "Work through this proof step by step",
    task_type="complex_reasoning",
    extended_thinking=True,
    thinking_budget_tokens=4096,
)
print(result.thinking)  # the reasoning trace, when using a Claude model
```

---

## Voice

### STT — faster-whisper (local, no API key)

```python
from cortexflow_ai.voice.stt import WhisperSTT

stt = WhisperSTT(model_size="base", device="cpu")
text = await stt.transcribe(audio_bytes)          # bytes or Path
# streaming:
async for partial in stt.transcribe_stream(chunks):
    print(partial)
```

### TTS — fallback chain

```python
from cortexflow_ai.voice.tts import TTSEngine

tts = TTSEngine()                           # ElevenLabs → Kokoro → pyttsx3
audio = await tts.synthesize("Hello!")      # returns bytes (MP3/WAV)
await tts.synthesize("Hello!", output_path=Path("out.mp3"))

# prefer local (Kokoro first, no API cost):
tts = TTSEngine(prefer_local=True)

# Custom voice cloning (ElevenLabs):
voice_id = await tts.clone_voice("My Voice", [sample1_bytes, sample2_bytes])
tts.use_voice(voice_id)
```

---

## CLI

```
cortex start                       Start WebSocket gateway + all configured channels
cortex start --background          Start as a detached background process (writes a PID file)
cortex stop                        Stop a background gateway started above
cortex status                      Agent/model/gateway/voice summary + memory row count

cortex chat                        Interactive terminal chat session

cortex config show                 Print resolved configuration (JSON)
cortex config init                 Write starter config.toml to ~/.cortexflow/
cortex config edit                 Open config.toml in $EDITOR

cortex channels list               List configured channel adapters and their status
cortex channels add <name>         Enable a channel adapter in config.toml
cortex channels remove <name>      Disable a channel adapter in config.toml

cortex memory search <query>       Full-text search in long-term SQLite memory
cortex memory stats                Show namespace counts across all agent nodes
cortex memory edit <id>            Edit an entry's content/importance score
cortex memory prune                Remove low-importance entries
cortex memory clear                Permanently delete long-term memory entries
cortex memory archive              Condense inactive sessions into one archive summary

cortex skills list                 List installed skill hub packages
cortex skills install <package>    Install a skill hub package from PyPI
cortex skills remove <package>     Uninstall a skill hub package

cortex plugins list                List registered plugins
cortex tools list                  List all registered built-in tools

cortex voice clone <name> <file>   Clone a custom ElevenLabs voice from audio samples

cortex version                     Print installed version
cortex update                      Check PyPI and self-update if a newer version exists
```

---

## Configuration Reference

Full `~/.cortexflow/config.toml` reference:

```toml
[agent]
name     = "My Assistant"
persona  = "You are a helpful personal AI assistant."
timezone = "UTC"
language = "en"

[models]
anthropic_api_key  = "ENV:ANTHROPIC_API_KEY"
gemini_api_key     = "ENV:GEMINI_API_KEY"
deepseek_api_key   = "ENV:DEEPSEEK_API_KEY"
openai_api_key     = "ENV:OPENAI_API_KEY"
mistral_api_key    = "ENV:MISTRAL_API_KEY"
groq_api_key       = "ENV:GROQ_API_KEY"
cohere_api_key     = "ENV:COHERE_API_KEY"
grok_api_key       = "ENV:GROK_API_KEY"
ollama_base_url    = "http://localhost:11434"

[memory]
redis_url       = "redis://localhost:6379"
qdrant_url      = "http://localhost:6333"
sqlite_path     = "~/.cortexflow/memory.db"
short_term_ttl  = 3600    # seconds
long_term_days  = 90

[voice]
stt_model           = "base"        # tiny|base|small|medium|large-v3
stt_device          = "cpu"         # cpu|cuda
tts_engine          = "elevenlabs"  # elevenlabs|kokoro|system
elevenlabs_api_key  = "ENV:ELEVENLABS_API_KEY"
elevenlabs_voice_id = ""            # set via `cortex voice clone`

[gateway]
bind = "127.0.0.1"
port = 7432

[ui]
web_port = 3000

[channels.telegram]
enabled   = true
bot_token = "ENV:TELEGRAM_BOT_TOKEN"

[channels.discord]
enabled   = true
bot_token = "ENV:DISCORD_BOT_TOKEN"
```

`ENV:VAR_NAME` values are resolved from environment variables at load time — no secrets in files.

---

## Testing

```bash
# Run all unit tests
pytest tests/ -v

# Single module
pytest tests/unit/test_models_router.py -v

# With coverage
pytest tests/ -v --cov=cortexflow_ai --cov-report=term-missing

# Lint
ruff check cortexflow_ai tests --select E,F,W,I --ignore E501
```

**Current status: 4 900+ tests, all passing.**

---

## Roadmap

```
Phase 0 — Cleanup & Foundation                [DONE]
Phase 1 — Core Gateway + First Channels       [DONE]
Phase 2 — More Channels + Voice               [DONE]
  ✅ WebSocket gateway (FastAPI) + REST API
  ✅ TOML config with ENV secret resolution
  ✅ 14 → 32 channel adapters
  ✅ 3-tier memory retrieval pipeline, shared across all channels
  ✅ Task-aware model router (16 providers) with Claude extended thinking
  ✅ Voice: STT (faster-whisper) + TTS (ElevenLabs / Kokoro / pyttsx3)
  ✅ Reflection engine (quality scoring + self-correction)
  ✅ Plugin system (subprocess-sandboxed)
  ✅ Full `cortex` CLI + first-run setup wizard

Phase 3/4 — Remaining backend                 [DONE]
  ✅ Background daemon, self-update, cross-session memory sharing
  ✅ Memory edit / prune / archive via REST + CLI + web UI
  ✅ Plugin SDK (`cortexflow-sdk` on PyPI)
  ✅ Chat WebSocket streaming, Zustand store, error handling
  ✅ Settings page fully wired (LLM keys + WebSocket URL)
  ✅ 4 900+ unit tests passing

Phase 5 — Orchestration & Isolation           [DONE]
  ✅ AgentOrchestrator — multi-node priority routing
  ✅ MemoryNamespaceStore — per-node LRU KV store
  ✅ MemoryNamespaceManager — lazy namespace registry
  ✅ REST: GET/DELETE /nodes/{name}/memory + GET /namespaces
  ✅ 36 HTTP tests for namespace endpoints

Phase 6 — Metrics, Reflection, WebSocket      [DONE]
  ✅ Prometheus-format metrics (/api/v1/metrics, /api/v1/metrics/snapshot)
  ✅ ReflectionEngine wired to gateway
  ✅ DeepSeekProvider integrated into model router
  ✅ Telegram/Discord/Slack/Email channel tests

Phase 7 — Desktop + Cross-Platform           [DONE]
  ✅ Tauri v2 desktop shell (Windows / macOS / Linux)
  ✅ /ws/terminal WebSocket endpoint — embedded CMD panel
  ✅ xterm.js terminal page with quick-action buttons
  ✅ Skills, Orchestrator, Canvas pages in web UI
  ✅ macOS + Linux PyInstaller build scripts
  ✅ Cross-platform CLI install scripts

Up next
  ⬜ Skill hub — publish curated packages to PyPI
  ⬜ Canvas real-time graph (D3 / ReactFlow integration)
  ⬜ Mobile PWA polish (iOS Safari WebPush, Android home screen)
  ⬜ GitHub Actions CI — build .exe / .dmg / .deb on every release tag
```

---

## Documentation

| Doc | Description |
|---|---|
| [docs/SKILL.md](docs/SKILL.md) | Full implementation knowledge base — architecture, protocol specs, build rules |
| [docs/IMPLEMENTATION_PLAN_v2.md](docs/IMPLEMENTATION_PLAN_v2.md) | Detailed phase-by-phase build plan |
| [docs/COMPETITIVE_ANALYSIS_OPENCLAW.md](docs/COMPETITIVE_ANALYSIS_OPENCLAW.md) | Side-by-side comparison with OpenClaw |

---

## License

[Business Source License 1.1](LICENSE) — free for non-production use
(development, evaluation, testing, personal/internal non-revenue use).
Production use requires a commercial license — contact
ask.amitchandra@gmail.com. Converts automatically to Apache 2.0 on
2030-06-26.

The plugin SDK (`cortexflow-sdk`) and its example plugins are MIT
licensed and published separately on PyPI — see
[cortexflow-sdk/README.md](cortexflow-sdk/README.md).

---

<div align="center">

**CortexFlow-AI** — Built for people who want their AI to actually know them.

Created by [Amit Chandra](https://theamitchandra.github.io/My-Portfolio)

[![GitHub](https://img.shields.io/badge/GitHub-TheAmitChandra%2FCortexFlow-AI-181717?style=for-the-badge&logo=github)](https://github.com/TheAmitChandra/CortexFlow-AI)

</div>
