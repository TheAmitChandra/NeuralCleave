# NeuralCleave vs OpenClaw — Gap Analysis & Build Plan (Round 8)
**2026-08-30 | Companion to `COMPETITIVE_ANALYSIS_2026_08_30_ROUND7.md` (Round 7, closed 2026-08-30)**

> Round 7 shipped seven fixes on branch `fix/canvas-ws-origin-check` (17 commits, not yet merged to `main`): the missing `/ws/canvas` origin check plus a `127.0.0.1` branch in `ORIGIN_REGEX`; a `client_id`-based stable `sender_id` for the web/desktop chat socket; the PWA shell's WS protocol mismatch and `/push/notify`'s fabricated `sent` count; binding `ConfigWatcher` to the config file `load_config()` actually read; an audit log for the embedded terminal; and a Hub-fetch hardening drive-by. This round had the usual two jobs: re-verify those end-to-end against the current working tree, and sweep for new gaps. **All seven of Round 7's fixes re-verified clean** — the first round in this series with no partial or regressed fix, and a marked improvement on Round 7's own two-of-four result. The OpenClaw half came back empty for the third consecutive round, again verifiably rather than by assumption: a fresh `git fetch` shows `origin/main` is still byte-identical to `4f3d6af7352a`, the same commit Rounds 6 and 7 snapshotted. So 100% of this round's material is NeuralCleave's own.
>
> The fresh sweep went to three subsystems no prior round has touched — cost/usage tracking, the Tauri desktop shell's Rust layer, and the backup/restore round trip — and found this project's signature bug class in its purest form yet. **The entire cost-estimation feature reaches a real user through exactly zero working surfaces.** Its CLI reads the wrong process's counters and can never print a non-empty table; its REST endpoint has no caller in the shipped product; and even in the Prometheus scrape where the number does survive, the pricing table cannot price the default model of six of the ten task types, so it reports `$0.0000` for the routes a fresh install actually uses.

**Method note:** every claim below was checked against actual source in this repo *on the current branch* (`fix/canvas-ws-origin-check`, 17 commits ahead of `main`), tracing full call chains from the real gateway startup path (`gateway/main.py`'s `create_app()` and `_build_lifespan()`), the same discipline every prior round has used. No finding is included on the strength of a symbol grep alone; §5.1's pricing-coverage table was produced by *executing* `estimate_cost_usd()` against every model constant in `models/router.py`'s live `_ROUTING`/`_PROVIDER_TO_MODEL` tables, not by eyeballing the prefixes. OpenClaw's local clone (`c:/Amit-Projects/AI-Projects/Openclaw`) was re-fetched from its remote during this round and compared against Round 7's cited snapshot by `git rev-parse`, `git log`, and `git diff --stat`.

---

## 1. Headline verdict

Four findings, in descending severity:

1. **Cost/usage tracking is a three-layer facade.** `neuralcleave usage` (`cli.py:1120-1160`) calls `usage_summary()`, which reads the module-level `REGISTRY` singleton **in the CLI's own process**. The gateway runs in a separate process. The CLI process never performs a generation, so `per_model` is always empty and the command is structurally incapable of printing anything but `No LLM generations recorded yet in this process.` — while `mintlify-docs/cli.mdx:108-115` documents a populated example table that cannot occur. This is precisely the bug class PR #140 fixed for `approvals pending/approve/deny`, which established the `_try_gateway_json()` proxy pattern that this command does not use — even though the correct endpoint, `GET /api/v1/usage`, already exists. And that endpoint has **zero callers in the shipped product**: the Observability page reads `/metrics/snapshot` and renders tokens only, with no cost column at all (§5.1a).
2. **The pricing table cannot price the models the router actually routes to.** Executed against the live routing table, `estimate_cost_usd()` returns `None` for **15 of 29** provider/model pairs — including `gemini-2.5-flash`, the *first-choice* model for `general`, `summarization`, `intent_extraction`, `reflection`, and `validation`, and `deepseek-coder`, first choice for `code_generation` and `code_review`. Six of ten task types have an unpriceable primary. `pricing.py`'s table carries `gemini-1.5-pro` / `gemini-2.0-flash` entries — the exact two constants `router.py:53-58` documents having *replaced* a month before `pricing.py` was written (`git log`: router bumped 2026-07-20, `pricing.py` created 2026-08-17 and never modified since). Worse, `pricing.py:110-111` carefully returns `None` rather than `0.0` specifically "so callers can distinguish 'free by design' from 'unknown; don't report a misleading number'" — and its only caller, `_record_generation_metrics()` (`runtime.py:1238`), throws that distinction away by skipping the increment, after which `usage_summary()` (`usage.py:33`) initialises `cost_usd: 0.0` for every model it saw tokens for. The user gets exactly the misleading number the pricing module was written to prevent (§5.1b).
3. **Even a correct pricing table would count one LLM call in up to eight.** `_record_generation_metrics()` is fed `result.usage`, which `pipeline.py:240` / `:400` populate from *only* the primary generation. Every other billable call in the same turn is invisible: `_extract_intent()` (`pipeline.py:645`, runs on every message ≥5 chars, both streaming and non-streaming), `_run_tool_chain()`'s per-step regeneration (`pipeline.py:594`, up to `_max_tool_steps` calls), `_maybe_run_tool()`'s `gen2` (`pipeline.py:536`), and `ReflectionEngine`'s `_score` + `_correct` + post-correction `_score` (`reflection/engine.py:163,189,133`). Reflection is constructed unconditionally with `enabled=True` at `runtime.py:171`, so a plain chat message already costs three LLM calls of which one is counted (§5.1c).
4. **The embedded terminal's Stop button has never worked.** `terminal.py:341` declares `current_proc: asyncio.subprocess.Process | None = None` inside `terminal_ws()` and **never assigns to it** — `_run_command()` creates its subprocess in its own local `proc`. The `interrupt` handler (`:355-357`) and the disconnect cleanup (`:385-387`) are both guarded by `if current_proc and …`, so both are permanent no-ops. The frontend genuinely sends the frame (`frontend/src/app/(dashboard)/terminal/page.tsx:182`, wired to a `SquareX` "Stop" control), so the user gets a button that does nothing and a runaway command that only the 120-second `_TIMEOUT` will stop (§5.2).

Round 7's seven deliverables all re-verified clean (§4). Two smaller items round out the sweep: the Tauri shell hardcodes port 7432 in five places against a documented-configurable `[gateway] port` (§5.3), and `verify_backup()` validates the tar wrapper and its own self-generated checksum but never looks inside the archive (§5.4).

---

## 2. NeuralCleave: current state snapshot

- **Version**: 2.1.5 (`pyproject.toml:7`) — unchanged, per [[feedback_versioning]]
- **Channel adapters**: 31 — unchanged from Rounds 6-7
- **LLM providers**: 25 entries in `_PROVIDER_TO_MODEL` (`models/router.py:145-171`)
- **Tests**: 6,887 test functions across 338 files under `tests/` (was 6,866/337 at Round 7 — growth from Round 7's own fixes)
- **WebSocket endpoints**: 4 (`/ws`, `/ws/voice`, `/ws/terminal`, `/ws/canvas`) — all four now origin-checked
- **Branch**: `fix/canvas-ws-origin-check`, 17 commits ahead of `main`. Round 7's fixes are on this branch only; `main` is a round behind.
- Round 7's fixes: **seven PASS, zero partial** (§4). Best re-verification result in the series.

---

## 3. OpenClaw: what's changed since Round 7

Rounds 6 and 7 both cited snapshot commit `4f3d6af7352a` (2026-08-29 10:25:53 -07:00). To keep "nothing changed" falsifiable, the clone was **re-fetched from `origin` during this analysis** (`git fetch origin main`, succeeded). Result:

- `git rev-parse HEAD`, `origin/main`, and `FETCH_HEAD` are **all `4f3d6af7352a`**. `git rev-list --count HEAD..origin/main` → **0**. `git diff --stat HEAD FETCH_HEAD` → empty.
- Consequently `CHANGELOG.md`'s `### Changes` and `### Fixes` diffs are empty, and `git diff --diff-filter=A -- docs/` adds nothing — the check Round 6 used to find `memory-provenance.md` finds nothing this time.

**Net verdict for §3**: three consecutive rounds with literally zero upstream commits. This is no longer a "the changelog lags" caveat — the upstream project has not moved in over 24 hours of wall clock across three analyses, and the two long-standing deferred items (the capability-manifest widget/dashboard security model, and Workboard) are unchanged by definition. The partially-closed **memory provenance** item carried forward from Round 7 §3 is likewise unchanged: cross-channel identity linking, hook-source attribution, and an ingestion admission policy all remain unbuilt. At this point the competitive half of this exercise has stopped producing material, and the honest framing for future rounds is that this is now an internal-quality audit that also checks upstream, not a comparison that also finds internal bugs.

---

## 4. Re-verification of Round 7's shipped fixes

### 4.1 P0 — `/ws/canvas` origin check + `127.0.0.1` regex — **PASS**

Both halves hold, and they compose correctly under a real browser scenario.

- `canvas/routes.py:120-123` runs `if not is_allowed_origin(ws.headers.get("origin")): await ws.close(code=1008); return` **before** `await ws.accept()`, matching the three handlers verified in Round 7 (`websocket.py:148` for `/ws`, `websocket.py:481` for `/ws/voice`, `terminal.py:333` for `/ws/terminal`). All four sockets are now covered.
- `origin_check.py:47`'s `ORIGIN_REGEX` is now `https?://(tauri\.)?(localhost|127\.0\.0\.1)(:\d+)?`, matched with `fullmatch()` so `http://localhost.evil.com` still fails.

Traced against the four real browser origins that can reach `/ws/canvas`:

| Page | Origin sent | Verdict | Why |
|---|---|---|---|
| Gateway's own `/canvas` HTML page (`canvas/routes.py:415`), opened at `http://127.0.0.1:7432/canvas` | `http://127.0.0.1:7432` | **allowed** | `ORIGIN_REGEX` (this is Round 7's gap B, now closed) |
| Same page via `http://localhost:7432/canvas` | `http://localhost:7432` | allowed | `ORIGIN_REGEX` |
| Next.js dashboard canvas page (`frontend/.../canvas/page.tsx:512`) at `localhost:3000` | `http://localhost:3000` | allowed | explicit `_allowed` entry from `cfg.ui.web_port` |
| Tauri desktop shell | `http://tauri.localhost` | allowed | explicit `_allowed` entry |
| Any third-party page | its own origin | **rejected, 1008** | neither |

`set_allowed_origins(cfg)` is still called from `create_app()` before any route can be reached, so `_allowed` is populated for every request the app can serve. The LAN-IP case (`http://192.168.x.x:7432`) remains deliberately rejected, as Round 7 argued.

### 4.2 P1 — `client_id` → stable `sender_id` — **PASS on the surface it was written for; two other WS surfaces do not send one**

The round trip is real and complete on the primary path:
- `_resolve_sender_id()` (`websocket.py:25-43`) reads `websocket.query_params.get("client_id")`, validates it against `_CLIENT_ID_RE = [A-Za-z0-9_-]{1,128}` with `fullmatch`, and falls back to `uuid4()`.
- `Session` (`websocket.py:46-61`) carries `sender_id` as a field distinct from the per-connection `session_id`, with a docstring explaining the split.
- Both endpoints construct it correctly: `websocket.py:152` (`/ws`) and `:491` (`/ws/voice`), each `Session(websocket=websocket, sender_id=_resolve_sender_id(websocket))`.
- All three consumers now pass `sender_id=session.sender_id`: `_handle_chat_message` (`:247`), `_handle_audio_frame` (`:369`), `_handle_audio_frame_stream` (`:444`). No `session.session_id` remains in any `process_inbound_text_stream()` call — the remaining uses are logging and `WebSocketManager` bookkeeping, which is correct.
- Frontend: `getOrCreateClientId()` (`websocket.ts:27-40`) reads/writes `NeuralCleave_client_id` in `localStorage`, generating via `crypto.randomUUID()`, with a `try/catch` fallback for private browsing. `getConnectUrl()` (`:76-91`) puts it in a `URLSearchParams` on **every** connect path, including the settings-override branch. Both singletons go through this class — `gatewayWS = new ReconnectingWSClient("/ws")` (`websocket.ts:192`) and `voiceStreamWS = new ReconnectingWSClient("/ws/voice")` (`voice-ws.ts:16`) — so the desktop app and web UI both keep a stable memory identity across reconnects. Fix confirmed effective.

**Surveyed every other raw `new WebSocket(...)` in the repo** (the specific check this round was asked to make), and two of the four construct sockets outside `ReconnectingWSClient`:

| Site | Endpoint | Needs `client_id`? |
|---|---|---|
| `frontend/.../terminal/page.tsx:56` | `/ws/terminal` | **No** — the terminal handler never touches `process_inbound_text_stream()` or any sender-scoped path; it shells out. Correctly untouched. |
| `frontend/.../canvas/page.tsx:512` | `/ws/canvas` | **No** — read-only subscription; client→server messages are explicitly ignored (`canvas/routes.py:133`). Correctly untouched. |
| `canvas/routes.py:256` (gateway's own canvas page JS) | `/ws/canvas` | **No** — same. |
| `pwa/routes.py:232` (PWA app shell) | **`/ws`** | **Yes, and it does not.** |

The PWA shell is the one real gap. It connects to the same `/ws` endpoint whose chat protocol Round 7 just fixed, so it now genuinely reaches `process_inbound_text_stream()` — but it sends no `client_id`, so `_resolve_sender_id()` falls back to a fresh `uuid4()` on every connect and the PWA has no long-term-memory continuity across a page reload. `_resolve_sender_id()`'s own docstring names "the PWA shell" as an expected fallback case, so this is acknowledged rather than accidental; but the practical effect is that the surface Round 7 spent P2 making *able* to chat is the one surface where Round 7's P1 memory fix does not apply. Small, self-contained follow-on: generate and persist an id in the shell's `localStorage` and append it to `wsUrl()`.

Round 7's noted-and-deferred **channel split** (`"websocket"` for typed turns vs `"voice_ws"` for spoken ones, `websocket.py:246` vs `:443`) is confirmed still present. Typed and spoken turns from the same UI, same connection, same `sender_id` still land in two different `long_term` scopes.

### 4.3 P2 — PWA chat protocol + honest `/push/notify` — **PASS**
`pwa/routes.py:232`'s shell now sends `text` and reads `delta`, matching `websocket.py:228` (`msg.get("text") or msg.get("payload")`) and `:269` (`"delta": chunk.text`) exactly. `/push/notify` returns `sent: 0, delivered: false, matched_subscribers: N`. The three items Round 7 explicitly scoped out — no push-subscription client, the permanently-503 VAPID endpoint, and the LAN-reachability triple block (`gateway.bind` default, the origin allow-list, secure-context) — are all still open, as documented. No regression; the deferral is still accurately described in Round 7's own resolution note.

### 4.4 P3 — `ConfigWatcher` binds to the loaded file — **PASS**
`NeuralCleaveConfig.config_path` is set by `load_config()`; `config_watcher.py:110`'s comment records the failure mode it closed. `watchfiles` and `cryptography` are now explicit `pyproject.toml` dependencies rather than transitive-via-`uvicorn[standard]`. `neuralcleave config show`'s `default=str` fix is in place. No dead-code gap: `ConfigWatcher` is constructed and started from `main.py` with the live `cfg`.

### 4.5 P4 — terminal audit log — **PASS on reachability, with two design gaps worth recording**
Reachability is real and traced end to end: `terminal.py:50` imports `record_command`, and `_run_command()` calls it as its **first statement** (`:394`), before the subprocess is even created — so a spawn failure still leaves a record. `_run_command()` is the sole shell path from the live `/ws/terminal` handler (`:378`), reached for every `{"type":"run"}` frame that isn't intercepted by `_maybe_dispatch_nc()` — and that exemption is correct, since the `neuralcleave`/`nc` dispatch never touches a shell. Not dead code.

Two gaps that don't invalidate the fix but should be written down:
- **The log has no reader.** `~/.neuralcleave/terminal_history.log` is written by exactly one function and read by nothing — no CLI command, no REST endpoint, no rotation, no size cap. `PrivacyAuditLog`, by contrast, has report endpoints. An audit trail nobody can query without `cat` is thin, and an unbounded append-only file is a slow leak.
- **It records secrets in cleartext, and the backup sweeps them up.** The entry is `{"timestamp", "cmd"}` with the command verbatim — so `export OPENAI_API_KEY=sk-…` or `curl -H "Authorization: Bearer …"` lands unredacted in a plain file with default permissions. That file lives inside `~/.neuralcleave`, which is exactly what `create_backup()` tars (§5.4). Round 7 was right that this belongs in its own module rather than shoehorned onto `PrivacyAuditLog`; it just inherited none of that module's handling discipline.

### 4.6 Drive-by — Hub fetch hardening + checksum — **PASS**
`_fetch_code()` (`installer.py:206-219`) now accepts only `data:` and `https://`, matching the class docstring and its own error message. `install()` takes `expected_checksum` and compares it (case-insensitively) at `:135` **before** `_resolve_name`, the collision check, the scanner, and `_write_skill` — so a mismatch aborts before anything is scanned, written, or registered. Both user-facing entry points are genuinely threaded, verified by reading each: `neuralcleave hub install --checksum` passes it into the gateway-proxy body (`cli.py:2382`) *and* the local-fallback `installer.install()` call (`cli.py:2404`), and `POST /api/v1/hub/packages` reads `body.get("expected_checksum") or None` (`routes.py:1615`). `scan_url()` is gone. No dead-code gap. The host allow-list and `follow_redirects=True` items Round 7 scoped out remain open, as documented.

---

## 5. Newly identified gaps (fresh sweep)

Subsystems chosen because no prior round has audited them: cost/usage tracking (`models/pricing.py`, `observability/usage.py`), the Tauri desktop shell's Rust layer (`frontend/src-tauri/`), and the backup/restore round trip (`neuralcleave/backup.py`). The embedded terminal's interrupt path (§5.2) surfaced while re-verifying §4.5 and is included because it is a live user-facing no-op.

### 5.1 Cost/usage tracking reaches a real user through zero working surfaces (headline finding)

Three independent defects, each confirmed by reading both sides of the interface. Any one of them alone would make the feature unreliable; together they make it unreachable.

**(a) `neuralcleave usage` reads the wrong process's counters and can never print a table.**
`cli.py:1120-1133`:

```python
from neuralcleave.observability.usage import usage_summary
per_model = usage_summary()
if not per_model:
    console.print("[dim]No LLM generations recorded yet in this process.[/dim]")
    return
```

`usage_summary()` (`observability/usage.py:26,40`) reads `REGISTRY.get("tokens_total")` and `REGISTRY.get("cost_usd_total")` off the module-level singleton in `observability/metrics.py`. The gateway runs as a separate process (`neuralcleave start` → uvicorn). The CLI process has its own fresh `REGISTRY` and performs no generations, so `per_model` is empty on every invocation, forever. There is no `_try_gateway_json()` call in this command — the helper PR #140 introduced for exactly this problem, used by `approvals pending` (`cli.mdx:155`) and `hub install` (`cli.py:2377`), and there is already a correct endpoint to proxy to (`GET /api/v1/usage`, `routes.py:644`). The command's own docstring ("for this process") and the doc note ("a live, in-process view") are technically true and completely misleading, because the process they describe is not the one the user is asking about. `mintlify-docs/cli.mdx:108-115` then shows a populated example table with `claude-opus-4-8` and `$0.1642` — output the shipped command cannot produce.

**(b) `GET /api/v1/usage` works, and has no caller.** `routes.py:644-655` reads the gateway's *own* `REGISTRY`, so it returns real data. Nothing consumes it. The Observability page (`frontend/src/app/(dashboard)/observability/page.tsx:83`) queries `/metrics/snapshot`, derives `tokenRows` from it (`:139`), and renders a four-column table — Model / Input / Output / Total (`:273-276`). **There is no cost column anywhere in the UI**, and a repo-wide grep for `cost_usd` / `total_cost` across `frontend/src` (excluding tests) returns nothing. So the only surface that can show a cost number is the CLI command from (a), which never shows one. The single path where the value survives is a Prometheus scrape of `/metrics` picking up `cost_usd_total` directly — which is real, but is not what "cost tracking" was sold as.

**(c) The pricing table cannot price what the router routes to.** Executed `estimate_cost_usd(provider=…, model=…, input_tokens=1000, output_tokens=1000)` against every constant in `models/router.py`. **15 of 29 pairs return `None`:**

| Result | Pairs |
|---|---|
| Priced | `claude-opus-4-8`, `claude-sonnet-4-6`, `gpt-4o`, `gpt-4o-mini`, `ollama/llama3.2:1b` (0.0), `mistral-large-latest`, `mistral-small-latest`, `command-r-plus`, `command-r`, `moonshot-v1-8k`, `glm-4`, `glm-4-flash`, `qwen-max`, `doubao-pro-32k` |
| **Unpriced** | **`gemini-2.5-pro`**, **`gemini-2.5-flash`**, **`deepseek-coder`**, `grok-3`, `grok-3-mini`, `qwen-turbo`, `ernie-bot-4`, `ernie-speed`, `doubao-lite-32k`, `openrouter/*`, `azure/*`, `bedrock/*`, `groq/*`, `together/*`, `fireworks/*` |

Only the last six of those are the deliberate omissions `pricing.py:28-29,81-82` documents (openrouter/azure/bedrock contract pricing). The rest are plain misses:

- `PRICING_PER_1M_TOKENS["google"]` holds `gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.0-flash`. `router.py:53-58` documents having *replaced* `gemini-1.5-pro` / `gemini-2.0-flash` because both lost their free-tier quota. `git log` confirms the router bump landed **2026-07-20** and `pricing.py` was created **2026-08-17** and has not been modified since — so this isn't drift, the table was born a month stale.
- `["deepseek"]` holds `deepseek-reasoner` / `deepseek-chat`; the router's only DeepSeek constant is `deepseek-coder`.
- `["xai"]` holds `grok-2` / `grok-beta`; the router uses `grok-3` / `grok-3-mini`.
- `["ernie"]` holds `ernie-4.0`; the router uses `ernie-bot-4` / `ernie-speed`.
- `groq`, `together`, and `fireworks` have no provider key at all and are not mentioned in the "deliberately omitted" comment.

The cost of those misses lands squarely on the default path. Cross-referencing `_ROUTING` (`router.py:126-140`), the **first-choice** model is unpriceable for six of ten task types — `code_generation`, `code_review`, `summarization`, `intent_extraction`, `reflection`, `validation` — and for `general`, the fallback every ordinary chat message uses. A fresh install with a Gemini key therefore records tokens and reports `$0.0000`.

And the reporting layer erases the one safeguard the pricing layer built. `pricing.py:110-111` is explicit:

> Returns `None` — not `0.0` — when *provider*/*model* has no pricing entry, so callers can distinguish "free by design" from "unknown; don't report a misleading number."

Its only caller does not make that distinction: `_record_generation_metrics()` (`runtime.py:1238-1239`) simply skips the increment when `cost is None`. `usage_summary()` (`usage.py:32-34`) then seeds `{"input_tokens": 0.0, "output_tokens": 0.0, "cost_usd": 0.0}` for every model that has *token* counters, and `cli.py:1151` formats it as `f"${stats['cost_usd']:.4f}"`. A model that could not be priced is rendered identically to a model that is genuinely free.

**(d) Only one LLM call per turn is counted.** `_record_generation_metrics()` is fed `result.usage`, and `PipelineResult.usage` comes from a single source in each path — `gen.usage` (`pipeline.py:240`) and `final_usage` (`:400`), both the primary generation. Every other `self._router.generate()` in the same turn is billable and uncounted:

| Call | Location | When it runs |
|---|---|---|
| `_extract_intent()` | `pipeline.py:645` | **Every** message ≥5 chars, both `run()` (`:164`) and `run_stream()` |
| `_maybe_run_tool()` → `gen2` | `pipeline.py:536` | Single-shot tool path |
| `_run_tool_chain()` → per-step regen | `pipeline.py:594` | Once per tool step, up to `_max_tool_steps` |
| `ReflectionEngine._score()` | `reflection/engine.py:163` | Every message (reflection is on by default) |
| `ReflectionEngine._correct()` + re-`_score()` | `reflection/engine.py:189`, `:133` | Per correction attempt when score < 70 |

`ReflectionEngine` is constructed unconditionally at `runtime.py:171` (`ReflectionEngine(router=router)`) with its defaults `enabled=True, quality_threshold=70.0, max_corrections=1`, so the reflection calls are not hypothetical. A plain chat message is already three LLM calls reported as one; a message that triggers a three-step tool chain and one reflection correction is eight reported as one. The reflection engine's own docstring — "uses a cheap fast model … to avoid burning expensive tokens on meta-evaluation" — is a cost claim about calls the cost tracker cannot see.

**Portability judgment**: entirely NeuralCleave's own, and the cleanest example yet of this project's recurring failure mode — `pricing.py`, `usage.py`, `cost_usd_total`, `neuralcleave usage`, and `GET /api/v1/usage` are all built, unit-tested, documented with a worked example, and collectively deliver nothing to a user. Notably, *each layer is individually defensible*: the pricing module is careful, the metric is registered, the endpoint is correct, the CLI is readable. The failure is entirely in the seams, which is exactly where per-module unit tests cannot look.

### 5.2 The embedded terminal's Stop button is a permanent no-op

`gateway/terminal.py:341`, inside `terminal_ws()`:

```python
current_proc: asyncio.subprocess.Process | None = None
```

`grep -n current_proc` over the file returns exactly five lines: the declaration, and four *reads* (`:355`, `:357`, `:385`, `:387`). **There is no assignment anywhere.** The subprocess is created inside `_run_command()` (`:397`) and bound to that function's local `proc`, which is never returned or stored.

Consequences, both live:
- The `{"type": "interrupt"}` handler (`:354-360`) evaluates `if current_proc and current_proc.returncode is None:` against a permanent `None` and falls through silently. The frontend sends this frame from a real, always-visible control — `frontend/src/app/(dashboard)/terminal/page.tsx:182`, `wsRef.current?.send(JSON.stringify({ type: "interrupt" }))`, behind the `SquareX` "Stop" button. The user presses Stop and nothing happens, with no error frame, because the handler `continue`s as if it had worked.
- The disconnect cleanup (`:384-389`) is the same no-op, so closing the terminal tab mid-command orphans the subprocess until `_TIMEOUT` (120 s) or process exit.

The only interruption that works is `_run_command()`'s own `asyncio.wait_for(..., timeout=_TIMEOUT)` → `proc.terminate()` (`:426-428`). A long-running or runaway command is therefore uninterruptible for up to two minutes, on the one surface Round 7 just decided *not* to put behind an approval gate partly on the reasoning that it is the operator's own direct interactive session. An interactive session where Ctrl-C does nothing is a weaker version of that argument. Fix is small: have `_run_command()` accept a setter (or return the handle) so `terminal_ws()` can track the live process.

### 5.3 The Tauri shell hardcodes port 7432 in five places against a documented-configurable port

The desktop layer is otherwise in better shape than expected — every Rust `#[tauri::command]` has a real frontend caller (`set_unread_badge` ← `lib/trayBadge.ts:10`, `restart_backend` ← `settings/page.tsx:408`, `save_and_open_html` ← `chat/page.tsx:300`), and both cfg-gated plugins are genuinely used (`tauri-plugin-autostart` ← `settings/page.tsx:7`, `tauri-plugin-notification` ← `lib/notifications.ts:12`). No orphaned commands, no registered-but-unused plugin. The tray, global hotkey (`Ctrl+Shift+Space`), single-instance guard, and sidecar lifecycle all trace clean.

The gap is that the Rust side treats 7432 as a constant while `config.py:93`'s `GatewayConfig.port` is a documented, user-editable key (`mintlify-docs/configuration.mdx:120` shows `port = 7432` under `[gateway]`). Five hardcodes in `frontend/src-tauri/src/lib.rs`:

| Line | Code | Effect if `[gateway] port` is changed |
|---|---|---|
| `:119` | `gateway_is_healthy()` → `SocketAddr::from(([127,0,0,1], 7432))` | Health probe always fails |
| `:89-101` | `restart_backend()`'s 30×500 ms health loop | Returns `"Gateway started but did not respond within 15 seconds"` on a **successful** restart |
| `:152,155` | `kill_process_on_port_7432()` PowerShell (`Get-NetTCPConnection -LocalPort 7432`, `netstat \| Select-String ':7432 '`) | Never kills the real sidecar |
| `:170` | non-Windows `lsof -ti tcp:7432` | Same |
| `:300-303` | startup "is the port occupied" check | Never detects the stale sidecar it exists to clear |

Two of these are worse than a no-op. `restart_backend()` reports failure on success, and — because `kill_process_on_port_7432()` is called unconditionally at startup and on every restart, killing **by PID, whatever owns the port** with `taskkill /F /T` on Windows and `kill -9` elsewhere — a user who moved NeuralCleave off 7432 gets their desktop app force-killing an unrelated process tree on every launch. The name `kill_process_on_port_7432` is honest about being hardcoded; the behaviour is not scoped to NeuralCleave's own process in any way.

The same hardcode runs through the JS side, with one instance stricter than the others: `websocket.ts:23` and `terminal/page.tsx:8` both default to `ws://127.0.0.1:7432` but honour a settings override, whereas `canvas/page.tsx:512` builds `` `${protocol}//127.0.0.1:7432/ws/canvas` `` unconditionally, ignoring the "Backend API URL" setting the other two respect. So on a non-default port the canvas page silently degrades to its 5-second REST poll forever.

Severity is bounded — the default works, and this only bites users who change the port — but "changing a documented config key silently breaks the desktop app and kills a bystander process" is a bad shape for a setting that appears in the docs as an ordinary knob. The narrow fix is to pass the resolved port to the frontend and to the Rust side (Tauri config, an env var on the sidecar spawn, or a `/health`-discovered value) rather than embedding the literal.

### 5.4 `verify_backup()` verifies the wrapper, not the contents

`backup.py`'s round trip is structurally sound where it matters most — `restore_backup()` (`:191-193`) filters members to the `neuralcleave-state/` prefix and extracts with `filter="data"`, so path traversal and absolute paths are genuinely rejected, and the non-empty-target guard (`:185`) is real. The CLI wraps all four operations with a confirmation prompt. This is not a facade.

What it does not do is verify anything about what is *in* the archive. `verify_backup()` (`:101-127`) does two things: open the tar and call `getmembers()`, and — if the `.sha256` sidecar exists — compare the archive's digest against it. But that digest was computed by `create_backup()` from the archive it had just written (`:94-96`), so it can only detect corruption of the archive file *after* it was created. It detects nothing about whether the backup captured anything useful. Concretely:

- An empty or near-empty `~/.neuralcleave` produces a valid archive that `verify_backup()` reports as `Valid backup:` and `neuralcleave backup list` shows with a size. A user who backed up before ever running the gateway gets a green checkmark on a backup of nothing.
- The archive contains SQLite databases (`memory.db`, `privacy_audit.db`, `plugin_state.db`, `approval_policy.db`) copied file-by-file by `tar.add()` while the gateway may be running and writing. No `journal_mode` is set anywhere in the codebase, so these are rollback-journal databases: the `.db` and any `.db-journal` are captured at different instants, and a restore can land a torn database. `verify_backup()` would still call it valid, because a torn SQLite file is a perfectly readable tar member.
- If `cfg.memory.sqlite_path` points outside `~/.neuralcleave` (it is a config key, `config.py:62`), or the gateway was started with `-c /elsewhere/config.toml`, the backup silently misses the data or the config — and still verifies.

A cheap improvement covers all three: have `verify_backup()` assert the archive contains the manifest plus a non-empty `neuralcleave-state/` tree, and run `PRAGMA integrity_check` (or at minimum open) each `.db` member it finds. Separately worth noting that the archive is an unencrypted tar.gz containing `config.toml` — with every provider API key in plaintext — plus, since Round 7, `terminal_history.log` with whatever secrets were typed into the terminal (§4.5). That's inherent to backing up a state directory, but it deserves a line in the docs it does not currently have.

---

## 6. Recommended build order

### P0 — Make `neuralcleave usage` talk to the running gateway (§5.1a)
The smallest change with the largest honesty payoff. Route the command through `_try_gateway_json(cfg, "GET", "/api/v1/usage")` — the exact pattern `approvals pending` and `hub install` already use — and fall back to the local registry with a printed note, matching those commands' established behaviour. Without this, the command's only possible output is "nothing recorded", which is not a bug a user will report as a bug; they will conclude they have no usage. While there, correct `mintlify-docs/cli.mdx:108-115` so the example matches what the command can actually return. Highest priority because it is small, mechanical, has a precedent already in the codebase, and today ships a documented feature that cannot work.

**Resolved (2026-08-30)**: `usage()` now tries `GET /api/v1/usage` first via `_try_gateway_json`, falling back to the local (necessarily-empty-unless-run-inside-the-gateway-process) registry only when unreachable, with the same "No gateway reachable at …" note `orchestrate status` prints. `mintlify-docs/cli.mdx`'s example corrected to match. New `TestUsageCommand` class covers both branches plus the empty-gateway-response case — this command had zero test coverage before.

### P1 — Refresh the pricing table and stop rendering "unknown" as `$0.0000` (§5.1b)
Two parts, both narrow. (1) Add entries for the models the router actually routes to — at minimum `gemini-2.5-flash` / `gemini-2.5-pro`, `deepseek-coder`, `grok-3` / `grok-3-mini`, `ernie-bot-4` / `ernie-speed`, `qwen-turbo`, `doubao-lite`, and provider keys for `groq` / `together` / `fireworks` — and extend the "deliberately omitted" comment to name every provider that is genuinely unpriceable, so the next reader can tell a decision from an oversight. (2) Preserve the `None` that `pricing.py` is careful to return: track unpriced generations separately (a `cost_unknown_tokens_total` counter, or a per-model `priced: bool`) and render them as `—` / `unknown` rather than `$0.0000`. Add one test that iterates `_ROUTING`'s models and asserts each either prices or appears on an explicit known-unpriceable list — that single test is what would have caught the month-stale table on the day it was written, and is what stops it recurring.

**Resolved (2026-08-30), both parts**: (1) added every missing entry named above to `pricing.py`, kept the retired ones (a manual forced-provider override could still name one), and added a new `TestEveryRoutedModelIsPricedOrExplicitlyUnpriceable` test that exercises every real `_ROUTING` model/provider pair against an explicit `_DELIBERATELY_UNPRICEABLE` allowlist (openrouter/azure/bedrock) — this is the exact test the recommendation asked for. (2) new `cost_unpriced_generations_total` counter, incremented by `_record_generation_metrics()` whenever `estimate_cost_usd()` returns `None`; `usage_summary()` now reports `cost_usd: None` + `unpriced: True` for any such model instead of silently defaulting to `0.0`; both the CLI table (`"— (unpriced)"`, excluded from the total, with an explanatory footnote) and `GET /api/v1/usage`'s `total_cost_usd` sum honor the distinction.

### P2 — Count every LLM call, or say plainly that you don't (§5.1d)
Accumulate usage across the whole turn rather than reporting only the primary generation: have `_extract_intent`, `_maybe_run_tool`/`_run_tool_chain`, and `ReflectionEngine` return or accumulate their `GenerationResult.usage` into a per-turn total that `PipelineResult.usage` carries. If that's a larger refactor than is wanted right now, the honest interim is to label the reported figure as "primary generation only" in the CLI, the endpoint, and the docs — because as it stands a user comparing `neuralcleave usage` against a provider bill will find the bill 3-8× larger and have no way to explain the gap. Ranked below P1 because a correct table on one call is more useful than a stale table on all calls, and the two can ship independently.

### P3 — Track the live subprocess so the terminal's Stop button works (§5.2)
`_run_command()` should hand its `proc` back to `terminal_ws()` (a mutable holder, a callback, or restructure so the handler owns the spawn) and the two `current_proc` guards should then do what they were written to do. Small and self-contained. Prioritised above the remaining items because it is a visible control in the shipped UI that silently does nothing, on the surface Round 7 deliberately left ungated. Add a test that runs a sleeping command, sends `interrupt`, and asserts the process is gone — the existing terminal tests cover audit and origin but never assert on interruption.

**Resolved (2026-08-30) — turned out to need one layer more than described**: `_run_command()` now runs as a background task (`asyncio.create_task`) while `terminal_ws()`'s loop keeps listening concurrently via `asyncio.wait()`, sharing a new `_RunState` (not a bare mutable holder — see below for why) so an interrupt can reach the real subprocess. Two deeper issues surfaced while writing the test this section asked for: (a) an interrupt arriving *before* the subprocess even exists (a real, hit-on-first-try race, since spawning takes measurably longer than the message round-trip) was silently lost with a plain holder — `_RunState.interrupted` fixes this by letting `_run_command()` apply a pending interrupt retroactively the moment the process starts; (b) `proc.terminate()` only ever killed the shell wrapper `create_subprocess_shell()` spawns, not whatever *that* shell ran — interrupting a running `python script.py` left the script itself orphaned. New `_terminate_process_tree()` (`taskkill /T` on Windows, a process-group signal on POSIX via `start_new_session=True`) actually stops the real work. The test recommended here (run a sleeping command, interrupt, assert it's gone) is exactly what caught both of these — it failed twice against two different "fixed" versions before passing for real.

### P4 — Stop hardcoding 7432 in the desktop shell (§5.3)
Thread the resolved `[gateway] port` to the Rust layer (env var on the sidecar spawn, or a Tauri config value written at build/launch) and use it in `gateway_is_healthy()`, the startup port check, and `kill_process_on_port_7432()` — which should additionally be scoped to a process it knows is ours rather than force-killing whatever owns the port. Fix `canvas/page.tsx:512` to honour the same settings override the WebSocket client and terminal page already respect. Ranked here because the default path works and only users who change a documented setting are affected — but the failure mode (force-killing an unrelated process tree, and reporting a successful restart as a 15-second timeout) is disproportionate to the cause.

### Deliberately not prioritized this round
- **A `client_id` for the PWA shell** (§4.2): one `localStorage` read and one query param in `pwa/routes.py`'s `wsUrl()`. Real, tiny, and correct to fix — but the PWA still cannot be reached from the phone it was built for (Round 7 §5.1's three independent blockers), so memory continuity on a surface that only works on the gateway's own machine is not where the next hour goes. Good drive-by for whichever PR next touches `neuralcleave/pwa/`.
- **The `"websocket"` / `"voice_ws"` channel split** (§4.2, carried from Round 7): typed and spoken turns from the same connection still land in different memory scopes. Unchanged from Round 7's reasoning — unifying them is a scoping decision, not a mechanical follow-on, and it should be made deliberately rather than as a side effect.
- **Backup content verification** (§5.4): assert the archive holds a non-empty state tree and integrity-check the SQLite members; document that the archive contains plaintext API keys. Worth doing, but the restore path's actual safety properties (traversal rejection, non-empty-target guard) are sound, so this is hardening rather than a hole.
- **A reader and a size cap for `terminal_history.log`** (§4.5): the log is write-only, unrotated, unbounded, and captures whatever secrets were typed. Pair it with the backup docs note above whenever either is touched.
- **Memory provenance beyond `(channel, sender_id)`** (§3): unchanged — cross-channel identity linking, hook-source attribution, and an ingestion admission policy all still unbuilt, still no demand signal.
- **Capability-scoped widget/dashboard security model** and **Workboard-equivalent task board**: unchanged. Upstream produced zero commits for the third consecutive round, so neither gained urgency by definition.
- **A2A channel**: unchanged from Rounds 6-7 — real and portable, no demand signal, channel breadth settled as a non-gap in Round 3.

---

## 7. One-paragraph summary for future sessions

As of 2026-08-30, OpenClaw's clone was re-fetched and `origin/main`, `HEAD`, and `FETCH_HEAD` are all still `4f3d6af7352a` — the third consecutive round with literally zero upstream commits, so every finding here is NeuralCleave's own and the competitive half of this exercise has stopped producing material. Re-verifying Round 7's seven fixes (on branch `fix/canvas-ws-origin-check`, 17 commits ahead of `main`) produced the best result in the series: **all seven PASS**. The `/ws/canvas` origin check is in place pre-`accept()` and composes correctly with the new `(localhost|127\.0\.0\.1)` regex across all four real browser origins; the `client_id` → `sender_id` round trip is complete on both `/ws` and `/ws/voice` and both frontend singletons send it; the PWA chat protocol and honest `/push/notify` are correct; `ConfigWatcher` trusts `config_path`; `record_command()` is the first statement of `_run_command()`; and `expected_checksum` is verified before anything is scanned or written, threaded through both the CLI and REST install paths. Two follow-ons surfaced during re-verification: the PWA shell is the one remaining `/ws` client that sends no `client_id` (so it alone still mints a fresh identity per reload), and the terminal audit log has no reader, no rotation, and records typed secrets verbatim into a file the backup archives. The fresh sweep of three never-audited subsystems found this project's signature bug class at its purest: **cost/usage tracking reaches a real user through zero working surfaces**. `neuralcleave usage` reads the CLI process's own `REGISTRY` singleton instead of the running gateway's, so it can only ever print "No LLM generations recorded yet in this process" — the same bug PR #140 fixed for `approvals`, with the `_try_gateway_json()` proxy already sitting in the same file unused, and with `mintlify-docs/cli.mdx` documenting a populated example table that cannot occur; `GET /api/v1/usage` is correct but has no caller, since the Observability page reads `/metrics/snapshot` and renders no cost column at all; and executing `estimate_cost_usd()` against every router constant shows 15 of 29 pairs unpriced, including `gemini-2.5-flash` and `deepseek-coder` — the first-choice models for six of ten task types — because `pricing.py` was written on 2026-08-17 carrying `gemini-1.5-pro`/`gemini-2.0-flash` entries the router had replaced on 2026-07-20, and has never been edited since. `pricing.py` deliberately returns `None` rather than `0.0` "so callers can distinguish free-by-design from unknown," and its only caller discards that distinction, so the user sees exactly the misleading `$0.0000` the module was written to prevent; and even a correct table would count one call in up to eight, since intent extraction, tool-chain regeneration, and the always-on reflection scorer/corrector are all billable and all invisible. Also found: `gateway/terminal.py:341` declares `current_proc` and never assigns it, so the terminal's Stop button and its disconnect cleanup have both always been no-ops while the frontend genuinely sends the frame; and the Tauri shell hardcodes port 7432 in five places against a documented-configurable `[gateway] port`, such that changing it makes `restart_backend()` report failure on success and makes the app force-kill whatever unrelated process owns 7432 on every launch. Build order: P0 route `neuralcleave usage` through the gateway's REST API, P1 refresh the pricing table and stop rendering unknown as `$0.0000` (with a test iterating `_ROUTING`), P2 accumulate usage across the whole turn or label the figure "primary generation only", P3 track the live subprocess so the terminal's Stop button works, P4 stop hardcoding 7432 in the desktop shell.
