<div align="center">

<img src="cortexflow.png" alt="CortexFlow" width="100%" />

<br/>

# CortexFlow v2

### Your Personal AI Assistant — Smarter, Faster, and Fully Yours

<br/>

[![License: BUSL 1.1](https://img.shields.io/badge/License-BUSL%201.1-blue.svg?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

<br/>

[![Stars](https://img.shields.io/github/stars/TheAmitChandra/CortexFlow?style=flat-square)](https://github.com/TheAmitChandra/CortexFlow/stargazers)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](CONTRIBUTING.md)

<br/>

> **One AI assistant. Every channel. Smarter memory. No lock-in.**

<br/>

[Website](https://theamitchandra.github.io/CortexFlow/) · [Get Started](#-quick-start) · [Architecture](#-architecture) · [Channels](#-channel-adapters) · [Voice](#-voice) · [CLI](#-cli) · [Roadmap](#-roadmap)

</div>

---

## What is CortexFlow?

CortexFlow is a **personal AI assistant gateway** that connects you to the best AI models across every platform you already use — Telegram, Discord, Slack, WhatsApp, Email — all from one unified backend that knows who you are and remembers everything.

Unlike OpenClaw and similar tools, CortexFlow is:

- **Python-first** — better AI/ML ecosystem, embed model calls anywhere
- **Memory-native** — 3-tier memory (Redis + Qdrant + SQLite) vs. flat file stores
- **Model-agnostic** — routes each request to the optimal provider with automatic fallback
- **Voice-ready** — built-in local STT (faster-whisper) and TTS (ElevenLabs / Kokoro / system)
- **Local-first** — works fully offline with Ollama; no cloud dependency required

```
You (any channel) → CortexFlow Gateway → Smart Memory Retrieval → Best Available Model → Reply
```

> The enterprise version of this project (multi-tenant RBAC, Kubernetes, governance) lives at [CortexFlow-Enterprise](https://github.com/TheAmitChandra/CortexFlow-Enterprise).

---

## Why Better Than OpenClaw?

| Feature | OpenClaw | CortexFlow v2 |
|---|:---:|:---:|
| Language | TypeScript | Python (better AI/ML) |
| Memory | LanceDB (flat) | Redis + Qdrant + SQLite (3-tier) |
| Model routing | Single provider | Multi-provider with task-aware fallback |
| Local/offline mode | ❌ | Ollama (full offline) |
| Voice (STT + TTS) | ❌ | faster-whisper + ElevenLabs/Kokoro |
| Desktop app | ❌ | Tauri v2 (roadmap) |
| Config format | YAML | TOML (simpler, typed) |
| ENV secret resolution | Manual | `ENV:VAR_NAME` in TOML |
| CLI | ❌ | `cortex` (click + rich) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     You (any surface)                            │
│   Telegram · Discord · Slack · WhatsApp · Email · Web · CLI     │
└────────────────────────────┬────────────────────────────────────┘
                             │ messages / voice / files
┌────────────────────────────▼────────────────────────────────────┐
│               WebSocket Gateway  (FastAPI)                        │
│               ws://127.0.0.1:7432/ws                             │
│               Channel Adapters: subscribe / broadcast            │
└──────────┬─────────────────────────────────────┬────────────────┘
           │                                     │
┌──────────▼──────────┐               ┌──────────▼──────────────┐
│  3-Tier Memory      │               │  Task-Aware Model Router │
│                     │               │                           │
│  Short-term: Redis  │               │  complex_reasoning →      │
│  Semantic: Qdrant   │               │    Claude Opus 4.8        │
│  Long-term: SQLite  │               │  code_generation →        │
│                     │               │    DeepSeek Coder         │
│  Retrieval Pipeline │               │  general/fast →           │
│  + dedup + ranking  │               │    Gemini Flash           │
└──────────┬──────────┘               │  offline →               │
           │                          │    Ollama (local)        │
           └──────────────┬───────────┘                          │
                          │                                       │
┌─────────────────────────▼──────────────────────────────────────┐
│                      Voice Layer                                 │
│   STT: faster-whisper (local, any size: tiny → large-v3)        │
│   TTS: ElevenLabs → Kokoro → pyttsx3 (fallback chain)          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
CortexFlow/
├── cortexflow/
│   ├── __init__.py          ← version
│   ├── config.py            ← TOML config loader (ENV:VAR_NAME secrets)
│   ├── cli.py                ← `cortex` CLI entry point
│   ├── init_wizard.py        ← guided first-run setup
│   ├── workspace.py          ← SOUL.md/TOOLS.md/MEMORY.md/RULES.md loader
│   ├── gateway/
│   │   ├── main.py           ← FastAPI app factory + uvicorn runner
│   │   ├── websocket.py      ← WebSocket session manager + /ws endpoint
│   │   └── routes.py         ← REST API (/api/v1/*)
│   ├── channels/             ← 14 adapters behind one ChannelAdapter ABC
│   │   ├── base.py           ← ChannelAdapter ABC, InboundMessage, Attachment
│   │   ├── telegram.py, discord_.py, slack.py, whatsapp.py, email_.py,
│   │   │   sms.py, matrix.py, irc.py, signal_.py, webhook.py, mastodon_.py,
│   │   │   teams.py, mattermost.py, nextcloud.py
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
│   │   ├── router.py         ← ModelRouter — task routing + fallback chain
│   │   ├── deepseek.py, openai_.py
│   ├── voice/
│   │   ├── stt.py            ← WhisperSTT (faster-whisper)
│   │   ├── tts.py             ← TTSEngine (ElevenLabs / Kokoro / pyttsx3) + cloning
│   │   └── wake_word.py      ← OpenWakeWord
│   ├── reflection/engine.py  ← quality scoring + self-correction
│   ├── plugins/, tools/      ← sandboxed plugin system + built-in tools
│   ├── commands/handler.py   ← /reset /memory /model /status /compact /voice
│   └── update_checker.py     ← PyPI version check for `cortex update`
├── tests/unit/               ← 761 tests
├── frontend/                 ← Next.js web UI (basic chat + memory explorer)
├── docs/
│   ├── SKILL.md                     ← Full implementation knowledge base
│   └── IMPLEMENTATION_PLAN_v2.md    ← Phase-by-phase build roadmap + checklist
└── pyproject.toml            ← `cortex` entry point + pytest/ruff config
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- Git

### 1. Clone and install

```bash
git clone https://github.com/TheAmitChandra/CortexFlow.git
cd CortexFlow

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

---

## Channel Adapters

CortexFlow normalises every platform into a single `InboundMessage` format:

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
| Mastodon | Implemented | Mastodon.py |
| Microsoft Teams | Implemented | Bot Framework |
| Mattermost | Implemented | webhook + REST |
| Nextcloud Talk | Implemented | REST API |
| Web UI | Implemented (basic chat + memory explorer) | Next.js + WebSocket |
| Desktop | Roadmap | Tauri v2 |

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

---

## Model Routing

Each request is routed to the optimal provider based on task type, with automatic fallback:

| Task Type | Primary | Fallback 1 | Fallback 2 |
|---|---|---|---|
| `complex_reasoning` | Claude Opus 4.8 | Gemini Pro | Ollama |
| `code_generation` | DeepSeek Coder | Claude Sonnet | Gemini Flash |
| `code_review` | DeepSeek Coder | Gemini Flash | Ollama |
| `summarization` | Gemini Flash | Ollama | — |
| `intent_extraction` | Gemini Flash | Ollama | — |
| `task_decomposition` | Claude Sonnet | Gemini Pro | Ollama |
| `cheap_inference` | Ollama | Gemini Flash | — |
| `general` | Gemini Flash | Ollama | — |

```python
from cortexflow.models.router import ModelRouter

router = ModelRouter(anthropic_api_key="...", gemini_api_key="...")
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
from cortexflow.voice.stt import WhisperSTT

stt = WhisperSTT(model_size="base", device="cpu")
text = await stt.transcribe(audio_bytes)          # bytes or Path
# streaming:
async for partial in stt.transcribe_stream(chunks):
    print(partial)
```

### TTS — fallback chain

```python
from cortexflow.voice.tts import TTSEngine

tts = TTSEngine()                           # ElevenLabs → Kokoro → pyttsx3
audio = await tts.synthesize("Hello!")      # returns bytes (MP3/WAV)
await tts.synthesize("Hello!", output_path=Path("out.mp3"))

# prefer local (Kokoro first, no API cost):
tts = TTSEngine(prefer_local=True)

# Custom voice cloning (ElevenLabs):
voice_id = await tts.clone_voice("My Voice", [sample1_bytes, sample2_bytes])
tts.use_voice(voice_id)
```

### Voice notes — full round trip

Inbound audio attachments (Telegram voice messages, Discord-style URL attachments) are
transcribed automatically before the message reaches the cognitive pipeline, and replies
to voice-only messages are synthesized back to audio and sent alongside the text — no
extra config needed beyond having `[voice]` configured.

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
cortex memory edit <id>            Edit an entry's content/importance score
cortex memory prune                Remove low-importance entries
cortex memory clear                Permanently delete long-term memory entries
cortex memory archive              Condense inactive sessions into one archive summary

cortex voice clone <name> <file>   Clone a custom ElevenLabs voice from audio samples
cortex tools list                  List all registered built-in tools

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
anthropic_api_key = "ENV:ANTHROPIC_API_KEY"
gemini_api_key    = "ENV:GEMINI_API_KEY"
deepseek_api_key  = "ENV:DEEPSEEK_API_KEY"
ollama_base_url   = "http://localhost:11434"

[memory]
redis_url       = "redis://localhost:6379"
qdrant_url      = "http://localhost:6333"
sqlite_path     = "~/.cortexflow/memory.db"
short_term_ttl  = 3600    # seconds
long_term_days  = 90

[voice]
stt_model          = "base"        # tiny|base|small|medium|large-v3
stt_device         = "cpu"         # cpu|cuda
tts_engine         = "elevenlabs"  # elevenlabs|kokoro|system
elevenlabs_api_key = "ENV:ELEVENLABS_API_KEY"
elevenlabs_voice_id = ""           # set via `cortex voice clone` to use a cloned voice

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
pytest tests/ -v --cov=cortexflow --cov-report=term-missing

# Lint
ruff check cortexflow tests --select E,F,W,I --ignore E501
```

**Current status: 1159 tests, all passing (99.7% coverage); plus 27 tests / 100% coverage for the standalone `cortexflow-sdk` package.**

---

## Roadmap

```
Phase 0 — Cleanup & Foundation            [DONE]
Phase 1 — Core Gateway + First Channels   [DONE]
Phase 2 — More Channels + Voice           [DONE]
  ✅ WebSocket gateway (FastAPI) + REST API
  ✅ TOML config with ENV secret resolution
  ✅ 14 channel adapters: Telegram, Discord, Slack, WhatsApp, Email, SMS,
     Matrix, IRC, Signal, Webhook, Mastodon, Microsoft Teams, Mattermost,
     Nextcloud Talk
  ✅ 3-tier memory retrieval pipeline, shared across all channels
  ✅ Task-aware model router (Claude / Gemini / DeepSeek / GPT-4 / Ollama)
     with Claude extended thinking mode support
  ✅ Voice: STT (faster-whisper) + TTS (ElevenLabs / Kokoro / pyttsx3) +
     voice note round trip + ElevenLabs voice cloning
  ✅ Reflection engine (quality scoring + self-correction)
  ✅ Memory: importance scoring, pruning, auto-tagging, session archiving
  ✅ Plugin system (subprocess-sandboxed)
  ✅ Full `cortex` CLI (see below) + first-run setup wizard
  ✅ 1159 unit tests passing

Phase 3/4 — Remaining backend work        [DONE]
  ✅ Background daemon (`cortex start --background` / `cortex stop`)
  ✅ Self-update (`cortex update`)
  ✅ Cross-session memory sharing
  ✅ Manual memory editing (REST + CLI; web UI controls still open)
  ✅ Plugin SDK (`cortexflow-sdk/` — standalone, dependency-free package)

Frontend / distribution                   [Open]
  ☐ Tauri v2 desktop app (wraps the existing Next.js web UI)
  ☐ Web UI: memory edit/delete controls, channel status page, mobile layout
  ☐ One-command install (`pip install cortexflow` once published)
  ☐ Publish `cortexflow-sdk` to PyPI
  ☐ Docker image published to GHCR
  ☐ Performance benchmarks vs OpenClaw
```

---

## Documentation

| Doc | Description |
|---|---|
| [docs/SKILL.md](docs/SKILL.md) | Full implementation knowledge base — architecture, protocol specs, build rules |
| [docs/IMPLEMENTATION_PLAN_v2.md](docs/IMPLEMENTATION_PLAN_v2.md) | Detailed 5-phase build plan |
| [docs/COMPETITIVE_ANALYSIS_vs_OpenClaw.md](docs/COMPETITIVE_ANALYSIS_vs_OpenClaw.md) | Side-by-side comparison with OpenClaw |

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

**CortexFlow** — Built for people who want their AI to actually know them.

Created by [Amit Chandra](https://theamitchandra.github.io/My-Portfolio)

[![GitHub](https://img.shields.io/badge/GitHub-TheAmitChandra%2FCortexFlow-181717?style=for-the-badge&logo=github)](https://github.com/TheAmitChandra/CortexFlow)

</div>
