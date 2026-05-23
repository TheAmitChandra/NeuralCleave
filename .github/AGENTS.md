# CortexFlow — AGENTS.md

> This file defines guidance for AI coding agents (GitHub Copilot, Claude, etc.)
> working inside the CortexFlow repository.

---

## Project Identity

**CortexFlow** is an Autonomous Cognitive Operating System for AI Agents.
- **Backend**: Python 3.12 + FastAPI + SQLAlchemy async + Alembic + Celery
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind CSS + Zustand + React Query v5
- **Databases**: PostgreSQL 16, Qdrant, Neo4j, Redis

---

## Absolute Rules for Agents

1. **ONE file changed = ONE immediate commit + ONE push. No exceptions.**
2. Never accumulate multiple changes before committing.
3. Never use `git add -A` — always stage the exact file changed.
4. Never delete feature branches — all branches are kept permanently.
5. Never commit secrets, API keys, or passwords.
6. Never expose internal error details in API responses.
7. Never use string interpolation in SQL — always use parameterized queries.
8. Never hardcode configuration — use `backend/app/config.py` (pydantic-settings).

---

## Git Commit Format

```
<type>(<scope>): <short description>

Types: feat | fix | refactor | test | docs | chore | security
Scopes: agent-runtime | memory | workflow | security | tools | frontend | db | api | observability | learning
```

---

## Branch Strategy

```bash
git checkout -b feature/<module-name>

# For EVERY single file:
git add <that-exact-file>
git commit -m "feat(<scope>): <description>"
git push origin feature/<module-name>

# After all files done:
git checkout main
git merge feature/<module-name> --no-ff -m "feat(<scope>): merge <description>"
git push origin main
```

---

## Backend Conventions

- All I/O must use `async/await`
- All request/response schemas must be Pydantic models in `backend/app/schemas/`
- Use `FastAPI.Depends()` for DB sessions and auth
- Use `SQLAlchemy` async ORM for PostgreSQL; never raw SQL strings
- Use `Alembic` for all database schema changes — never alter tables manually
- Tests live in `backend/tests/unit/` and `backend/tests/integration/`
- Minimum test coverage: **80%** (enforced by CI)
- Test naming: `test_<module>_<function>_<scenario>`
- Run: `cd backend && pytest tests/ -v --cov=app --cov-fail-under=80`

---

## Frontend Conventions

- All page components that use hooks must have `"use client"` directive
- Server state → **React Query** (`useQuery`, `useMutation`, `useQueryClient`)
- UI/client state → **Zustand** stores in `frontend/src/store/`
- API calls → `frontend/src/lib/api.ts` (base URL from `NEXT_PUBLIC_API_URL`)
- Dark theme only — slate-950 background, slate-800 cards, slate-700 borders
- Run type-check: `cd frontend && pnpm type-check`

---

## Security Requirements

- All user inputs validated with Pydantic before processing
- All tool executions must pass risk analysis
- JWT tokens: 15 min access, 7 day refresh
- Rate limiting on all API endpoints
- Prompt injection check on all LLM inputs
- Audit log every tool execution and permission change

---

## Key File Locations

| File | Purpose |
|---|---|
| `backend/app/config.py` | All settings via pydantic-settings |
| `backend/app/main.py` | FastAPI app entry + router registration |
| `backend/app/api/v1/` | All REST API endpoints |
| `backend/app/core/` | All 12 core modules |
| `backend/app/db/models/` | SQLAlchemy ORM models |
| `backend/alembic/versions/` | Database migration files |
| `frontend/src/app/(dashboard)/` | All dashboard pages |
| `frontend/src/store/` | Zustand stores |
| `frontend/src/lib/api.ts` | Axios API client |
| `deploy/docker-compose.dev.yml` | Local dev stack |
| `deploy/k8s/` | Kubernetes manifests |
