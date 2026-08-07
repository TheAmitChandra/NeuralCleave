# NeuralCleave vs OpenClaw — Competitive Strategy
**August 2026 | Solo developer edition**

---

## 1. Executive Summary

NeuralCleave (CortexFlow) and OpenClaw are attacking the same problem: a self-hosted personal AI gateway that works across every messaging channel you already use. OpenClaw is the incumbent — MIT-licensed, non-profit backed, 200+ contributors, 3.3 MB changelog, and native apps for every platform. NeuralCleave is newer, smaller, and solo-built, but it has architectural advantages that OpenClaw cannot easily replicate because of its fundamental technology choice (Node.js vs Python).

**The one-line positioning:**
> OpenClaw is the everything-gateway for power users who want every feature. NeuralCleave is the AI-native gateway for users who want the model to *think*, *route intelligently*, and *extend itself* — with a voice-first, privacy-first design built on the Python AI stack.

This document maps both projects, identifies where NeuralCleave already wins, where OpenClaw dominates, and what to build next to pull ahead in the segments we can realistically own.

---

## 2. Project Snapshot — NeuralCleave Today

| Dimension | State |
|---|---|
| Version | 2.1.5 |
| License | BUSL-1.1 (source-available; converts to open-source after 4 years) |
| Runtime | Python 3.12 + FastAPI + Uvicorn |
| Frontend | Next.js 14 (App Router) + Tauri v2 desktop |
| Channels | 32 adapters |
| LLM providers | 13 providers, 19+ model aliases |
| Voice | STT (faster-whisper) · TTS 3-tier (ElevenLabs → Kokoro → pyttsx3) · wake word (OpenWakeWord) |
| Memory | 3-tier: Redis short-term + Qdrant semantic + SQLite long-term |
| Canvas | 7 block types, live WebSocket push, auto chart routing |
| Tests | 6,016 Python unit tests (99.7% coverage) + 236 frontend tests |
| Desktop | Windows/macOS/Linux (Tauri v2, PyInstaller sidecar) |
| Mobile | None |

### What's built and working
- 32 channel adapters (Telegram, Discord, WhatsApp, Signal, Slack, Teams, Matrix, XMPP, IRC, Nostr, Bluesky AT Protocol, Tlon/Urbit, LINE, Feishu, WeChat Work, QQ Bot, Zalo, Mastodon, Twitch, Viber, SMS/Twilio, email, Mattermost, Nextcloud, Rocket.Chat, Google Chat, Synology, iMessage, Facebook Messenger, Twilio Voice, generic webhook/WebSocket)
- Task-aware model routing: 10 task types, each with its own primary + fallback chain across 13 providers
- Auto-complexity detection (bumps general → complex_reasoning or cheap_inference without user involvement)
- Claude Extended Thinking — captures thinking traces
- Privacy mode (one flag → 100% local Ollama, zero external calls)
- 3-tier TTS fallback with voice cloning (ElevenLabs) and zero-API-key local option (Kokoro → pyttsx3)
- Cross-platform wake word (OpenWakeWord, works on Windows/macOS/Linux)
- VAD calibration, PTT, continuous voice listening, voice note round-trip on messaging channels
- Self-modifying skills — the AI writes, validates, and hot-loads new Python skills mid-conversation (WriteSkillTool)
- Hub marketplace with AST-level + regex dual-pass security scanner
- Canvas: 7 block types, auto chart routing (CHART_DATA protocol), live WebSocket diff push
- Workspace personality system (SOUL/TOOLS/MEMORY/RULES markdown files — zero-code behavior customization)
- Docker + SSH + local subprocess sandbox with API-key-stripped environment
- Full PyInstaller + Tauri desktop pipeline (single installer, orphan sidecar recovery, global hotkey)
- Prometheus-compatible metrics, structured JSON logging
- Proactive scheduler (5-field cron, no external dep)
- PWA with service worker, Web Push (VAPID)
- Multi-agent orchestrator (AgentOrchestrator with keyword/channel routing)
- Self-hosted hub marketplace for plugins

### Known gaps (honest accounting)
- **Semantic memory is wired but not firing**: Qdrant is set up but the pipeline never computes embeddings — `embedding=None` is always passed. The vector tier is architecturally present but functionally inert in production.
- **No MCP support**: No MCP server or MCP client. OpenClaw is bidirectional MCP (serves and consumes). This is a growing ecosystem gap.
- **No mobile app**: No iOS or Android companion. OpenClaw has Swift iOS + Kotlin Android + WatchOS + Wear OS.
- **Single-round tool use only**: One tool call per generation cycle. No multi-step agent loop (tool → result → tool → result).
- **Settings UI incomplete for new providers**: 8 of 13 providers (Mistral, xAI, Cohere, Moonshot, Zhipu, Qwen, ERNIE, Doubao) require manual `config.toml` edits — no Settings page form fields.
- **Canvas WebSocket not connected in frontend**: The `/ws/canvas` endpoint exists and works; the Next.js canvas page uses polling (TanStack Query REST) instead of subscribing to the WebSocket.
- **Orchestrator not auto-started**: `AgentOrchestrator` is complete but not wired into `gateway/main.py` lifespan — it's only accessible via tests and manual REST injection.
- **No multi-turn streaming tool use**: The streaming path buffers the entire generation to detect `TOOL_CALL:` markers, defeating streaming latency for tool-using conversations.
- **No config hot-reload**: Gateway restart required for most config changes. OpenClaw hot-reloads `openclaw.json` without restart.
- **No exec approval manager**: Shell tool runs without operator review. OpenClaw has an approval flow with push notifications for dangerous commands.
- **Documentation is thin**: Static HTML docs-site; no searchable reference. OpenClaw has Mintlify with 100+ pages.

---

## 3. OpenClaw Snapshot

| Dimension | State |
|---|---|
| Version | 2026.7.2 (calendar versioning) |
| License | MIT |
| Runtime | Node.js 24 (TypeScript ESM) |
| UI | Lit web components + Vite (Control UI) |
| Channels | ~30+ (including WhatsApp, Signal, iMessage, Discord, Slack, Teams, Matrix, IRC, QQ, LINE, Feishu, Zalo, Twitch, Nostr, Tlon, Mattermost, Nextcloud, Rocket.Chat, Google Chat, Synology, Viber, SMS, Voice Call, Twitch, Raft P2P) |
| LLM providers | 35+ (every major provider, plus 15+ minor/regional) |
| Voice | TTS (ElevenLabs, Fish Audio, Azure/DeepGram, Inworld, local MLX-TTS on macOS) · STT (Deepgram) |
| Memory | Multi-tier file-based + LanceDB vector (with actual embeddings) + background dreaming consolidation |
| Canvas | HTML/CSS/JS canvas served by Gateway HTTP; A2UI reactive renderer |
| Tests | 195+ Vitest shards |
| Desktop | macOS (Swift), Linux (Tauri), Windows (WinUI) |
| Mobile | iOS (Swift, full app + WatchOS), Android (Kotlin + Wear OS) |
| Backing | OpenClaw Foundation (non-profit), 200+ contributors, OpenAI/NVIDIA/Vercel sponsors |
| Plugin market | ClawHub (clawhub.ai) with publisher verification and provenance |

### OpenClaw's structural advantages
1. **JavaScript ecosystem**: npm is the largest package registry. OpenClaw plugins are npm packages — instantly publishable, instantly installable. Python's PyPI is strong but Node dominates web/tooling integrations.
2. **Native mobile apps**: iOS + watchOS + Android + Wear OS. NeuralCleave has zero mobile presence.
3. **macOS depth**: Swift menu-bar app with Bonjour discovery, animated "Molty" tray icon, HealthKit, screen recording, location, camera. The macOS experience is polished and genuinely OS-native.
4. **Memory that actually works**: LanceDB with real embedding models; background dreaming consolidation (Light → REM → Deep) promotes episodic to curated memory without blocking replies.
5. **Plugin SDK breadth**: Full-surface TypeScript plugin API — channels, providers, tools, harnesses, memory, TTS, voice, media generation, embeddings, hooks, CLI backends. Every capability surface is extensible.
6. **MCP bidirectional**: OpenClaw as MCP server (exposes channel conversations to Claude Code, Codex, Cursor) and MCP client (manages outbound MCP server connections). This is a growing ecosystem.
7. **Security posture**: Dedicated `openclaw security audit` CLI command, exec approval manager with push notifications, Docker sandbox, device pairing with Ed25519 challenge signing, formal verification artifacts.
8. **Deployment maturity**: Fly.io, Render, Railway, Kubernetes, Nix, Raspberry Pi, Tailscale Serve/Funnel with identity-aware auth — all documented. Config hot-reload without restart.
9. **Community velocity**: 3.3 MB changelog, weekly releases, Foundation backing, ClawHub marketplace, DeepWiki integration, 66 KB `AGENTS.md` for AI-assisted contribution.

---

## 4. Head-to-Head Feature Map

| Feature | NeuralCleave | OpenClaw | Winner |
|---|---|---|---|
| **Channels** | 32 adapters | ~30 | Tie (NC has more unique decentralized channels) |
| **LLM providers** | 13 | 35+ | OpenClaw |
| **Task-aware model routing** | Yes (10 task types, auto-routing) | No (manual model selection) | **NeuralCleave** |
| **Auto-complexity detection** | Yes | No | **NeuralCleave** |
| **Privacy mode (one flag → local)** | Yes | Partial (local models supported but no one-flag mode) | **NeuralCleave** |
| **Claude Extended Thinking** | Yes (captures thinking trace) | Yes | Tie |
| **Chinese AI providers** | 6 (Qwen, GLM, ERNIE, Doubao, Moonshot, DeepSeek) | 6+ (via extensions) | Tie |
| **Local model support** | Ollama | Ollama, llama.cpp, LM Studio, SGLang, vLLM | OpenClaw |
| **Wake word** | OpenWakeWord (cross-platform) | macOS-only (MLX) | **NeuralCleave** |
| **TTS** | 3-tier (ElevenLabs → Kokoro → pyttsx3) | ElevenLabs, Fish Audio, Azure, Inworld, MLX (macOS) | Tie (NC has better local fallback) |
| **Voice cloning** | Yes (ElevenLabs) | Yes (ElevenLabs) | Tie |
| **STT** | faster-whisper (local, free) | Deepgram (cloud, paid) | **NeuralCleave** (local + free) |
| **Voice note round-trip** | Yes | Yes | Tie |
| **Semantic memory** | Architecturally wired, functionally broken | LanceDB with real embeddings | OpenClaw |
| **Memory dreaming/consolidation** | No | Yes (3-phase background) | OpenClaw |
| **Self-modifying skills (AI writes code)** | Yes (WriteSkillTool) | No | **NeuralCleave** |
| **Workspace personality system** | Yes (SOUL/TOOLS/MEMORY/RULES) | Yes (AGENTS.md, SOUL.md, USER.md) | Tie |
| **Canvas** | 7 block types, auto chart routing | HTML/JS canvas, A2UI renderer | Tie |
| **Auto chart routing** | Yes (CHART_DATA protocol) | No (requires explicit tool call) | **NeuralCleave** |
| **MCP server** | No | Yes | OpenClaw |
| **MCP client** | No | Yes | OpenClaw |
| **Plugin system** | Hub marketplace (PyPI-based) | ClawHub (npm-based, publisher verified) | OpenClaw (more mature) |
| **Desktop app** | Tauri v2 (Win/Mac/Linux) | macOS Swift + Linux Tauri + Windows WinUI | OpenClaw (native macOS/Windows) |
| **Mobile** | None | iOS + WatchOS + Android + Wear OS | OpenClaw |
| **Multi-agent orchestration** | Yes (keyword/channel routing) | Yes (Task Flow, sub-agents, ACP, Codex) | OpenClaw (more sophisticated) |
| **Cron/automation** | Yes (5-field, no dep) | Yes (SQLite-backed) | Tie |
| **Config hot-reload** | No | Yes | OpenClaw |
| **Exec approval manager** | No | Yes (with push notifications) | OpenClaw |
| **Security scanner** | AST + regex dual-pass (hub) | `openclaw security audit` CLI | Tie (different surfaces) |
| **Docker sandbox** | Yes | Yes | Tie |
| **SSH sandbox** | Yes | No | **NeuralCleave** |
| **Web search** | DuckDuckGo scraper | Brave, Exa, Firecrawl, Tavily, Perplexity, 9 others | OpenClaw |
| **Browser automation** | Playwright (requires separate install) | Puppeteer/CDP (bundled) | OpenClaw |
| **Streaming tool use** | No (buffers generation) | Yes | OpenClaw |
| **PWA / Web Push** | Yes | No (Control UI is not PWA) | **NeuralCleave** |
| **Prometheus metrics** | Yes (built-in, no external dep) | Yes (via diagnostics-prometheus extension) | Tie |
| **Structured logging** | Yes | Yes | Tie |
| **Test coverage** | 6,016 tests, 99.7% coverage | 195 Vitest shards (comprehensive) | Tie |
| **Documentation** | Static HTML, thin | Mintlify, 100+ pages | OpenClaw |
| **Community** | Solo | 200+ contributors, Foundation, sponsors | OpenClaw |
| **License** | BUSL-1.1 (source-available) | MIT (fully open) | OpenClaw |

---

## 5. Where NeuralCleave Already Wins

These are genuine advantages, not just "we have it too":

### 5.1 Task-Aware Model Routing (No competitor has this)
OpenClaw lets users pick a model. NeuralCleave *decides* which model is best for each request:
- `complex_reasoning` → Claude Opus 4.8 (best thinking)
- `code_generation` → DeepSeek Coder (best code, cheapest)
- `summarization` → Gemini Flash (fast, cheap)
- `intent_extraction` → Gemini Flash (10-token classification, sub-50ms)
- `cheap_inference` → Ollama (free, local)

Plus auto-complexity detection that upgrades/downgrades the task type without user involvement. A user asking "what is 2+2" never pays Claude Opus rates. A user asking "architect this distributed system" gets the best model automatically.

**Why this is hard to copy**: OpenClaw is TypeScript with a plugin-based provider system. Adding routing logic means modifying a complex plugin architecture. NeuralCleave's routing is a first-class Python dataclass — easy to extend and expose in UI.

### 5.2 Self-Modifying Skills (Unique to NeuralCleave)
The AI can write new Python functions, AST-validate them, pass the blocked-import security scanner, and hot-load them as callable tools — all during a conversation, without restarting the gateway.

No other personal AI gateway has this. OpenClaw has Skill files (Markdown instruction packs) but they are static prompts. NeuralCleave's skills are executable Python code that the AI authors and invokes.

**Use case**: "Build me a tool that fetches my Notion tasks and summarizes overdue ones every morning." The AI writes the skill, it's live in 10 seconds, no code deployment needed.

### 5.3 Python AI Stack = Native Access to Every AI Library
OpenClaw is Node.js. It can call AI libraries via REST APIs or subprocess. NeuralCleave is Python — the native language of AI/ML. This means:
- **faster-whisper** locally in-process (no subprocess, no HTTP round-trip, no API key)
- **Kokoro** local neural TTS in-process (no API key, runs offline)
- **OpenWakeWord** in-process (works on all platforms, no cloud dependency)
- **sentence-transformers** for real embedding-based semantic memory (once wired — currently our biggest gap to close)
- **HuggingFace transformers** for local classification, summarization, embedding
- **PyTorch / ONNX** for custom inference without external APIs
- **ComputerVision** libraries (opencv, PIL) for image understanding locally

This is a moat OpenClaw cannot easily cross. Rewriting to Python would be a full rebuild.

**Positioning**: NeuralCleave is "built on the AI stack, not around it."

### 5.4 Privacy Mode — Genuine One-Flag Local
Set `model = "auto"` + `privacy_mode = true` in config and every request goes through Ollama. Zero external API calls. All three voice components (STT via faster-whisper, TTS via Kokoro or pyttsx3, wake word via OpenWakeWord) also run 100% locally.

OpenClaw supports local models but the user must manually configure each component. NeuralCleave's privacy mode is a single flag that routes everything.

**Target user**: Anyone in regulated industries (healthcare, legal, finance), anyone in privacy-sensitive jurisdictions, anyone with air-gapped setups.

### 5.5 Cross-Platform Wake Word
OpenClaw's local TTS uses MLX (macOS Apple Silicon only). NeuralCleave uses OpenWakeWord which runs on Windows, macOS, and Linux with identical API. This is a genuine differentiator for the majority of users on Windows.

### 5.6 Free Local STT
OpenClaw's STT integration is Deepgram (cloud, paid at scale). NeuralCleave bundles faster-whisper — local, free, runs on CPU without a GPU. A user transcribing voice notes throughout the day pays $0 to NeuralCleave. With Deepgram they accumulate API costs.

### 5.7 Auto Chart Routing (CHART_DATA Protocol)
When the AI outputs `CHART_DATA: {"type":"bar","labels":[...],"values":[...]}`, NeuralCleave automatically pushes a rendered chart to the canvas. No tool call required, no user interaction needed. The AI just produces a labeled line in its response and the chart appears.

OpenClaw's canvas requires an explicit tool call from the agent. NeuralCleave's approach is simpler and more reliable — the AI doesn't need to know canvas API details, just output a structured line.

### 5.8 Hub Marketplace with AST Security Scanner
Every plugin submitted to the hub goes through a dual-pass security gate: AST walk blocking 13 dangerous import categories, followed by regex scanning for 14 dangerous patterns (eval, exec, socket.connect, urllib.request, os.system, etc.). This is specifically designed to block API-key exfiltration and arbitrary code execution.

OpenClaw's ClawHub has publisher verification and provenance but no documented AST-level scanner. NeuralCleave's scanner is purpose-built for the "this plugin might steal your API keys" threat model.

### 5.9 SSH Sandbox Mode
NeuralCleave supports executing code in a remote SSH environment (via asyncssh) — useful for users who want the assistant to run code on a dedicated server, not their local machine. OpenClaw has Docker sandbox but no SSH execution backend.

### 5.10 PWA with Web Push
NeuralCleave is installable as a Progressive Web App with offline support (service worker) and Web Push notifications (VAPID/EC P-256). A user can "install" the web UI on their phone without a native app and receive push notifications. OpenClaw's Control UI is a standard web app, not a PWA.

---

## 6. Where OpenClaw Dominates (Honest Gaps)

### 6.1 Native Mobile
iOS + WatchOS + Android + Wear OS. This is a 2–3 person-year investment. Without mobile, NeuralCleave is a desktop/server product. OpenClaw is everywhere. This is the biggest single gap in raw user reach.

**Mitigation near-term**: PWA on mobile. It's not native but it's installable, receives push notifications, and works offline for cached messages. Ship the PWA story prominently.

### 6.2 Memory That Actually Works
OpenClaw's LanceDB memory with real embeddings and background dreaming consolidation is genuinely sophisticated. NeuralCleave's semantic tier has Qdrant wired but the pipeline passes `embedding=None` — the vector store is never actually queried semantically. This is the most embarrassing internal gap.

**Fix**: Add `sentence-transformers` (all-MiniLM-L6-v2, 80 MB, runs CPU) to the pipeline. One call: `model.encode(text)`. Wire into `CognitivePipeline`. This is a 50-line fix that turns the biggest weakness into a genuine strength.

### 6.3 Plugin Ecosystem Maturity
ClawHub has publisher verification, provenance chains, 100+ official and community extensions. NeuralCleave's Hub has 3 example plugins. This is a community problem, not a technical one — but the gap is wide.

### 6.4 Provider Count (35+ vs 13)
OpenClaw has 22 more LLM providers. Most are rarely used (Lobster, Arcee, Baseten, Chutes...) but the count looks better in feature comparisons. More importantly, image/video/music generation providers (DALL-E, fal.ai, Runway, PixVerse) are missing from NeuralCleave entirely.

### 6.5 MCP
MCP (Model Context Protocol) is growing fast as the standard for AI tool interoperability. OpenClaw exposes channel conversations as MCP tools consumable by Claude Code, Codex, Cursor. NeuralCleave has no MCP surface at all. As the MCP ecosystem grows, this becomes an integration gap.

### 6.6 Config Hot-Reload
OpenClaw watches `openclaw.json` and applies changes without restart. NeuralCleave requires a gateway restart for most config changes. For a long-running background service this is a real UX gap.

### 6.7 Documentation
OpenClaw's Mintlify docs (100+ pages, searchable, versioned) vs NeuralCleave's static HTML site. Users evaluating both will find OpenClaw much easier to understand and get started with.

### 6.8 Multi-Step Agentic Tool Use
OpenClaw's agent loop supports multi-step tool chains: tool → result → decision → another tool → result. NeuralCleave's tool use is single-round-trip only. Complex tasks requiring multiple tool calls require multiple user messages.

---

## 7. Strategic Differentiation — Where NeuralCleave Can Win

These are the segments where NeuralCleave can realistically claim territory:

### 7.1 The "AI-Native" Gateway (vs "JavaScript Gateway with AI Plugins")
**Thesis**: OpenClaw treats AI as a plugin. NeuralCleave *is* the AI stack.

Because NeuralCleave is Python, it can do things at the AI layer that OpenClaw cannot: local inference in-process, direct HuggingFace model loading, real embedding computation, custom fine-tuned model hosting, and self-modifying code execution. OpenClaw is a great message router with AI capabilities. NeuralCleave should be positioned as an AI runtime that also handles messaging.

**Concrete headline features to build toward this story**:
- Real semantic memory (sentence-transformers, fix the embeddings gap now)
- Local image understanding (via transformers/CLIP)
- Custom model hosting (load any HuggingFace model as a provider)
- AI-written skills that call HuggingFace models directly

### 7.2 Privacy-First / Air-Gapped
**Thesis**: The only AI assistant that works 100% offline, with zero external API calls, and passes a security audit.

NeuralCleave already has: local STT (faster-whisper), local TTS (Kokoro), local LLM (Ollama), local wake word (OpenWakeWord), local vector memory (in-process cosine fallback), local hub security scanner (AST-level). Adding local embeddings (all-MiniLM-L6-v2) would complete the picture.

**Target users**: Medical practices, law firms, intelligence/defense contractors, privacy advocates, anyone in the EU post-GDPR enforcement, users in countries where cloud AI is restricted.

**One differentiator to add**: A "privacy audit report" — a command that lists every external API call the gateway has made in the last session, so users can verify the privacy claim. OpenClaw has no equivalent.

### 7.3 Asia-Pacific Users
NeuralCleave has 6 Chinese AI providers (Qwen, GLM, ERNIE, Doubao, Moonshot, DeepSeek) and 9 Asia-specific channels (LINE, Feishu, WeChat Work, QQ Bot, Zalo, Synology, Tlon, Baidu Doubao adapters). With the Python stack, adding Baidu PaddlePaddle, iFLYTEK, Sensetime, etc. is feasible.

The documentation and onboarding are currently English-only. Translating the README and docs-site into Chinese, Japanese, and Korean would open a user segment OpenClaw doesn't actively target.

### 7.4 Developer Who Wants a Personal AI That Codes For Itself
**Thesis**: Your assistant should be able to add new capabilities mid-conversation.

The self-modifying skills feature is unique and genuinely compelling for developers. The pitch: "Ask your assistant to add a new tool. Watch it write the code, validate it, and activate it — in 10 seconds, without restarting anything."

Build this story with:
- A dedicated skills gallery (show what skills community members have built and shared)
- Skills that call local HuggingFace models (demonstrate Python-stack advantage)
- Skills that connect to developer tools (GitHub, Linear, Jira, Figma) without needing a formal plugin

### 7.5 The Voice-First Personal Assistant
OpenClaw's voice is an add-on (ElevenLabs TTS plugin, Deepgram STT). NeuralCleave's voice is architecturally wired from the start: wake word → continuous listener → VAD → STT → pipeline → TTS reply, all in one system.

**The differentiation**: "The only self-hosted AI assistant where you can walk up, say 'hey Jarvis', ask a question, and hear the answer — without touching your phone or keyboard."

To own this space: fix the voice WebSocket client in the frontend, add visible PTT button in the chat UI, and add a dedicated Voice page in the dashboard showing wake word status, active session, recent voice interactions.

---

## 8. Recommended Next Steps (Priority Order)

### P0 — Fix the biggest internal lie (this week)
**Wire embeddings into the semantic memory tier.**
The Qdrant tier passes `embedding=None` everywhere. Add `sentence-transformers` (`all-MiniLM-L6-v2`, 80 MB, pure CPU, Apache 2.0). One call in `CognitivePipeline` before `MemoryRetrievalPipeline.retrieve()`. This turns the biggest internal gap into a genuine differentiator that OpenClaw's Node.js stack cannot replicate without subprocess/HTTP overhead.

Files: `neuralcleave/agent/pipeline.py` (add embedding call), `neuralcleave/memory/retrieval.py` (consume the embedding parameter).

### P1 — Wire the orchestrator into the gateway lifespan
`AgentOrchestrator` is complete but never started. Add `set_orchestrator()` call in `neuralcleave/gateway/main.py` lifespan startup. This makes multi-agent routing live for all users, not just tests.

### P2 — Connect the canvas WebSocket in the frontend
The `/ws/canvas` endpoint works; the Next.js canvas page polls via REST. Replace the TanStack Query polling with a `useEffect` WebSocket subscription. Blocks with CHART_DATA already route correctly on the backend — the frontend just needs to subscribe instead of poll.

### P3 — Add MCP server support
MCP is becoming the standard integration layer for AI tools. Exposing NeuralCleave's channel conversations as MCP tools (consumable by Claude Code, Cursor, Codex) would make NeuralCleave part of the growing MCP ecosystem. The FastAPI + asyncio stack is a natural fit for an MCP stdio server.

### P4 — Settings UI for all 13 providers
The 8 new providers require `config.toml` edits. Add form fields to the Settings page. This removes the biggest onboarding friction point for new users who want to use Mistral, xAI Grok, Cohere, etc.

### P5 — Config hot-reload
Add `watchfiles` (zero-dependency file watcher) to detect `config.toml` changes and reload non-structural config (model settings, API keys, voice settings) without gateway restart. Do not need to reload channel connections or database pools.

### P6 — Voice UI in the chat page
Add a visible PTT button and wake word status indicator to the main chat page. The backend voice pipeline is complete; the frontend doesn't surface it prominently. This is the entry point for the voice-first positioning story.

### P7 — Privacy audit command
`neuralcleave privacy report` — lists every outbound HTTP call made in the last N sessions (provider, endpoint, tokens sent/received) so users can verify the privacy claim. This is a unique feature that matches NeuralCleave's positioning and has no OpenClaw equivalent.

### P8 — Mintlify (or equivalent) documentation
Replace the static HTML docs-site with searchable, versioned documentation. Mintlify has a free tier. This is table-stakes for competing with OpenClaw in evaluation contexts.

### P9 — Skills gallery (community differentiation)
A simple gallery page (could be a GitHub Discussions thread or a static page) showing community-built skills with copy-paste installation. This seeds the ecosystem for the "AI that extends itself" positioning.

### P10 — Multi-step tool chains
Extend the tool call protocol from single-round-trip to multi-step. The pipeline already handles one `TOOL_CALL:` detection → re-generation cycle. Extend to N cycles with a step counter and loop detection. This unlocks complex agentic behavior without a full agent framework rewrite.

---

## 9. Positioning Statement for neuralcleave.com

**Headline**: Your personal AI assistant — built on the AI stack, not bolted onto it.

**Sub-headline**: 32 messaging channels. 13 AI providers. 100% local voice. Self-modifying skills. Privacy mode that actually means it.

**Three pillars**:
1. **AI-native** — Python runtime with direct access to HuggingFace, faster-whisper, Kokoro, OpenWakeWord, and sentence-transformers. The model runs in-process, not behind an HTTP proxy.
2. **Privacy-first** — One flag enables full local mode: local LLM (Ollama), local STT (faster-whisper), local TTS (Kokoro), local wake word (OpenWakeWord), local embeddings (sentence-transformers). Zero external API calls, auditable.
3. **Self-extending** — The AI writes new tools mid-conversation. AST-validated, security-scanned, hot-loaded. No restart. No deploy. No code review.

**Choose NeuralCleave over OpenClaw when**:
- You want the AI to *decide* which model fits each request (smart routing), not choose manually
- You need 100% local, air-gapped operation (medical, legal, government, privacy)
- You want voice that works on Windows, not just macOS
- You want the AI to extend itself with new Python tools — no plugin marketplace required
- You prefer Python and want direct access to the HuggingFace/PyTorch ecosystem
- You're in Asia-Pacific and need Chinese AI providers + Asian messaging channels

---

## 10. Summary Table

| What | Status |
|---|---|
| NeuralCleave version | 2.1.5 |
| Feature parity with OpenClaw (core) | ~75% |
| Genuine leads over OpenClaw | 10 features (routing, self-modifying skills, local voice, privacy mode, cross-platform wake word, free local STT, auto chart routing, AST security scanner, SSH sandbox, PWA) |
| Biggest internal gap to fix first | Semantic memory embeddings (50-line fix, massive impact) |
| Biggest external gap | No mobile app |
| Best near-term differentiation story | AI-native (Python stack) + Privacy-first + Self-extending |
| Next milestone | Wire embeddings + MCP server + Voice UI |
