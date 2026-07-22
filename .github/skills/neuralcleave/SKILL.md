---
name: neuralcleave-v2
description: "Use when: building neuralcleave v2 personal AI assistant, implementing channel adapters, writing gateway code, building memory system, voice integration, CLI, frontend, tests, commits, branches, or any task related to the neuralcleave personal assistant project."
---

# neuralcleave v2 — Personal AI Assistant
## Master Skill File — Complete Project Knowledge Base

---

## CRITICAL WORKFLOW RULES (ALWAYS FOLLOW)

### ⛔ ABSOLUTE LAWS — NEVER VIOLATE, NO EXCEPTIONS

> These rules were violated on 2026-05-23: 13 files and 3000+ lines were changed across multiple logical units but only a single commit was made at the end. This is STRICTLY FORBIDDEN.

1. **ONE file changed = ONE immediate commit + ONE immediate push. No exceptions.**
2. **NEVER accumulate multiple file changes before committing.** After every single file create/edit — stop and commit + push that file before touching the next file.
3. **NEVER batch commits.** If you find yourself writing `git add -A` across multiple files, you are violating this rule.
4. **The sequence is non-negotiable:**
   ```
   edit file → git add <that file> → git commit → git push → then edit next file
   ```
5. **Every fix, every bug correction, every test file = its own commit + push immediately.**

### Git Branching Strategy
- **Every module/feature gets its own branch** — never develop on `main`
- Branch naming: `feature/<module-name>` (e.g. `feature/telegram-adapter`, `feature/memory-3tier`)
- Create branch → implement → write tests → tests pass → merge to `main`
- **Commit every change immediately** — atomic commits, one logical change per commit
- **Push every commit immediately** after committing — never batch pushes

### Commit Format
```
<type>(<scope>): <short description>

Types: feat | fix | refactor | test | docs | chore | security
Scopes: gateway | channels | memory | models | voice | cli | frontend | config | tests | docs
```

### Branch Lifecycle
```
git checkout -b feature/<module>

# THE ONLY ALLOWED PATTERN — repeat for every single file:
# 1. Edit/create exactly one file
# 2. Immediately:
git add <that-exact-file>
git commit -m "feat(<scope>): <description>"
git push origin feature/<module>
# 3. Only then move to the next file

# After ALL files done and tests pass:
git checkout main
git merge feature/<module> --no-ff
git push origin main
# DO NOT delete the branch — keep all branches permanently.
```

---

## PROJECT IDENTITY

**Name:** neuralcleave v2  
**Type:** Personal AI Assistant Gateway  
**Vision:** "One intelligent AI, everywhere you communicate — smarter memory, better routing, voice that works."  
**Mission:** Build the most capable open-source personal AI assistant — beating OpenClaw on memory quality, LLM routing intelligence, voice breadth, and web UI — while matching its channel coverage.  
**Primary Language:** Python 3.12+ (backend + channels), TypeScript (frontend)  
**Reference:** https://github.com/openclaw/openclaw (377k stars — what we're surpassing)

---

## WHY neuralcleave v2 EXISTS

OpenClaw (https://github.com/openclaw/openclaw) is a great personal AI assistant — 377k stars, 25+ messaging channels, TypeScript/Node.js monorepo. But it has structural limitations neuralcleave v2 solves:

| OpenClaw Limitation | neuralcleave v2 Solution |
|---|---|
| LanceDB only (flat vector store) | 3-tier memory: Redis (TTL) + Qdrant (semantic) + SQLite (persistent) |
| Single configured model, no routing | Task-aware LLM routing: Claude for reasoning, Gemini Flash for speed, Ollama for privacy |
| No hallucination detection | Reflection engine: quality scorer + auto-retry |
| macOS/iOS wake-word only | OpenWakeWord (cross-platform), faster-whisper STT, Kokoro local TTS |
| Static WebChat widget | Full Next.js dashboard: memory explorer, channel status, metrics |
| In-process plugins (no sandbox) | Subprocess-sandboxed plugins with typed Python SDK |
| Complex YAML config (~50 keys) | Simple TOML config (works in 3 lines) |
| Stdout logs only | structlog JSON + Prometheus metrics + trace IDs |
| TypeScript only | Python ecosystem (best for AI/ML libraries) |

Enterprise code (governance, RBAC, Celery, multi-tenant) lives at:  
https://github.com/TheAmitChandra/neuralcleave-Enterprise

---

## TECHNOLOGY STACK

### Backend (Python)
| Purpose | Technology | Version |
|---|---|---|
| Gateway daemon | FastAPI + WebSocket | 0.115+ |
| Runtime | Python asyncio | 3.12+ |
| Config | tomllib + pydantic | stdlib + v2 |
| STT | faster-whisper | latest |
| TTS cloud | ElevenLabs SDK | latest |
| TTS local | Kokoro | latest |
| Embeddings | sentence-transformers | latest |
| CLI | click + rich | latest |
| Testing | pytest + pytest-asyncio | latest |

### Channel Adapters (Python async)
| Channel | Library |
|---|---|
| Telegram | python-telegram-bot v21 |
| Discord | discord.py v2 |
| Slack | slack-sdk |
| WhatsApp | whatsapp-web.py |
| Email | aiosmtplib + aioimaplib |
| SMS | twilio |
| Matrix | matrix-nio |
| IRC | pydle |

### Frontend (TypeScript)
| Purpose | Technology |
|---|---|
| Framework | Next.js 14 (App Router) |
| Styling | Tailwind CSS + shadcn/ui |
| State | Zustand |
| Workflow UI | React Flow |
| Desktop app | Tauri v2 (wraps Next.js) |
| Testing | Vitest |

### Databases (simplified vs enterprise)
| Purpose | Technology | Note |
|---|---|---|
| Short-term memory | Redis 7+ | TTL-based context |
| Semantic memory | Qdrant | Vector embeddings |
| Long-term memory | SQLite (aiosqlite) | Replaces PostgreSQL for personal use |

### LLM Providers
| Provider | Model | Best For |
|---|---|---|
| Anthropic | Claude Opus 4.8 / Sonnet 4.6 | Complex reasoning |
| Google | Gemini 2.0 Flash | Speed, summarization |
| DeepSeek | DeepSeek-Coder | Code generation |
| Ollama | llama3.2, mistral | Privacy mode, offline |

---

## PROJECT STRUCTURE

```
neuralcleave/
├── .github/
│   ├── skills/
│   │   └── neuralcleave/
│   │       └── SKILL.md              ← THIS FILE
│   └── workflows/                    ← CI/CD (re-enabled in Phase 5)
├── neuralcleave/                       ← v2 Python package (NEW)
│   ├── __init__.py                   ← version, package root
│   ├── config.py                     ← TOML config loader
│   ├── cli.py                        ← click CLI (neuralcleave command)
│   ├── gateway/
│   │   ├── __init__.py
│   │   ├── main.py                   ← FastAPI app entry point
│   │   └── websocket.py              ← WS connection manager
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── base.py                   ← ChannelAdapter ABC
│   │   ├── telegram.py               ← Telegram adapter
│   │   ├── discord_.py               ← Discord adapter
│   │   ├── slack.py                  ← Slack adapter
│   │   ├── whatsapp.py               ← WhatsApp adapter
│   │   └── email_.py                 ← Email IMAP/SMTP adapter
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── retrieval.py              ← 3-tier MemoryRetrievalPipeline
│   │   ├── short_term.py             ← Redis TTL memory
│   │   ├── semantic.py               ← Qdrant vector search
│   │   └── long_term.py              ← SQLite persistent memory
│   ├── models/
│   │   ├── __init__.py
│   │   ├── router.py                 ← task-aware LLM routing
│   │   ├── claude.py                 ← Anthropic adapter
│   │   ├── gemini.py                 ← Google Gemini adapter
│   │   ├── deepseek.py               ← DeepSeek adapter
│   │   └── ollama.py                 ← Ollama local adapter
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── stt.py                    ← faster-whisper STT
│   │   └── tts.py                    ← ElevenLabs + Kokoro TTS
│   └── reflection/
│       ├── __init__.py
│       └── engine.py                 ← Quality scorer + self-correction
├── tests/                            ← v2 test suite (root level)
│   ├── __init__.py
│   └── unit/
│       ├── __init__.py
│       ├── test_config.py
│       ├── test_channels_base.py
│       ├── test_models_router.py
│       └── test_memory_retrieval.py
├── frontend/                         ← Next.js UI (adapted from enterprise)
├── docs/
│   ├── SKILL.md                      ← Copy of this file
│   ├── IMPLEMENTATION_PLAN_v2.md     ← Full build roadmap
│   └── COMPETITIVE_ANALYSIS_vs_OpenClaw.md
├── requirements-v2.txt               ← v2 Python dependencies
├── pyproject.toml                    ← Build config + test settings
└── README.md
```

---

## ARCHITECTURE OVERVIEW

```
┌──────────────────────────────────────────────────────────────────┐
│                   neuralcleave v2 Gateway                          │
│              (FastAPI + WebSocket, Python 3.12)                  │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────────┐ │
│  │   Channel   │  │   Session   │  │     Model Router         │ │
│  │   Manager   │  │   Manager   │  │  task-aware → Claude /   │ │
│  │             │  │  per-channel│  │  Gemini / DeepSeek /     │ │
│  │  Telegram   │  │  isolation  │  │  Ollama + fallback chain │ │
│  │  Discord    │  └─────────────┘  └──────────────────────────┘ │
│  │  Slack      │                                                 │
│  │  WhatsApp   │  ┌─────────────┐  ┌──────────────────────────┐ │
│  │  Email      │  │  Cognitive  │  │   Memory Pipeline (3-tier)│ │
│  │  + more     │  │  Pipeline   │  │  Redis (TTL context)     │ │
│  └─────────────┘  │  plan→exec  │  │  Qdrant (semantic)       │ │
│                   │  →reflect   │  │  SQLite (persistent)     │ │
│  ┌─────────────┐  └─────────────┘  └──────────────────────────┘ │
│  │   Voice     │                                                 │
│  │ STT:Whisper │  ┌────────────────────────────────────────────┐ │
│  │ TTS:Kokoro  │  │  Plugin System (subprocess sandboxed)      │ │
│  └─────────────┘  └────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
         ↑  WebSocket ws://127.0.0.1:7432 + REST API
┌────────┴────────────────────────┐
│  Clients                        │
│  - Next.js Web UI (port 3000)   │
│  - Tauri Desktop App            │
│  - neuralcleave CLI tool        │
└─────────────────────────────────┘
```

---

## WEBSOCKET PROTOCOL

**Endpoint:** `ws://127.0.0.1:7432/ws`  
**Format:** JSON text frames

### Message Types (Client → Server)
```json
{"type": "ping"}
{"type": "subscribe", "channel": "agents"}
{"type": "message", "id": "uuid", "text": "Hello", "session_id": "uuid"}
```

### Message Types (Server → Client)
```json
{"type": "hello", "session_id": "uuid", "version": "2.0.0"}
{"type": "pong", "timestamp": 1234567890.0}
{"type": "subscribed", "channel": "agents"}
{"type": "response", "session_id": "uuid", "text": "...", "model": "gemini-flash"}
{"type": "error", "message": "..."}
```

---

## CHANNEL ADAPTER INTERFACE

All adapters implement `ChannelAdapter` ABC in `neuralcleave/channels/base.py`:

```python
class ChannelAdapter(ABC):
    channel_id: str  # "telegram" | "discord" | "slack" | etc.

    async def connect(self) -> None: ...         # connect to platform
    async def disconnect(self) -> None: ...      # graceful shutdown
    async def send(target, text, *, reply_to, attachments) -> str | None: ...
    def on_message(self, handler: MessageHandler) -> None: ...
    def get_config_schema(self) -> dict: ...     # JSON Schema for config UI
```

### InboundMessage fields
```python
@dataclass
class InboundMessage:
    channel: str           # "telegram" | "discord" | ...
    sender_id: str         # platform user ID
    sender_name: str
    text: str | None
    attachments: list[Attachment]
    thread_id: str | None  # chat_id / channel_id
    reply_to_id: str | None
    timestamp: float
    raw: dict              # platform-native payload for debugging
```

---

## MEMORY SYSTEM (3-TIER)

```
Priority 1: Redis short-term (TTL=3600s) — active session context
Priority 2: Qdrant semantic — dense vector ANN search
Priority 3: SQLite long-term — persistent conversation history
```

`MemoryRetrievalPipeline.retrieve(query, embedding)` returns `RetrievalContext`:
1. Short-term inject (session context first)
2. Semantic search (Qdrant ANN, score_threshold=0.5)
3. Long-term query (SQLite, importance-ranked)
4. Content-hash deduplication
5. Score-rank + cap at top_k
6. Token estimation (4 chars ≈ 1 token)

`MemoryRetrievalPipeline.store_episodic(embedding, payload)` — dedup before storing.

**Pruning (scheduled daily):**
- SQLite: delete rows with `importance_score < 0.2`
- Qdrant: remove near-duplicate points (cosine similarity > 0.95)

---

## MODEL ROUTING TABLE

`ModelRouter.generate(prompt, task_type)` picks the optimal provider:

| task_type | Primary | Fallback |
|---|---|---|
| `complex_reasoning` | Claude Opus 4.8 | Gemini Pro |
| `code_generation` | DeepSeek Coder | Claude Sonnet |
| `code_review` | DeepSeek Coder | Gemini Flash |
| `summarization` | Gemini 2.0 Flash | Ollama |
| `intent_extraction` | Gemini 2.0 Flash | Ollama |
| `task_decomposition` | Claude Sonnet 4.6 | Gemini Pro |
| `cheap_inference` | Ollama llama3.2 | Gemini Flash |
| `general` | Gemini 2.0 Flash | Ollama |

Fallback chain: primary → fast → local → DEGRADED (return error).  
Retry: tenacity with exponential backoff (max 3 attempts per provider).

**Secret resolution:** Config values starting with `ENV:VAR_NAME` are resolved to env vars.

---

## VOICE SYSTEM

### STT — `neuralcleave/voice/stt.py`
```python
class WhisperSTT:
    model_size: str = "base"   # tiny|base|small|medium|large
    language: str | None = None  # None = auto-detect

    async def transcribe(self, audio: bytes | Path) -> str: ...
    async def transcribe_stream(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[str]: ...
```
Uses `faster-whisper` (local, no API key, GPU optional).

### TTS — `neuralcleave/voice/tts.py`
```python
class ElevenLabsTTS:
    async def synthesize(self, text: str, voice: str = "Rachel") -> bytes: ...
    async def stream(self, text: str, voice: str) -> AsyncIterator[bytes]: ...

class KokoroTTS:  # local fallback, no API key
    async def synthesize(self, text: str) -> bytes: ...

class SystemTTS:  # OS fallback (pyttsx3)
    async def synthesize(self, text: str) -> bytes: ...
```

Priority: ElevenLabs (if API key set) → Kokoro (local) → System.

---

## CLI COMMANDS

The `neuralcleave` CLI is built with `click` + `rich`:

```
neuralcleave start [--background] [--config PATH]   # start gateway daemon
neuralcleave stop                                   # stop daemon
neuralcleave status                                 # show channels, memory stats, model
neuralcleave message "text"                         # send to primary agent, print response
neuralcleave channels list                          # show connected channels + status
neuralcleave channels add telegram                  # guided channel setup wizard
neuralcleave channels remove telegram               # disconnect channel
neuralcleave memory search "query"                  # search memory
neuralcleave memory clear                           # reset all memory (confirm prompt)
neuralcleave config edit                            # open config in $EDITOR
neuralcleave update                                 # self-update to latest version
```

---

## CONFIG FORMAT (TOML)

File: `~/.neuralcleave/config.toml`

```toml
[agent]
name = "My Assistant"
model = "auto"            # auto = task-aware routing

[models]
primary = "claude-opus-4-8"
fallback = "gemini-2.0-flash"
fast = "gemini-2.0-flash"
local = "ollama/llama3.2"

[memory]
short_term_ttl = 3600
long_term_days = 90

[voice]
stt = "whisper"           # whisper | none
tts = "elevenlabs"        # elevenlabs | kokoro | system | none
tts_voice = "Rachel"

[channels.telegram]
enabled = true
bot_token = "ENV:TELEGRAM_BOT_TOKEN"

[channels.discord]
enabled = true
bot_token = "ENV:DISCORD_BOT_TOKEN"

[gateway]
port = 7432
bind = "127.0.0.1"

[ui]
web_port = 3000
```

**Secret resolution:** `"ENV:VAR_NAME"` → `os.getenv("VAR_NAME", "")`.

---

## WORKSPACE FILES

`~/.neuralcleave/workspace/` (injected into every LLM system prompt):
- `SOUL.md` — personality, tone, response style
- `TOOLS.md` — custom tool definitions (plain English)
- `MEMORY.md` — long-term memory instructions
- `RULES.md` — explicit rules (never do X, always do Y)

---

## BUILD PHASES

### Phase 0 — Foundation (CURRENT)
`feature/v2-foundation`
- [x] SKILL.md v2 + docs/SKILL.md
- [x] neuralcleave/ package scaffold
- [x] TOML config loader
- [x] Gateway WebSocket server
- [x] ChannelAdapter ABC
- [x] Telegram adapter
- [x] Discord adapter
- [x] 3-tier memory pipeline
- [x] Task-aware model router
- [x] Voice STT + TTS
- [x] click CLI
- [x] Unit tests

### Phase 1 — Core Channels + Memory
`feature/telegram-live` / `feature/discord-live` / `feature/memory-3tier`
- Working Telegram + Discord (real polling)
- Redis short-term memory wired
- Qdrant semantic search live
- SQLite long-term live
- Web UI adapted (remove enterprise pages)

### Phase 2 — More Channels + Voice
`feature/slack-adapter` / `feature/whatsapp-adapter` / `feature/voice`
- Slack, WhatsApp, Email adapters
- Whisper STT wired to voice notes
- ElevenLabs TTS responses
- Kokoro local fallback

### Phase 3 — Desktop + CLI
`feature/tauri-desktop` / `feature/cli-complete`
- Tauri v2 desktop app
- Full CLI with all commands
- System tray + native notifications

### Phase 4 — OpenClaw Parity
`feature/channels-extended` / `feature/wake-word`
- SMS, Matrix, IRC, Signal, Mastodon adapters
- OpenWakeWord cross-platform wake-word
- Memory timeline UI
- TTS voice cloning

### Phase 5 — Polish + Release
`feature/ci-reenable` / `feature/installer`
- Re-enable GitHub Actions CI
- One-command install: `pip install neuralcleave`
- `neuralcleave init` setup wizard
- Docs site (mkdocs)
- Docker image + Tauri installers

---

## TESTING REQUIREMENTS

Every branch must pass before merging to main:
```bash
# v2 tests (root-level)
pytest tests/ -v

# Frontend
cd frontend && pnpm test
```

Test naming: `test_<module>_<function>_<scenario>`

Coverage: minimum 80% for new modules.

---

## ENVIRONMENT VARIABLES

```bash
# LLM APIs
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
DEEPSEEK_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434

# Channel tokens (also configurable via config.toml ENV: syntax)
TELEGRAM_BOT_TOKEN=...
DISCORD_BOT_TOKEN=...
SLACK_APP_TOKEN=...

# Voice
ELEVENLABS_API_KEY=...

# Memory
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=                  # empty for local
```

---

## IMPLEMENTATION RULES

1. **Python style:** black (line-length=100), isort (profile=black), type hints everywhere
2. **Async first:** use `async/await` for all I/O — no blocking calls on the event loop
3. **Dataclasses + Pydantic:** dataclasses for internal structs, Pydantic for API schemas
4. **Secret resolution:** always call `_resolve_secret(value)` for config strings that may be `ENV:*`
5. **Graceful degradation:** if a channel fails to connect, log + skip (don't crash the gateway)
6. **No hardcoded secrets:** all API keys via env vars or config.toml `ENV:` references
7. **One responsibility per file:** small, focused modules
8. **Channel adapters:** must handle ImportError gracefully (library not installed = clear error message)
9. **Tests:** mock all network calls (pytest-mock) — no real API calls in unit tests
10. **Comments:** only where WHY is non-obvious — never explain what the code does

---

## QUICK-START COMMANDS

```bash
# Start all infra (dev)
docker compose -f deploy/docker-compose.dev.yml up -d

# Run gateway
python -m neuralcleave.gateway.main

# Run CLI
python -m neuralcleave.cli start

# Run tests
pytest tests/ -v --cov=neuralcleave

# Frontend dev
cd frontend && pnpm dev
```

---

## HOW WE BEAT OPENCLAW — SUMMARY

| Dimension | OpenClaw | neuralcleave v2 |
|---|---|---|
| Memory | LanceDB (flat) | 3-tier: Redis + Qdrant + SQLite |
| LLM routing | Single model | Task-aware: Claude/Gemini/DeepSeek/Ollama |
| Voice | macOS/iOS only | Cross-platform Whisper + Kokoro |
| Web UI | Static chat widget | Full Next.js dashboard + memory explorer |
| Plugin security | In-process (full trust) | Subprocess (sandboxed) |
| Config | Complex YAML (~50 keys) | Simple TOML (3 lines minimum) |
| Hallucination | None | Reflection engine + quality scoring |
| Observability | stdout only | structlog JSON + Prometheus metrics |
| Desktop | Swift/Kotlin native | Tauri (cross-platform, one codebase) |
| Language | TypeScript/Node.js | Python (best AI/ML ecosystem) |

---

## NON-GOALS (v2)

neuralcleave v2 does NOT aim to:
- Build enterprise multi-tenant platforms (that is neuralcleave-Enterprise)
- Implement RBAC, governance, or approval workflows
- Run Celery workers or complex task queues
- Require PostgreSQL or Neo4j
- Replace human judgment in safety-critical decisions

neuralcleave v2 IS for:
- Individual users wanting AI across all their messaging apps
- Developers wanting a local-first, privacy-preserving AI assistant
- Users wanting smarter memory, better LLM routing, and cross-platform voice
