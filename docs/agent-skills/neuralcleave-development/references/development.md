# Development and verification

Paths and commands assume the repository root unless stated otherwise. Match the affected subsystem and installed environment; do not launch the user's real gateway merely to inspect imports.

## Task routing

| Task | Inspect together | Existing test starting points |
| --- | --- | --- |
| Chat/streaming | `agent/runtime.py`, `agent/pipeline.py`, `agent/session.py`, `gateway/websocket.py`, frontend chat page and WS client | `test_agent_pipeline*.py`, `test_agent_runtime*.py`, `test_agent_session.py`, frontend WebSocket/chat tests |
| Memory | `memory/retrieval.py`, `short_term.py`, `long_term.py`, `embedder.py`, compactor/archiver, runtime writes | `test_memory*.py`, `test_agent_session.py`, pipeline tests |
| Provider/config | `config.py`, `models/router.py`, health/pricing/thinking, settings routes/page | `test_model_router.py`, `test_config*.py`, `test_agent_runtime_provider_keys.py`, settings tests |
| Gateway/API | `gateway/main.py`, `routes.py`, `websocket.py`, `origin_check.py`, frontend `lib/api.ts` | `test_gateway*.py`, `test_frontend_page_endpoints.py`, `frontend/src/lib/api.test.ts` |
| Voice | `voice/`, runtime construction/controls, voice routes, frontend `voice-ws.ts` and stores/components | `test_voice*.py`, `test_runtime_voice*.py`, `test_ws_voice*.py`, frontend voice tests |
| Tool/skill/plugin | `tools/`, `skills/`, `plugins/registry.py`, `hub/`, startup wiring, independent SDK | `test_plugins_registry.py`, skill/approval/tool tests, SDK and individual example-plugin suites |
| Orchestration | `orchestrator/`, gateway registration/routes, frontend orchestrator page | `test_orchestrator.py` and related namespace/node tests |
| Desktop | `frontend/src-tauri/`, bundle scripts, `desktop_launcher.py`, PyInstaller spec, Next config | `test_desktop_packaging.py`, frontend type-check/build, platform packaging checks |

Use `rg --files tests/unit` to resolve exact filenames rather than inventing paths. Most current backend tests are under root `tests/unit/`; root pytest configuration selects `tests`, not `backend/tests`. SDK and example-plugin jobs run separately.

## Authoritative CI commands

Read `.github/workflows/ci*.yml` when updating checks. Current CI uses Python 3.12 and Node 20.

```text
python -m pip install -e ".[dev]"
python -m pytest tests/ -v --tb=short -q
ruff check neuralcleave tests --select E,F,W,I --ignore E501

# In frontend/
npm ci
npm run lint
npm run type-check
npx vitest run
npm run build

# SDK, after installing its dev dependencies
python -m pip install -e "./neuralcleave-sdk[dev]"
python -m pytest neuralcleave-sdk/tests/ -v --tb=short -q
```

Example-plugin tests run independently for `neuralcleave-github`, `neuralcleave-notion`, and `neuralcleave-google-calendar` after installation. Avoid combining identically named test modules into a single ad hoc invocation without checking import behavior.

For ordinary behavior changes, use the affected test modules first, then applicable CI checks. For desktop distribution, `npm run build:tauri` verifies static export, while `npm run tauri build` also packages the sidecar and requires the platform toolchain. Do not substitute a successful default Next build for desktop packaging verification.

On this Windows checkout use `.venv/Scripts/python.exe`. PowerShell can block `npm.ps1`/`npx.ps1`; invoke the normal `npm.cmd`/`npx.cmd` launchers. Non-login shell execution avoids slow profile startup. Do not change machine execution policy as a routine project fix.

## Isolation and test interpretation

`tests/conftest.py` sets these import-time stores to `:memory:` using `setdefault`:

- `NEURALCLEAVE_AUDIT_DB_PATH`
- `NEURALCLEAVE_APPROVAL_DB_PATH`
- `NEURALCLEAVE_SKILL_REVIEW_DB_PATH`
- `NEURALCLEAVE_PLUGIN_STATE_DB_PATH`

An already-set variable is not overridden. Avoid using real persistent paths in test runs. Other stores may require `tmp_path` or explicit dependency injection.

The autouse embedder fixture marks local embeddings unavailable by default to prevent model downloads and environment-dependent behavior. Semantic-path tests need explicit mock embeddings/async storage, or the relevant controlled fixture override; passing general pipeline tests alone does not verify real embedding inference.

Use async mocks for awaited collaborators. Global gateway runtime, renderer, registry, origin list, and persistent-store singletons require cleanup when tests mutate them. A passing unit suite is not proof of live provider availability, external channel delivery, hardware audio, or container startup.

`pyproject.toml` is canonical for wheel dependencies. `requirements.txt`, old contributor commands, README counts, and historical guides can drift. Missing declared dependencies in an existing venv are environment findings; do not remove correct imports to make that environment pass.

## Changes spanning configuration and clients

Trace new settings across dataclass default, TOML parse/serialization, `ENV:` secret handling if applicable, REST persistence, runtime update/restart behavior, and frontend hydration/save payload. Avoid overwriting unrelated TOML sections or sending empty credential fields as replacements.

For a new route, check the actual frontend request and response shape. For streaming, test incremental delivery, final authoritative text, errors, reconnect identity, and tool-marker suppression when affected. For a new plugin, verify live tool registration in addition to isolated plugin lifecycle methods.

For releases, inspect package, frontend, Tauri JSON/Cargo, SDK independent version, installer metadata, and workflows. For container work, verify the selected manifest's executable, Linux path casing, configuration sources, and readiness behavior before relying on a successful image build.
