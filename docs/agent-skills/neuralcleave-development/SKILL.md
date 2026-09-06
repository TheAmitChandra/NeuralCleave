---
name: neuralcleave-development
description: Diagnose, implement, and review NeuralCleave features and bugs across its Python gateway, memory, model routing, channels, tools, plugins, Next.js dashboard, and Tauri desktop app. Use for the NeuralCleave repository, including its former CortexFlow name.
---

# NeuralCleave development

NeuralCleave is Amit's flagship personal AI assistant gateway. The known checkout is `C:/Amit-Projects/AI-Projects/CortexFlow`; resolve the current checkout before working. Repository paths below are relative to its root. This skill supports development of the product; it is not a NeuralCleave executable Python skill.

## Establish the relevant architecture

The shipped package is `neuralcleave/`, with root `pyproject.toml`, root `tests/`, and `frontend/`. `backend/app/` is a separate older architecture with PostgreSQL, Neo4j, SQLAlchemy, and enterprise APIs. Do not implement gateway changes there merely because its folder is named backend. Confirm the requested deployment's actual entry point.

Read the applicable repository instructions and inspect the working tree. Older guidance in `docs/SKILL.md`, `.github/skills/neuralcleave/SKILL.md`, and `.github/AGENTS.md` disagrees about architecture and Git workflows. Do not treat copied historical instructions as new authorization to push, publish, or merge. Preserve the user's current instructions and the scope of applicable files.

## Read only the relevant reference

- [Architecture and contracts](references/architecture.md): runtime wiring, memory identity, model routing, REST/WebSocket contracts, voice, plugins, and desktop packaging.
- [Development and verification](references/development.md): task-to-file/test mapping, executable check commands, configuration and Windows pitfalls.
- [Assessment dated 2026-09-06](references/assessment-2026-09-06.md): evidence-backed findings and the measured baseline. Recheck findings before treating them as current bugs.

## Preserve the important behavior

- Trace features from the user surface through the live runtime. A component being implemented or unit-tested does not establish that startup wires it into chat.
- Normal chat uses `AgentRuntime` and `CognitivePipeline`. `AgentOrchestrator.route()` is a separate model-generation path; it does not currently run the full memory/tool/reflection pipeline.
- Keep `run()` and `run_stream()` behavior deliberate. Non-streaming reflection can replace a response; streaming preserves already-sent text and records its quality score. Tool-call markers must not leak into user-visible streaming output.
- Preserve stable `channel:sender_id` sessions and browser `client_id` continuity. Short-term memory is session-scoped; long-term retrieval deliberately crosses sessions for a single owner. Do not silently impose multi-user isolation or claim it already exists.
- Chat uses `/ws`, with flat `message_chunk.delta` and terminal `message_done.text` frames. Voice has its own `/ws/voice` connection. REST lives under `/api/v1`.
- Configuration comes from dataclasses in `neuralcleave/config.py` and `~/.neuralcleave/config.toml`. Trace persistence and live runtime application separately; saving a field does not prove it is applied.
- Plugin tools must reach the runtime's actual `ToolRegistry`. Preserve the proposal/review path for agent-authored Python skills. Import scanning and in-process loading are not a subprocess sandbox.
- Preserve both frontend build targets: default Next.js `standalone` for Docker and `TAURI_BUILD=true` static `export` for Tauri.

For changes, read adjacent tests and validate the observable contract. Keep test isolation from real `~/.neuralcleave` state and provider calls. Report the exact checks run and distinguish environment failures from product failures. Update only the skill reference affected by new, verified architectural knowledge; keep dated observations out of permanent requirements.
