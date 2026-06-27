# Complete Pydantic Schemas

Move inline Pydantic schemas from API router files under `backend/app/api/v1/` (agents, workflows, memory, tools, events, approvals, observability) to dedicated files under `backend/app/schemas/` to clean up the backend codebase and improve modularity.

## Proposed Changes

We will perform this work on a new feature branch `feature/pydantic-schemas`.
Per the project rules, we will edit, commit, and push each file **individually**. One file changed = one immediate commit.

### Schemas

#### [NEW] [agents.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/schemas/agents.py)
Create `backend/app/schemas/agents.py` with schemas:
- `AgentCreateRequest`
- `AgentStatusPatch`
- `AgentExecuteRequest`
- `AgentResponse`
- `AgentExecuteResponse`

#### [NEW] [workflows.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/schemas/workflows.py)
Create `backend/app/schemas/workflows.py` with schemas:
- `WorkflowRunRequest`
- `WorkflowResponse`
- `WorkflowActionResponse`
- `DagUpdateRequest`

#### [NEW] [memory.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/schemas/memory.py)
Create `backend/app/schemas/memory.py` with schemas:
- `MemoryStoreRequest`
- `MemoryResponse`
- `MemorySearchResponse`

#### [NEW] [tools.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/schemas/tools.py)
Create `backend/app/schemas/tools.py` with schemas:
- `ToolListItem`
- `ToolExecuteRequest`
- `ToolExecuteResponse`

#### [NEW] [events.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/schemas/events.py)
Create `backend/app/schemas/events.py` with schemas:
- `WebhookPayload`
- `TriggerRegistration`
- `TriggerResponse`
- `EventDispatchResponse`

#### [NEW] [observability.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/schemas/observability.py)
Create `backend/app/schemas/observability.py` with schemas:
- `LogEntryResponse`
- `MetricsResponse`
- `TraceResponse`
- `AgentGraphResponse`

#### [NEW] [approvals.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/schemas/approvals.py)
Create `backend/app/schemas/approvals.py` with schemas:
- `ApprovalResponse`
- `RejectRequest`
- `CancelRequest`

#### [NEW] [governance.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/schemas/governance.py)
Create an empty placeholder `backend/app/schemas/governance.py` file or keep it as approvals.

#### [MODIFY] [__init__.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/schemas/__init__.py)
Update `backend/app/schemas/__init__.py` to import and expose all the newly defined schemas.

### API Routes

#### [MODIFY] [agents.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/api/v1/agents.py)
Import the schema classes from `app.schemas.agents` and remove their inline class definitions.

#### [MODIFY] [workflows.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/api/v1/workflows.py)
Import the schema classes from `app.schemas.workflows` and remove their inline class definitions.

#### [MODIFY] [memory.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/api/v1/memory.py)
Import the schema classes from `app.schemas.memory` and remove their inline class definitions.

#### [MODIFY] [tools.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/api/v1/tools.py)
Import the schema classes from `app.schemas.tools` and remove their inline class definitions.

#### [MODIFY] [events.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/api/v1/events.py)
Import the schema classes from `app.schemas.events` and remove their inline class definitions.

#### [MODIFY] [approvals.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/api/v1/approvals.py)
Import the schema classes from `app.schemas.approvals` and remove their inline class definitions.

#### [MODIFY] [observability.py](file:///c:/Amit-Projects/AI-Projects/CortexFlow-AI/backend/app/api/v1/observability.py)
Import the schema classes from `app.schemas.observability` and remove their inline class definitions.

---

## Verification Plan

### Automated Tests
- Run backend unit tests: `pytest tests/unit/ -v --cov=app --cov-fail-under=80`
- Run static security scan: `bandit -r app/ -f screen`

### Manual Verification
- Verify that FastAPI swagger docs (http://localhost:8000/docs) load correctly and schema specifications are accurately preserved.
