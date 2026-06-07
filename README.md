<div align="center">

<img src="cortexflow.png" alt="CortexFlow" width="100%" />

<br/>

# CortexFlow v2

### Your Personal AI Assistant — Smarter, Faster, and Fully Yours

<br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

<br/>

[![Stars](https://img.shields.io/github/stars/TheAmitChandra/CortexFlow?style=flat-square)](https://github.com/TheAmitChandra/CortexFlow/stargazers)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](CONTRIBUTING.md)

<br/>

> **One AI assistant. Every channel. Smarter memory. No lock-in.**

<br/>

[Get Started](#-quick-start) · [Architecture](#-architecture) · [Channels](#-channel-adapters) · [Voice](#-voice) · [CLI](#-cli) · [Roadmap](#-roadmap)

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
│   ├── __init__.py          ← version: 2.0.0
│   ├── config.py            ← TOML config loader (ENV:VAR_NAME secrets)
│   ├── cli.py               ← `cortex` CLI entry point
│   ├── gateway/
│   │   ├── websocket.py     ← WebSocket session manager + /ws endpoint
│   │   └── main.py          ← FastAPI app factory + uvicorn runner
│   ├── channels/
│   │   ├── base.py          ← ChannelAdapter ABC, InboundMessage, Attachment
│   │   ├── telegram.py      ← python-telegram-bot async adapter
│   │   └── discord_.py      ← discord.py adapter
│   ├── memory/
│   │   └── retrieval.py     ← MemoryRetrievalPipeline (3-tier)
│   ├── models/
│   │   └── router.py        ← ModelRouter with task routing + fallback
│   └── voice/
│       ├── stt.py           ← WhisperSTT (faster-whisper)
│       └── tts.py           ← TTSEngine (ElevenLabs / Kokoro / pyttsx3)
├── tests/
│   └── unit/
│       ├── test_config.py           ← 13 tests
│       ├── test_channels_base.py    ← 10 tests
│       ├── test_models_router.py    ← 15 tests
│       └── test_memory_retrieval.py ← 15 tests
├── docs/
│   ├── SKILL.md                     ← Full implementation knowledge base
│   └── IMPLEMENTATION_PLAN_v2.md    ← 5-phase build roadmap
├── requirements-v2.txt
└── pyproject.toml                   ← `cortex` entry point + pytest config
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
| Slack | Roadmap | `slack-bolt` |
| WhatsApp | Roadmap | WhatsApp Cloud API (httpx) |
| Email | Roadmap | IMAP/SMTP |
| Web UI | Roadmap | Next.js + WebSocket |
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
from cortexflow.models.router import model_router

result = await model_router.generate(
    "Explain this stack trace...",
    task_type="code_review",
)
print(result.text)   # answered by DeepSeek Coder (or fallback)
print(result.model)  # the actual model used
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
```

---

## CLI

```
cortex start              Start WebSocket gateway + all configured channels
cortex chat               Interactive terminal chat session
cortex config show        Print resolved configuration (JSON)
cortex config init        Write starter config.toml to ~/.cortexflow/
cortex memory prune       Remove low-importance entries from SQLite + Qdrant
cortex version            Print version
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

[gateway]
bind = "127.0.0.1"
port = 7432

[ui]
frontend_port = 3000

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
```

**Current status: 53 tests, all passing.**

---

## Roadmap

```
Phase 1 — Foundation           [DONE]
  ✅ WebSocket gateway (FastAPI)
  ✅ TOML config with ENV secret resolution
  ✅ Channel adapters: Telegram, Discord (base for all others)
  ✅ 3-tier memory retrieval pipeline
  ✅ Task-aware model router (Claude / Gemini / DeepSeek / Ollama)
  ✅ Voice: STT (faster-whisper) + TTS (ElevenLabs / Kokoro / pyttsx3)
  ✅ CLI: cortex start | chat | config | memory | version
  ✅ 53 unit tests passing

Phase 2 — More Channels        [Next]
  ☐ Slack adapter
  ☐ WhatsApp adapter (Cloud API)
  ☐ Email adapter (IMAP/SMTP)
  ☐ Web UI chat page (Next.js)

Phase 3 — Desktop + CLI        [Planned]
  ☐ Tauri v2 desktop app (wraps Next.js)
  ☐ cortex run <task> one-shot execution
  ☐ Plugin system for custom tools

Phase 4 — Intelligence         [Planned]
  ☐ Reflection engine (quality scoring)
  ☐ Proactive reminders and follow-ups
  ☐ Tool use: web search, file ops, calendar

Phase 5 — Polish               [Planned]
  ☐ One-command Docker setup
  ☐ Settings UI
  ☐ Memory visualiser
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

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**CortexFlow** — Built for people who want their AI to actually know them.

[![GitHub](https://img.shields.io/badge/GitHub-TheAmitChandra%2FCortexFlow-181717?style=for-the-badge&logo=github)](https://github.com/TheAmitChandra/CortexFlow)

</div>
