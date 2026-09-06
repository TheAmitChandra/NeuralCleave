# NeuralCleave source assessment - 2026-09-06

Analyzed local checkout `C:/Amit-Projects/AI-Projects/CortexFlow`, HEAD `fb506b98` (`docs: record resolution of round-8's P0, P1, and P3 findings`). This is a source-based architecture and development assessment, not a production penetration test or a live comparison with other products. No external provider availability, pricing, or competitor claims were verified. Existing untracked `.claude/settings.local.json` was left untouched.

## Architectural assessment

NeuralCleave's strongest foundation is the shared Python runtime behind multiple user surfaces. The normalized channel message, model router, cognitive pipeline, and live tool registry provide useful extension points. Recent source changes address actual wiring problems: plugin tools now share the runtime registry, the orchestrator receives the real router, session IDs survive recreation, and startup distinguishes readiness from liveness.

The most consequential remaining engineering challenge is integration consistency. Several capabilities have separate implementations across normal chat, streaming, orchestration, voice, settings, and packaging. Those paths do not automatically inherit each other's guarantees. Future work should trace the complete user workflow and test the transitions between components, rather than infer readiness from subsystem size or test counts.

Memory has a clear personal-use design: session-local immediate context plus cross-channel long-term recall. That is useful for one owner, but it is not a multi-tenant architecture. SQLite provides durable storage; Redis/Qdrant fallbacks keep requests usable with reduced durability/capability. This tradeoff should stay explicit in product behavior and deployment decisions.

The dashboard and Tauri shell share frontend code, but deploy differently. Browser/server builds and static desktop builds must remain independently valid. Similarly, having both `backend/` and `neuralcleave/` in one checkout increases the risk of fixing the wrong runtime. The new skill records the package entry points and current CI as the primary navigation anchors.

## Findings supported by source

| Priority/context | Finding and consequence | Evidence | Follow-up acceptance criterion |
| --- | --- | --- | --- |
| High: root Docker startup | Root Dockerfile invokes `cortex`, but the package defines `neuralcleave` and `neuralcleave-desktop`. A clean image built from these sources is expected to fail at entrypoint execution. Container startup was not run. | `Dockerfile:41`; `[project.scripts]` in `pyproject.toml` | Build and boot the root image; reach readiness using the installed console script. |
| High: root Compose/config | Root Compose mounts `/root/.NeuralCleave`, whereas config and memory default to lowercase `/root/.neuralcleave`. On Linux these differ. Compose supplies Redis/Qdrant environment variables, but memory parsing uses TOML/defaults rather than those environment names. | `docker-compose.yml:23-26`; `config.py:18`, `MemoryConfig`, `_parse_config` | Demonstrate data survives container recreation and configured services are reached rather than localhost fallbacks. Check the image name's uppercase spelling with Compose too. |
| High when remotely hosted: transport authentication | REST can require `X-API-Key`, but WebSocket handlers validate Origin and accept missing Origin without validating a gateway key. Terminal uses the same boundary. Default loopback binding limits exposure; remote deployment must not assume REST authentication protects these sockets. | `gateway/main.py:create_app`; `gateway/websocket.py:websocket_endpoint`; `gateway/terminal.py:terminal_ws`; `origin_check.py:is_allowed_origin` | Unauthorized non-browser clients fail chat/voice/terminal handshakes in a deliberately authenticated remote configuration. |
| Medium: orchestrator claims vs execution | Orchestrator tasks generate through `ModelRouter` without the cognitive pipeline's memory retrieval, tool chain, or reflection. Namespace APIs exist but are not read by `route()`. | `orchestrator/orchestrator.py:180-234`; `gateway/main.py` runtime wiring | Either expose this distinction clearly or wire and test node-specific full-pipeline execution. |
| Medium: reflection semantics | Non-streaming reflection may replace the reply; streaming reflection keeps original text and records a score. A universal claim of correction before every reply is inaccurate for streaming. | `agent/pipeline.py:run`, `run_stream`; README reflection description | Document the distinction and preserve an explicit streaming correction contract if changed. |
| Medium: extension containment | Generated skill proposals require review and import scanning, but loaded code executes in process through `exec_module`; installed plugin discovery imports entry points in process too. Historical descriptions of subprocess-sandboxed plugins overstate containment. | `skills/writer.py:_load_skill_module`; `plugins/registry.py:discover`; older skill guides | Describe actual containment; if isolation is requested, test execution boundaries and limits rather than only blocked imports. |
| Medium: frontend authentication integration | The inspected shared Axios client does not attach `X-API-Key`; gateway enforcement expects that header. Authenticated gateway use needs a complete client/server path. | `frontend/src/lib/api.ts`; `gateway/main.py:create_app` | Verify a configured-key gateway works from the UI and unauthenticated requests are rejected. |
| Maintenance: source/document drift | README advertises 13 providers while config/router contain more branches; contribution docs point to old coverage paths and test totals; old skills disagree on direct merge vs PR-only workflows. | README; CONTRIBUTING; `models/router.py`; `docs/SKILL.md`; `.github/skills/neuralcleave/SKILL.md` | Refresh claims from executable source and retain one maintained development knowledge base. |

These are observations for follow-up, not fixes applied by this task. Priorities reflect likely user impact in the specified context, not a formal vulnerability rating.

## Additional inspection targets

- `ReconnectingWSClient.getConnectUrl()` uses a saved full WebSocket URL for any client path. Since voice instantiates the same class with `/ws/voice`, a saved chat URL may override the dedicated voice path. This is a source-based concern requiring a targeted reproduction with custom Settings.
- Background memory writes and compaction are scheduled with `create_task`. Review shutdown draining and overlapping same-session turns when durability/concurrency work is requested; this review did not establish a lost-write reproduction.
- Pipeline instructions permit approximate chart values and say never to refuse chart requests, while workspace defaults say never fabricate facts. Review chart provenance and labeling if analytical output quality is a product priority.
- Router capabilities such as per-channel overrides should be checked at call sites before being described as active in every chat path.

## Verification baseline

The local venv uses Python 3.13, while CI specifies 3.12. The full root pytest run stopped during collection because `tomli_w` is missing from this venv; it is already declared in `pyproject.toml`. Thus the README's passing-test count was not independently confirmed.

| Check actually run | Result |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/ -q --tb=short` | Collection stopped: missing `tomli_w` in `test_settings_voice_config_preservation.py`; no full-suite passing claim. |
| Selected Python modules: session, pipeline and streaming, runtime and streaming, gateway auth, orchestrator, memory retrieval, plugin registry | 435 passed, 1 failed in 37.99 seconds. Failure: `test_require_shell_approval_end_to_end_through_real_config_and_registry` returns `Program not found: 'echo'` on Windows. This is an observed platform-dependent command assumption, not evidence the entire approval mechanism is broken. |
| `npm.cmd run type-check` in `frontend/` | Passed. |
| `npx.cmd --no-install vitest run` in `frontend/` | All 169 files / 287 tests passed in 115.68 seconds. Non-fatal warnings included React Query query-function warnings in gateway toast tests and Vite's CJS deprecation warning. |
| Skill creator `quick_validate.py` | Passed for `docs/agent-skills/neuralcleave-development`. |

The selected Python command used these explicit files under `tests/unit/`: `test_agent_session.py`, `test_agent_pipeline.py`, `test_agent_pipeline_streaming.py`, `test_agent_runtime.py`, `test_agent_runtime_streaming.py`, `test_gateway_auth.py`, `test_orchestrator.py`, `test_memory_retrieval.py`, and `test_plugins_registry.py`.

Container boot, packaged desktop launch, full backend suite, SDK/plugin example suites, lint, production frontend build, external channels/providers, and microphone/speaker hardware were not verified in this assessment. Dependencies and application code were not changed to force a green baseline.

No runtime application code was changed. The new skill separates stable architecture/contracts, task-specific development guidance, and this dated assessment so future tasks can load only relevant detail and revalidate stale findings.
