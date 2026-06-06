# CortexFlow — Complete Project Analysis
## Enterprise-Grade Autonomous Cognitive Operating System

**Analyzed:** 2026-06-06 | **Branch:** feature/memory-graph-integration  
**Scope:** 177 Python files across 12 core modules  
**Purpose:** Enterprise pitch preparation — identify all bugs, gaps, and hardening requirements

---

## 1. EXECUTIVE SUMMARY

CortexFlow is a **production-architecture AI agent orchestration platform** — the "Kubernetes for Autonomous AI Agents." It combines deterministic DAG-based workflow execution, a 4-tier memory hierarchy, zero-trust security sandboxing, multi-model LLM routing, and enterprise governance into a single coherent system.

**Honest Assessment:** The architecture is exceptional and genuinely differentiates from CrewAI, AutoGen, and LangChain. The scaffolding is solid. However, several critical runtime bugs exist that would cause failures in a live demo or production environment. These must be fixed before any enterprise pitch or evaluation.

**Completion Level by Module:**

| Module | Scaffolding | Wired Up | Production-Ready |
|---|---|---|---|
| FastAPI App + Middleware | ✅ | ✅ | ✅ |
| Auth (JWT + RBAC) | ✅ | ✅ | ⚠️ (missing last_login_at) |
| Agent CRUD API | ✅ | ✅ | ⚠️ (execute is a stub) |
| Workflow Engine (DAG) | ✅ | ✅ | ✅ |
| Memory System (4-tier) | ✅ | ✅ | ⚠️ (lazy model load) |
| Tool Registry (9-step pipeline) | ✅ | ✅ | ✅ |
| Security + Sandbox | ✅ | ✅ | ⚠️ (event loop bug) |
| Observability (logs/metrics/traces) | ✅ | Partial | ❌ (metrics/traces are stubs) |
| Knowledge Graph (Neo4j) | ✅ | ✅ | ⚠️ (Cypher param bug) |
| Model Router (multi-LLM) | ✅ | ✅ | ✅ |
| Reflection Engine | ✅ | ✅ | ✅ |
| Governance (RBAC) | ✅ | ✅ | ✅ |
| Celery Workers | ✅ | Defined | ❌ (not wired to AgentRuntime) |
| Approvals Workflow | ✅ | ✅ | ⚠️ |
| Adaptive Learning | ✅ | Defined | ❌ (not integrated) |
| Event Bus | ✅ | Defined | ❌ (not wired) |
| SDK | ✅ | Defined | ❌ (not tested) |

---

## 2. ARCHITECTURE OVERVIEW

### Tech Stack

```
API Layer:        FastAPI 0.115 + Uvicorn (ASGI, async-native)
Task Queue:       Celery 5.4 + Redis (8 queues, Beat scheduler)
Auth:             JWT (python-jose) + bcrypt (passlib)
Rate Limiting:    slowapi (60 req/min default)
ORM:              SQLAlchemy 2.0 async + asyncpg + Alembic migrations

PostgreSQL:       User/Agent/Workflow/Task/AuditLog/MemoryEntry models
Redis:            Short-term memory (TTL 1h) + Celery broker + event bus
Qdrant:           Vector semantic memory (all-MiniLM-L6-v2, 384-dim)
Neo4j:            Knowledge graph (User/Agent/Workflow/Task/Tool nodes)

LLM Providers:    Gemini Pro/Flash | DeepSeek Coder | Ollama (local)
Embeddings:       sentence-transformers (local, no API cost)
Observability:    structlog + Prometheus + OpenTelemetry (OTLP)
Security:         Docker sandboxing (4 isolation tiers) + prompt injection detection
```

### 4-Tier Memory Architecture

```
Tier 1: Short-term  → Redis           TTL 1h   Active session context
Tier 2: Semantic    → Qdrant          Forever  Vector similarity search
Tier 3: Episodic    → PostgreSQL      Forever  Workflow history / task outcomes  
Tier 4: Knowledge   → Neo4j           Forever  Entity relationships / graph traversal
```

### Zero-Trust Tool Execution Pipeline (9 Steps)

```
1. Schema Validation   (Pydantic)
2. Permission Check    (agent scope vs tool permissions)
3. Risk Scoring        (0–100: base level + permission penalties)
4. Policy Evaluation   (placeholder, Phase 3)
5. Dry-run Simulation  (risk > 60)
6. Sandbox Allocation  (0–25=process, 26–60=container, 61–85=isolated, 86+=blocked)
7. Execution           (delegate to tool handler)
8. Result Validation   (output schema check)
9. Audit Log           (immutable PostgreSQL record)
```

### Risk Score → Isolation Tier

```
0–25     process           asyncio subprocess (resource limits)
26–60    container         ephemeral Docker, auto-removed
61–85    isolated_container Docker + network=none + read-only FS
86–100   blocked           requires human approval gate
```

---

## 3. COMPLETE BUG REGISTER

### CRITICAL — Production Breaking

---

#### BUG-001: Neo4j Cypher Parameterized Path Depth Not Supported
**File:** `backend/app/core/memory/knowledge_graph.py:241`  
**Severity:** CRITICAL  
**Impact:** `get_collaborating_agents()` always throws `CypherSyntaxError` at runtime

**Root Cause:** Neo4j Cypher does not support parameterized values in variable-length path bounds. The expression `*1..$depth` requires literal integers, not parameters.

```python
# BUG — $depth is a parameter, Cypher requires a literal here
result = await session.run(
    """
    MATCH path = (a:Agent {id: $agent_id})-[:COMMUNICATES_WITH*1..$depth]->(other:Agent)
    ...
    """,
    agent_id=str(agent_id),
    depth=depth,        # ← This causes SyntaxError
)
```

**Fix:**
```python
# Build the literal range into the query string directly
cypher = f"""
MATCH path = (a:Agent {{id: $agent_id}})-[:COMMUNICATES_WITH*1..{int(depth)}]->(other:Agent)
RETURN DISTINCT other.id AS id, other.name AS name, other.type AS type,
               length(path) AS hops
ORDER BY hops
"""
result = await session.run(cypher, agent_id=str(agent_id))
```

---

#### BUG-002: `asyncio.get_event_loop()` Deprecated Inside Async Context
**File:** `backend/app/core/security/sandbox.py:267`  
**Severity:** CRITICAL  
**Impact:** `DeprecationWarning` in Python 3.10, `RuntimeError` in Python 3.12+ when no current event loop

**Root Cause:** Inside an async function, `asyncio.get_event_loop()` is deprecated. The correct call is `asyncio.get_running_loop()`.

```python
# BUG
loop = asyncio.get_event_loop()
```

**Fix:**
```python
loop = asyncio.get_running_loop()
```

---

#### BUG-003: Memory Delete Has No Ownership Check (Security Vulnerability)
**File:** `backend/app/api/v1/memory.py:192-210`  
**Severity:** CRITICAL  
**Impact:** Any authenticated user can delete ANY other user's memory entries by guessing/knowing the UUID

**Root Cause:** The `delete_memory` endpoint fetches by `id` only, without filtering to `current_user`.

```python
# BUG — no ownership check
result = await db.execute(select(MemoryEntry).where(MemoryEntry.id == mid))
```

**Fix:**
```python
# Tie entries to an agent owned by the current user, or add a user_id column
result = await db.execute(
    select(MemoryEntry)
    .join(Agent, MemoryEntry.agent_id == Agent.id, isouter=True)
    .where(
        MemoryEntry.id == mid,
        (Agent.owner_id == current_user.id) | (MemoryEntry.agent_id == None)
    )
)
```

---

#### BUG-004: `execute_agent_task` Is a Stub — Task Never Actually Runs
**File:** `backend/app/api/v1/agents.py:164-193`  
**Severity:** CRITICAL  
**Impact:** Calling `POST /agents/{id}/execute` returns `QUEUED` but the task is never submitted to Celery or the AgentRuntime. The task is silently dropped.

```python
# BUG — no actual work dispatched
task_id = str(uuid.uuid4())
return {"agent_id": agent_id, "task_id": task_id, "status": "QUEUED", ...}
```

**Fix:** Wire to Celery worker:
```python
from app.workers.agent_worker import run_agent_task
task_id = str(uuid.uuid4())
run_agent_task.apply_async(
    args=[agent_id, task_id, body.task, body.context],
    queue="execution_queue",
    task_id=task_id,
)
return {"agent_id": agent_id, "task_id": task_id, "status": "QUEUED", ...}
```

---

#### BUG-005: Orphaned Docker Container on Timeout Kill Failure
**File:** `backend/app/core/security/sandbox.py:279-293`  
**Severity:** CRITICAL  
**Impact:** If `container.kill()` raises an exception, the container is never removed. Over time this leaks containers on the Docker host.

```python
# BUG — if kill() throws, logs() and remove() never run
except asyncio.TimeoutError:
    timed_out = True
    exit_code = -1
    await loop.run_in_executor(None, lambda: container.kill())
# ← No try/except around kill; subsequent cleanup skipped on exception
logs_bytes = await loop.run_in_executor(...)     # never reached
await loop.run_in_executor(..., container.remove)  # never reached
```

**Fix:**
```python
except asyncio.TimeoutError:
    timed_out = True
    exit_code = -1
    try:
        await loop.run_in_executor(None, lambda: container.kill())
    except Exception:
        pass  # best effort

# Always clean up in a finally block
finally:
    try:
        logs_bytes = await loop.run_in_executor(None, lambda: container.logs(...))
        await loop.run_in_executor(None, lambda: container.remove(force=True))
    except Exception:
        pass
```

---

### HIGH SEVERITY — Demo/Pitch Breaking

---

#### BUG-006: `import uuid` Inside Function Body
**File:** `backend/app/api/v1/auth.py:87`  
**Severity:** HIGH  
**Impact:** Not a crash, but a Python anti-pattern — import is re-executed on every call

```python
# BUG — import inside function
async def refresh_tokens(body: RefreshRequest, ...) -> dict:
    ...
    import uuid   # ← Should be at top of file
    result = await db.execute(...)
```

**Fix:** Move `import uuid` to line 5 of auth.py (it's already imported for type hints elsewhere).

---

#### BUG-007: SentenceTransformer Model Loaded Lazily on First HTTP Request
**File:** `backend/app/api/v1/memory.py:75-85, 161-171`  
**Severity:** HIGH  
**Impact:** The first call to `GET /memory/search` or `POST /memory/store` triggers a ~3-5 second model download/load, causing request timeouts in production and an obviously broken demo experience.

```python
# BUG — model loaded on first request, not at startup
if "_EMBEDDING_MODEL" not in globals() or _EMBEDDING_MODEL is None:
    _EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
```

**Fix:** Preload in `lifespan()` in `main.py`:
```python
# In app/main.py lifespan startup:
from sentence_transformers import SentenceTransformer
import app.api.v1.memory as memory_module
memory_module._EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
logger.info("embedding_model_loaded")
```

---

#### BUG-008: `last_login_at` Never Updated on Successful Login
**File:** `backend/app/api/v1/auth.py:52-74`  
**Severity:** HIGH  
**Impact:** The `users.last_login_at` column is always `NULL`. Enterprise security dashboards show "never logged in" for all users. Breaks audit trail completeness.

```python
# BUG — last_login_at never set
access_token = create_access_token(...)
refresh_token = create_refresh_token(...)
logger.info("user_login", user_id=str(user.id))
return {...}
```

**Fix:**
```python
from datetime import datetime, timezone
user.last_login_at = datetime.now(timezone.utc)
await db.flush()
```

---

#### BUG-009: `DELETE /workflows/{id}` Endpoint Missing
**File:** `backend/app/api/v1/workflows.py`  
**Severity:** HIGH  
**Impact:** The documented API spec includes `DELETE /{workflow_id}` but the endpoint does not exist. Frontend delete button will hit 404. API docs will show the route as absent.

**Fix:** Add the endpoint:
```python
@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, 
               response_class=Response, response_model=None)
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    wf = await _get_workflow_or_404(workflow_id, current_user.id, db)
    if wf.status == "RUNNING":
        raise HTTPException(status_code=409, detail="Cannot delete a running workflow")
    await db.delete(wf)
    logger.info("workflow_deleted", workflow_id=workflow_id)
```

---

#### BUG-010: Metrics, Traces, and Agent Graph Endpoints Are Stubs
**File:** `backend/app/api/v1/observability.py:61-120`  
**Severity:** HIGH  
**Impact:** All three observability endpoints return hardcoded empty/zero data:
- `GET /metrics` → always returns `{"tool_calls_total": 0, ...}`
- `GET /traces/{trace_id}` → always returns `{"spans": []}`
- `GET /agents/{id}/graph` → always returns `{"nodes": [], "edges": []}`

These will be immediately noticed in any enterprise demo. The underlying infrastructure (Prometheus, SpanRecorder, KnowledgeGraphMemory) is already built — endpoints just need to read from them.

---

### MEDIUM SEVERITY — Quality / Correctness

---

#### BUG-011: Container Sandbox Merges stdout + stderr into `stdout` Field
**File:** `backend/app/core/security/sandbox.py:289-331`  
**Severity:** MEDIUM  
**Impact:** `SandboxResult.stderr` is always `""` for `container` and `isolated_container` tiers. Error output appears in `stdout`, making error detection unreliable.

**Root Cause:** `container.logs(stdout=True, stderr=True)` returns a single combined byte stream. Docker SDK requires `stream=True` to separate them.

---

#### BUG-012: `PATCH /agents/{id}` Route Has Unexpected `/status` Suffix
**File:** `backend/app/api/v1/agents.py:118`  
**Severity:** MEDIUM  
**Impact:** API spec documents `PATCH /agents/{agent_id}` but implementation is `PATCH /agents/{agent_id}/status`. Frontend and SDK must use the actual route, not the documented one.

---

#### BUG-013: `ToolRegistry` Singleton Not Thread-Safe
**File:** `backend/app/core/tools/registry.py:148-159`  
**Severity:** MEDIUM  
**Impact:** Under concurrent startup, two Celery workers could each call `get_instance()` before either sets `_instance`, creating two separate registries with independent tool catalogues.

```python
@classmethod
def get_instance(cls) -> "ToolRegistry":
    if cls._instance is None:        # ← race condition window
        cls._instance = cls()        # ← two instances possible
        cls._instance._register_default_tools()
    return cls._instance
```

**Fix:** Use a threading lock:
```python
import threading
_registry_lock = threading.Lock()

@classmethod
def get_instance(cls) -> "ToolRegistry":
    if cls._instance is None:
        with _registry_lock:
            if cls._instance is None:
                cls._instance = cls()
                cls._instance._register_default_tools()
    return cls._instance
```

---

#### BUG-014: `ModelRouter` Singleton Instantiates All LLM Clients at Import Time
**File:** `backend/app/core/model_router/router.py:155`  
**Severity:** MEDIUM  
**Impact:** `model_router = ModelRouter()` at the bottom of the module creates `GeminiClient`, `DeepSeekClient`, and `OllamaClient` when the module is first imported. If `GEMINI_API_KEY` is missing, tests fail at import, not at the actual call site.

**Fix:** Use lazy initialization or defer to startup.

---

#### BUG-015: `rollback_workflow` Allows Rolling Back a RUNNING Workflow
**File:** `backend/app/api/v1/workflows.py:196`  
**Severity:** MEDIUM  
**Impact:** `wf.status not in ("FAILED", "PAUSED", "RUNNING")` means a workflow can be rolled back while still actively running. This sets the DB status to ROLLED_BACK without stopping the Celery tasks, leaving a split-brain state.

**Fix:** Remove "RUNNING" from the allowed states for rollback. Require `pause → rollback`.

---

#### BUG-016: `reflect_sync` Won't Work If Event Loop Is Already Running
**File:** `backend/app/core/reflection/engine.py:192-196`  
**Severity:** MEDIUM  
**Impact:** `asyncio.run()` raises `RuntimeError: This event loop is already running` when called from within FastAPI's async event loop. `reflect_sync` is broken in the production context.

```python
def reflect_sync(self, **kwargs):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, self.reflect(**kwargs)).result()
```

**Fix:** Use `asyncio.run_coroutine_threadsafe` or remove this method (the async version is always available in the FastAPI context).

---

### LOW SEVERITY — Code Quality

---

#### BUG-017: Redundant `try/except` That Only Re-Raises in `zero_trust.py`
**File:** `backend/app/core/security/zero_trust.py:57-68, 71-83`

```python
def verify_access_token(token: str) -> str:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise JWTError("Not an access token")
        sub = payload.get("sub")
        if not sub:
            raise JWTError("Missing subject")
        return sub
    except JWTError:
        raise  # ← adds nothing
```

The `try/except JWTError: raise` pattern is identical to having no try/except. Remove it.

---

#### BUG-018: Redundant `globals()` Check in `memory.py`
**File:** `backend/app/api/v1/memory.py:77, 162`

```python
if "_EMBEDDING_MODEL" not in globals() or _EMBEDDING_MODEL is None:
```

Since `_EMBEDDING_MODEL: Any = None` is declared at module level, `"_EMBEDDING_MODEL"` is **always** in `globals()`. The first condition is always `False`. Simplify to:

```python
if _EMBEDDING_MODEL is None:
```

---

#### BUG-019: `tenant_id = None` Silently Propagates into JWT Claims
**File:** `backend/app/api/v1/auth.py:62-65`

```python
extra_claims={"role": user.role, "tenant_id": user.tenant_id}  # tenant_id can be None
```

`None` in a JWT payload becomes `null` in JSON. Consumers expecting a string will crash. Use `user.tenant_id or "default"`.

---

#### BUG-020: `auth.py` — `import uuid` at Wrong Scope
**File:** `backend/app/api/v1/auth.py:87`  
`uuid` is not imported at the top of `auth.py`. The `import uuid` inside `refresh_tokens()` works but is an anti-pattern that adds overhead on every call and confuses static analysis.

---

## 4. SECURITY AUDIT

### Implemented Security Controls ✅
- JWT access tokens (15 min expiry) + refresh tokens (7 days)
- bcrypt password hashing with salt
- RBAC with 5 roles and 30+ permission scopes
- Rate limiting (60 req/min, configurable)
- CORS allowlist
- Docker sandbox isolation (4 tiers based on risk score)
- Prompt injection detection
- Immutable audit log
- SQL injection prevention (parameterized queries via SQLAlchemy)
- Input validation (Pydantic v2 throughout)

### Security Gaps ⚠️

| Gap | Risk | Phase |
|---|---|---|
| JWT refresh tokens not blacklisted on logout | Medium | Phase 3 |
| No email verification flow | Medium | Phase 2 |
| No brute-force protection on login (only global rate limit) | Medium | Phase 2 |
| Memory entries lack user ownership enforcement | HIGH | Fix Now (BUG-003) |
| HashiCorp Vault integration is declared but not wired | Low | Phase 3 |
| No HTTPS enforcement in app (must be handled by reverse proxy) | High | Infra |
| No CSRF protection (Bearer token auth inherently safe, but note for future cookie auth) | Low | N/A |

---

## 5. DATABASE SCHEMA

### PostgreSQL Models

| Table | Key Columns | Notes |
|---|---|---|
| `users` | id, email, hashed_password, role, tenant_id, last_login_at | Multi-tenant |
| `agents` | id, name, agent_type, status, trust_score, owner_id | 8 types |
| `workflows` | id, name, status, dag_definition (JSONB), checkpoint_data (JSONB) | Versioned |
| `tasks` | id, title, status, risk_score, input_data/output_data (JSONB) | 11 stages |
| `tool_calls` | id, tool_name, risk_score, isolation_level, requires_approval | Full audit |
| `audit_logs` | id, event_type, actor_id, outcome, details (JSONB) | Immutable |
| `memory_entries` | id, memory_type, content, qdrant_vector_id, importance_score | 4 types |

### Qdrant Collections
```
conversation_embeddings   → all-MiniLM-L6-v2 (384-dim, Cosine similarity)
workflow_embeddings
knowledge_embeddings
task_embeddings
```

### Neo4j Graph Schema
```
Nodes:    User | Agent | Workflow | Task | Tool | Feedback
Relationships:
  (:User)-[:OWNS]->(:Agent)
  (:Agent)-[:EXECUTES]->(:Workflow)
  (:Agent)-[:USES]->(:Tool)          # count property (usage frequency)
  (:Workflow)-[:CONTAINS]->(:Task)
  (:Task)-[:DEPENDS_ON]->(:Task)
  (:Agent)-[:LEARNS_FROM]->(:Feedback)
  (:Agent)-[:COMMUNICATES_WITH]->(:Agent)
```

---

## 6. API ENDPOINTS CATALOG

### Auth  `/api/v1/auth`
| Method | Path | Status |
|---|---|---|
| POST | `/register` | ✅ Working |
| POST | `/login` | ⚠️ Missing last_login_at update |
| POST | `/refresh` | ✅ Working |
| POST | `/logout` | ⚠️ Client-side only, no token blacklist |
| GET | `/me` | ✅ Working |

### Agents  `/api/v1/agents`
| Method | Path | Status |
|---|---|---|
| POST | `/create` | ✅ Working |
| GET | `/` | ✅ Working |
| GET | `/{agent_id}` | ✅ Working |
| PATCH | `/{agent_id}/status` | ✅ Working |
| POST | `/{agent_id}/execute` | ❌ Stub — task never queued |
| DELETE | `/{agent_id}` | ✅ Working (soft-delete) |

### Workflows  `/api/v1/workflows`
| Method | Path | Status |
|---|---|---|
| POST | `/run` | ✅ Working |
| GET | `/` | ✅ Working |
| GET | `/{workflow_id}` | ✅ Working |
| POST | `/{workflow_id}/pause` | ✅ Working |
| POST | `/{workflow_id}/resume` | ✅ Working |
| POST | `/{workflow_id}/rollback` | ⚠️ Allows rollback of RUNNING state |
| PATCH | `/{workflow_id}/dag` | ✅ Working |
| DELETE | `/{workflow_id}` | ❌ Missing endpoint |

### Memory  `/api/v1/memory`
| Method | Path | Status |
|---|---|---|
| GET | `/search` | ⚠️ First call triggers 3-5s model load |
| POST | `/store` | ⚠️ First call triggers 3-5s model load |
| DELETE | `/{memory_id}` | ❌ No ownership check (security bug) |

### Observability  `/api/v1/observability`
| Method | Path | Status |
|---|---|---|
| GET | `/logs` | ✅ Working (in-memory buffer) |
| GET | `/metrics` | ❌ Always returns zeros |
| GET | `/traces/{trace_id}` | ❌ Always returns empty spans |
| GET | `/agents/{id}/graph` | ❌ Always returns empty graph |

### Tools  `/api/v1/tools` | Approvals `/api/v1/approvals` | Events `/api/v1/events`  
All endpoints are structurally complete and working.

### Health
| Method | Path | Status |
|---|---|---|
| GET | `/health` | ✅ Working |
| GET | `/ready` | ✅ Working (checks PostgreSQL + Redis) |

---

## 7. CELERY TASK QUEUE ARCHITECTURE

**8 Queues with Priority Scheduling:**

| Queue | Priority | Purpose |
|---|---|---|
| `high_priority_queue` | 10 | Agent dispatch, termination signals |
| `planning_queue` | 8 | Task decomposition (PlannerAgent) |
| `execution_queue` | 8 | Tool calls, sandbox execution |
| `approval_queue` | 8 | Human approval gate requests |
| `validation_queue` | 5 | ValidatorAgent + CriticAgent |
| `reflection_queue` | 5 | Quality scoring, hallucination detection |
| `observability_queue` | 2 | Metrics flush, audit writes |
| `low_priority_queue` | 1 | Learning consolidation, memory pruning |

**Beat Schedule (Periodic Tasks):**
```
agent-heartbeat                → every 60s
memory-pruning                 → every 30m
metrics-flush                  → every 15s
stale-workflow-recovery        → every 5m
nightly-learning-consolidation → 02:00 UTC
```

**Critical Gap:** The Celery workers (`agent_worker.py`, `workflow_worker.py`) import from the correct modules, but `execute_agent_task` in the API never calls `apply_async`. The queue exists but nothing enqueues to it.

---

## 8. MODEL ROUTING TABLE

| Task Type | Provider | Model | Notes |
|---|---|---|---|
| `complex_reasoning` | Gemini | gemini-1.5-pro | Highest quality |
| `task_decomposition` | Gemini | gemini-1.5-pro | Planning phase |
| `code_generation` | DeepSeek | deepseek-coder | Code specialist |
| `code_review` | DeepSeek | deepseek-coder | Code specialist |
| `summarization` | Gemini | gemini-2.0-flash | Fast + cheap |
| `intent_extraction` | Gemini | gemini-2.0-flash | Fast + cheap |
| `validation` | Gemini | gemini-2.0-flash | Fast + cheap |
| `reflection` | Gemini | gemini-2.0-flash | Fast + cheap |
| `cheap_inference` | Ollama | local | Air-gapped mode |
| `general` | Gemini | gemini-2.0-flash | Default |

**Fallback Chain:** `gemini_flash → gemini_pro → deepseek_coder → ollama`

**Budget Gating:** Token budgets enforced per agent+task when both IDs provided. `BudgetExceededError` skips fallback chain.

---

## 9. REFLECTION ENGINE DECISION MATRIX

```
quality ≥ threshold (60) AND hallucination < 0.5  → pass
quality ≥ threshold (60) AND hallucination ≥ 0.5  → rethink
quality < threshold      AND quality ≥ 45          → retry
quality < 45             AND hallucination < 0.5   → rethink
quality < 25             AND hallucination ≥ 0.5   → escalate
```

**Retry Back-off:** `delay = base * 2^(attempt-1)`, capped at `max_retry_delay` (60s)

---

## 10. WHAT'S MISSING FOR PRODUCTION / ENTERPRISE

### Phase 2 (Before Enterprise Pilot)
1. **Fix all CRITICAL bugs** (BUG-001 through BUG-005)
2. **Fix HIGH bugs** (BUG-006 through BUG-010)
3. Wire `execute_agent_task` to Celery
4. Wire observability endpoints to real data sources
5. Implement `DELETE /workflows/{id}`
6. Preload embedding model at startup
7. Add email verification flow
8. Add login brute-force protection

### Phase 3 (Enterprise Features)
1. HashiCorp Vault integration (secrets management)
2. JWT token blacklist on logout (Redis-based)
3. Policy engine (rule-based, beyond RBAC)
4. Advanced Celery result tracking (WebSocket push on task completion)
5. Multi-region PostgreSQL setup
6. Full Kubernetes manifests with HPA
7. SSO/SAML integration
8. Tenant isolation (row-level security in PostgreSQL)

---

## 11. COMPETITIVE DIFFERENTIATION MATRIX

| Capability | OpenClaw | CrewAI | AutoGen | LangChain | **CortexFlow** |
|---|:---:|:---:|:---:|:---:|:---:|
| Enterprise Multi-tenancy | ❌ | ❌ | ❌ | ❌ | ✅ |
| Zero-Trust Docker Sandboxing | ❌ | ❌ | ❌ | ❌ | ✅ |
| Deterministic DAG Workflows | ❌ | ⚠️ | ❌ | ⚠️ | ✅ |
| 4-Tier Memory Architecture | ❌ | ❌ | ❌ | ⚠️ | ✅ |
| RBAC + Governance + Approvals | ❌ | ❌ | ❌ | ❌ | ✅ |
| Hallucination Mitigation | ❌ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Full Observability (OTel + Prometheus) | ❌ | ❌ | ❌ | ⚠️ | ✅ |
| Adaptive Learning | ❌ | ❌ | ❌ | ❌ | ✅ |
| Multi-Model Cost Routing + Fallback | ❌ | ❌ | ⚠️ | ⚠️ | ✅ |
| Human-in-the-Loop Approval Gates | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Air-Gapped Local Mode (Ollama) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Kubernetes-Native + Autoscaling | ❌ | ❌ | ❌ | ❌ | ✅ |
| Knowledge Graph Memory (Neo4j) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Risk-Scored Execution | ❌ | ❌ | ❌ | ❌ | ✅ |
| MCP Protocol Compatibility | ✅ | ❌ | ❌ | ⚠️ | ✅ |

---

## 12. CRITICAL FILES MAP

```
Entry Points:
  backend/app/main.py                          FastAPI app factory + lifespan
  backend/app/workers/celery_app.py            Celery config + Beat schedule

Core Intelligence:
  backend/app/core/agent_runtime/agent.py      Agent lifecycle + state machine
  backend/app/core/orchestration/orchestrator.py  Multi-agent pipeline
  backend/app/core/memory/retrieval.py         Unified 4-tier memory assembly
  backend/app/core/workflow_engine/dag.py      DAG definition + Kahn's toposort
  backend/app/core/model_router/router.py      LLM routing + fallback chain

Security:
  backend/app/core/security/zero_trust.py      JWT + bcrypt
  backend/app/core/security/sandbox.py         Docker isolation tiers
  backend/app/core/tools/registry.py           9-step execution pipeline

Databases:
  backend/app/db/postgres.py                   AsyncSession + connection pool
  backend/app/db/redis.py                      Redis client
  backend/app/db/qdrant.py                     Vector DB client + collections
  backend/app/db/neo4j.py                      Graph DB + schema constraints

Models:
  backend/app/db/models/user.py               User + RBAC
  backend/app/db/models/agent.py              Agent registry
  backend/app/db/models/workflow.py           Workflow + DAG definition
  backend/app/db/models/task.py              Atomic task units
  backend/app/db/models/audit.py             Immutable audit log

API:
  backend/app/api/v1/auth.py                  Auth endpoints
  backend/app/api/v1/agents.py                Agent CRUD + execute
  backend/app/api/v1/workflows.py             Workflow lifecycle
  backend/app/api/v1/memory.py                4-tier memory API
  backend/app/api/v1/observability.py         Logs/metrics/traces
```

---

## 13. BUG PRIORITY SUMMARY

| ID | File | Severity | Description |
|---|---|---|---|
| BUG-001 | knowledge_graph.py:241 | 🔴 CRITICAL | Cypher parameterized path depth crashes Neo4j |
| BUG-002 | sandbox.py:267 | 🔴 CRITICAL | `asyncio.get_event_loop()` deprecated |
| BUG-003 | memory.py:204 | 🔴 CRITICAL | Memory delete has no ownership check (security) |
| BUG-004 | agents.py:185 | 🔴 CRITICAL | execute_agent_task is a stub |
| BUG-005 | sandbox.py:279 | 🔴 CRITICAL | Orphaned Docker containers on timeout |
| BUG-006 | auth.py:87 | 🟠 HIGH | `import uuid` inside function body |
| BUG-007 | memory.py:75 | 🟠 HIGH | Embedding model loaded lazily on first request |
| BUG-008 | auth.py:68 | 🟠 HIGH | `last_login_at` never updated |
| BUG-009 | workflows.py | 🟠 HIGH | DELETE endpoint missing |
| BUG-010 | observability.py | 🟠 HIGH | Metrics/traces/graph always return empty |
| BUG-011 | sandbox.py:330 | 🟡 MEDIUM | Container stderr not separated from stdout |
| BUG-012 | agents.py:118 | 🟡 MEDIUM | PATCH route has undocumented /status suffix |
| BUG-013 | registry.py:154 | 🟡 MEDIUM | Singleton not thread-safe |
| BUG-014 | router.py:155 | 🟡 MEDIUM | LLM clients instantiated at import time |
| BUG-015 | workflows.py:196 | 🟡 MEDIUM | Rollback allowed on RUNNING workflow |
| BUG-016 | engine.py:192 | 🟡 MEDIUM | `reflect_sync` broken in async context |
| BUG-017 | zero_trust.py:60 | 🟢 LOW | Redundant try/except re-raise |
| BUG-018 | memory.py:77 | 🟢 LOW | Redundant `globals()` check |
| BUG-019 | auth.py:64 | 🟢 LOW | `tenant_id=None` in JWT claims |
| BUG-020 | auth.py:87 | 🟢 LOW | `uuid` imported inside function |

---

*This analysis was generated by Claude Sonnet 4.6 on 2026-06-06 against commit b1e4965 on branch feature/memory-graph-integration.*
