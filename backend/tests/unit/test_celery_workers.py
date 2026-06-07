"""Unit tests for Celery worker tasks — agent_worker and workflow_worker.

All Celery tasks are tested by calling them directly (task.run(...)) with their
underlying coroutines fully mocked, so no broker/backend is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build minimal task payloads
# ---------------------------------------------------------------------------


def _agent_payload(**kwargs):
    return {
        "agent_id": "agent-test-001",
        "task_id": "task-test-001",
        "description": "Test task description",
        "agent_type": "generic",
        "priority": 5,
        "metadata": {},
        **kwargs,
    }


def _workflow_dag():
    return {
        "nodes": [
            {
                "node_id": "n1",
                "tool_name": "file.read",
                "parameters": {"path": "/tmp/x"},
                "depends_on": [],
            },
            {"node_id": "n2", "tool_name": "file.write", "parameters": {}, "depends_on": ["n1"]},
        ],
        "edges": [{"source": "n1", "target": "n2", "type": "success"}],
    }


# ===========================================================================
# celery_app tests
# ===========================================================================


class TestCeleryApp:
    def test_celery_app_importable(self):
        from app.workers.celery_app import celery_app

        assert celery_app is not None

    def test_celery_app_name(self):
        from app.workers.celery_app import celery_app

        assert celery_app.main == "cortexflow"

    def test_eight_queues_defined(self):
        from app.workers.celery_app import celery_app

        queue_names = {q.name for q in celery_app.conf.task_queues}
        expected = {
            "high_priority_queue",
            "planning_queue",
            "execution_queue",
            "approval_queue",
            "validation_queue",
            "reflection_queue",
            "observability_queue",
            "low_priority_queue",
        }
        assert expected.issubset(queue_names)

    def test_task_routes_registered(self):
        from app.workers.celery_app import celery_app

        routes = celery_app.conf.task_routes
        assert "app.workers.agent_worker.run_agent_task" in routes
        assert "app.workers.workflow_worker.execute_workflow" in routes
        assert "app.workers.workflow_worker.rollback_workflow" in routes

    def test_execution_queue_is_default(self):
        from app.workers.celery_app import celery_app

        assert celery_app.conf.task_default_queue == "execution_queue"

    def test_beat_schedule_has_expected_tasks(self):
        from app.workers.celery_app import celery_app

        beat = celery_app.conf.beat_schedule
        assert "agent-heartbeat" in beat
        assert "memory-pruning" in beat
        assert "stale-workflow-recovery" in beat
        assert "nightly-learning-consolidation" in beat

    def test_task_acks_late_enabled(self):
        from app.workers.celery_app import celery_app

        assert celery_app.conf.task_acks_late is True

    def test_worker_prefetch_multiplier_is_one(self):
        from app.workers.celery_app import celery_app

        assert celery_app.conf.worker_prefetch_multiplier == 1

    def test_json_serializer_configured(self):
        from app.workers.celery_app import celery_app

        assert celery_app.conf.task_serializer == "json"
        assert "json" in celery_app.conf.accept_content


# ===========================================================================
# agent_worker tests
# ===========================================================================


class TestRunAgentTask:
    @patch("app.workers.agent_worker.AgentRuntime")
    @patch("app.workers.agent_worker.asyncio.run")
    def test_run_agent_task_success(self, mock_run, mock_runtime_cls):
        from app.workers.agent_worker import run_agent_task

        mock_runtime = MagicMock()
        mock_runtime_cls.return_value = mock_runtime
        mock_run.return_value = {"output": "task result"}

        result = run_agent_task.run(_agent_payload())

        assert result["success"] is True
        assert result["agent_id"] == "agent-test-001"
        assert result["task_id"] == "task-test-001"
        assert "completed_at" in result

    @patch("app.workers.agent_worker.AgentRuntime")
    @patch("app.workers.agent_worker.asyncio.run")
    def test_run_agent_task_uses_agent_type(self, mock_run, mock_runtime_cls):
        from app.core.agent_runtime.agent import AgentConfig
        from app.workers.agent_worker import run_agent_task

        mock_runtime_cls.return_value = MagicMock()
        mock_run.return_value = {}

        run_agent_task.run(_agent_payload(agent_type="code_generator"))

        call_kwargs = mock_runtime_cls.call_args[1]
        assert call_kwargs["config"].agent_type == "code_generator"

    @patch("app.workers.agent_worker.AgentRuntime")
    @patch("app.workers.agent_worker.asyncio.run", side_effect=RuntimeError("execution failed"))
    def test_run_agent_task_retries_on_exception(self, mock_run, mock_runtime_cls):
        from app.workers.agent_worker import run_agent_task

        mock_runtime_cls.return_value = MagicMock()

        with pytest.raises(Exception):
            run_agent_task.run(_agent_payload())

    @patch("app.workers.agent_worker.asyncio.run")
    @patch("app.workers.agent_worker.AgentRuntime")
    def test_run_agent_task_soft_timeout_returns_error_dict(self, mock_runtime_cls, mock_run):
        from celery.exceptions import SoftTimeLimitExceeded

        from app.workers.agent_worker import run_agent_task

        mock_runtime_cls.return_value = MagicMock()
        mock_run.side_effect = SoftTimeLimitExceeded()

        result = run_agent_task.run(_agent_payload())
        assert result["success"] is False
        assert result["error"] == "soft_time_limit_exceeded"


class TestDecomposeTask:
    @patch("app.workers.agent_worker.PlannerAgent")
    @patch("app.workers.agent_worker.asyncio.run")
    def test_decompose_task_success(self, mock_run, mock_planner_cls):
        from app.workers.agent_worker import decompose_task

        mock_planner_cls.return_value = MagicMock()
        mock_run.return_value = {"subtasks": ["a", "b"], "dag": {}}

        result = decompose_task.run("Build a web scraper", context={"user_id": "u1"})

        assert result["success"] is True
        assert "plan" in result

    @patch("app.workers.agent_worker.PlannerAgent")
    @patch("app.workers.agent_worker.asyncio.run", side_effect=ValueError("bad input"))
    def test_decompose_task_retries_on_failure(self, mock_run, mock_planner_cls):
        from app.workers.agent_worker import decompose_task

        mock_planner_cls.return_value = MagicMock()
        with pytest.raises(Exception):
            decompose_task.run("bad task")


class TestValidateAgentOutput:
    @patch("app.workers.agent_worker.ValidatorAgent")
    @patch("app.workers.agent_worker.asyncio.run")
    def test_validate_success(self, mock_run, mock_validator_cls):
        from app.workers.agent_worker import validate_agent_output

        mock_validator_cls.return_value = MagicMock()
        mock_run.return_value = {"passed": True, "score": 92, "issues": []}

        result = validate_agent_output.run("task-001", {"output": "hello"})
        assert result["success"] is True
        assert result["task_id"] == "task-001"
        assert "validation" in result


class TestCritiqueAgentOutput:
    @patch("app.workers.agent_worker.CriticAgent")
    @patch("app.workers.agent_worker.asyncio.run")
    def test_critique_success(self, mock_run, mock_critic_cls):
        from app.workers.agent_worker import critique_agent_output

        mock_critic_cls.return_value = MagicMock()
        mock_run.return_value = {
            "quality_score": 88,
            "feedback": "Good.",
            "recommendation": "deploy",
        }

        result = critique_agent_output.run("task-001", {"output": "good code"})
        assert result["success"] is True
        assert "critique" in result


class TestReflectOnExecution:
    @patch("app.workers.agent_worker.ReflectionEngine")
    @patch("app.workers.agent_worker.asyncio.run")
    def test_reflect_success(self, mock_run, mock_engine_cls):
        from app.workers.agent_worker import reflect_on_execution

        mock_engine_cls.return_value = MagicMock()
        mock_run.return_value = {"score": 80, "insights": [], "retry_recommendation": "none"}

        record = {"task_id": "t1", "agent_id": "a1", "output": {}, "duration_ms": 500}
        result = reflect_on_execution.run(record)
        assert result["success"] is True
        assert "reflection" in result


class TestWriteAuditEvent:
    @patch("app.workers.agent_worker.asyncio.run")
    def test_write_audit_event_does_not_raise(self, mock_run):
        from app.workers.agent_worker import write_audit_event

        # Patch the AuditLogger import inside the task
        with patch.dict("sys.modules", {"app.core.security.audit": MagicMock()}):
            mock_run.return_value = None
            # Should not raise even if AuditLogger raises
            write_audit_event.run({"event_type": "tool_executed", "payload": {}})

    @patch("app.workers.agent_worker.asyncio.run", side_effect=RuntimeError("db down"))
    def test_write_audit_event_swallows_errors(self, mock_run):
        from app.workers.agent_worker import write_audit_event

        with patch.dict("sys.modules", {"app.core.security.audit": MagicMock()}):
            # Must not raise — observability is fire-and-forget
            write_audit_event.run({"event_type": "heartbeat", "payload": {}})


class TestRequestHumanApproval:
    @patch("app.workers.agent_worker.asyncio.run")
    @patch("app.workers.agent_worker.ApprovalWorkflow")
    @patch("app.workers.agent_worker.ApprovalRequest")
    def test_request_approval_success(self, mock_req_cls, mock_mgr_cls, mock_run):
        from app.workers.agent_worker import request_human_approval

        mock_mgr_cls.return_value = MagicMock()
        mock_run.return_value = "approval-123"

        result = request_human_approval.run(
            {
                "action": "delete_file",
                "agent_id": "agent-1",
                "risk_score": 80,
                "context": {"path": "/etc/passwd"},
            }
        )
        assert result["success"] is True
        assert result["approval_id"] == "approval-123"
        assert result["status"] == "pending"


class TestHeartbeatSweep:
    @patch("app.workers.agent_worker.asyncio.run")
    def test_heartbeat_sweep_does_not_raise(self, mock_run):
        from app.workers.agent_worker import agent_heartbeat_sweep

        with patch.dict("sys.modules", {"app.core.agent_runtime.heartbeat": MagicMock()}):
            mock_run.return_value = None
            agent_heartbeat_sweep.run()

    @patch("app.workers.agent_worker.asyncio.run", side_effect=ConnectionError("redis down"))
    def test_heartbeat_sweep_swallows_connection_errors(self, mock_run):
        from app.workers.agent_worker import agent_heartbeat_sweep

        with patch.dict("sys.modules", {"app.core.agent_runtime.heartbeat": MagicMock()}):
            # Should not propagate — beat tasks must never crash the scheduler
            agent_heartbeat_sweep.run()


class TestPruneMemory:
    @patch("app.workers.agent_worker.asyncio.run")
    def test_prune_memory_success(self, mock_run):
        from app.workers.agent_worker import prune_memory

        mock_run.return_value = {"pruned": 42, "deduplicated": 7}
        with patch.dict("sys.modules", {"app.core.memory.retrieval": MagicMock()}):
            result = prune_memory.run()
        assert result["success"] is True


# ===========================================================================
# workflow_worker tests
# ===========================================================================


class TestExecuteWorkflow:
    @patch("app.workers.workflow_worker.WorkflowScheduler")
    @patch("app.workers.workflow_worker.WorkflowDAG")
    @patch("app.workers.workflow_worker.asyncio.run")
    def test_execute_workflow_success(self, mock_run, mock_dag_cls, mock_scheduler_cls):
        from app.workers.workflow_worker import execute_workflow

        mock_dag_cls.from_dict.return_value = MagicMock()
        mock_scheduler_cls.return_value = MagicMock()
        mock_run.return_value = {"n1": "output1", "n2": "output2"}

        result = execute_workflow.run("wf-001", _workflow_dag(), initiator_id="agent-1")

        assert result["success"] is True
        assert result["workflow_id"] == "wf-001"
        assert "results" in result
        assert "completed_at" in result

    @patch("app.workers.workflow_worker.WorkflowDAG")
    @patch("app.workers.workflow_worker.asyncio.run", side_effect=RuntimeError("dag error"))
    @patch("app.workers.workflow_worker.WorkflowScheduler")
    def test_execute_workflow_retries_on_failure(self, mock_scheduler_cls, mock_run, mock_dag_cls):
        from app.workers.workflow_worker import execute_workflow

        mock_dag_cls.from_dict.return_value = MagicMock()
        mock_scheduler_cls.return_value = MagicMock()

        with pytest.raises(Exception):
            execute_workflow.run("wf-fail", _workflow_dag())

    @patch("app.workers.workflow_worker.WorkflowScheduler")
    @patch("app.workers.workflow_worker.WorkflowDAG")
    @patch("app.workers.workflow_worker.asyncio.run")
    def test_execute_workflow_soft_timeout(self, mock_run, mock_dag_cls, mock_scheduler_cls):
        from celery.exceptions import SoftTimeLimitExceeded

        from app.workers.workflow_worker import execute_workflow

        mock_dag_cls.from_dict.return_value = MagicMock()
        mock_scheduler_cls.return_value = MagicMock()
        mock_run.side_effect = SoftTimeLimitExceeded()

        result = execute_workflow.run("wf-timeout", _workflow_dag())
        assert result["success"] is False
        assert result["error"] == "soft_time_limit_exceeded"


class TestExecuteWorkflowNode:
    @patch("app.workers.workflow_worker.WorkflowScheduler")
    @patch("app.workers.workflow_worker.asyncio.run")
    def test_execute_node_success(self, mock_run, mock_scheduler_cls):
        from app.workers.workflow_worker import execute_workflow_node

        mock_scheduler_cls.return_value = MagicMock()
        mock_run.return_value = {"data": "node output"}

        node = {"node_id": "n1", "tool_name": "file.read", "parameters": {}, "depends_on": []}
        result = execute_workflow_node.run("wf-001", node, upstream_results={})

        assert result["success"] is True
        assert result["node_id"] == "n1"
        assert result["output"] == {"data": "node output"}

    @patch("app.workers.workflow_worker.WorkflowScheduler")
    @patch("app.workers.workflow_worker.asyncio.run", side_effect=ValueError("tool missing"))
    def test_execute_node_retries_on_failure(self, mock_run, mock_scheduler_cls):
        from app.workers.workflow_worker import execute_workflow_node

        mock_scheduler_cls.return_value = MagicMock()
        node = {"node_id": "n1", "tool_name": "missing.tool", "parameters": {}, "depends_on": []}
        with pytest.raises(Exception):
            execute_workflow_node.run("wf-001", node)


class TestRollbackWorkflow:
    @patch("app.workers.workflow_worker.RecoveryManager")
    @patch("app.workers.workflow_worker.asyncio.run")
    def test_rollback_success(self, mock_run, mock_recovery_cls):
        from app.workers.workflow_worker import rollback_workflow

        mock_recovery_cls.return_value = MagicMock()
        mock_run.return_value = None

        result = rollback_workflow.run("wf-001", reason="execution_failure")
        assert result["success"] is True
        assert result["workflow_id"] == "wf-001"
        assert "rolled_back_at" in result


class TestCheckpointWorkflowState:
    @patch("app.workers.workflow_worker.CheckpointManager")
    @patch("app.workers.workflow_worker.asyncio.run")
    def test_checkpoint_success(self, mock_run, mock_checkpoint_cls):
        from app.workers.workflow_worker import checkpoint_workflow_state

        mock_checkpoint_cls.return_value = MagicMock()
        mock_run.return_value = "ckpt-abc"

        result = checkpoint_workflow_state.run(
            "wf-001", {"status": "RUNNING", "completed_nodes": ["n1"]}
        )
        assert result["success"] is True
        assert result["checkpoint_id"] == "ckpt-abc"


class TestRecoverStaleWorkflows:
    @patch("app.workers.workflow_worker.RecoveryManager")
    @patch("app.workers.workflow_worker.asyncio.run")
    def test_recover_stale_success(self, mock_run, mock_recovery_cls):
        from app.workers.workflow_worker import recover_stale_workflows

        mock_recovery_cls.return_value = MagicMock()
        mock_run.return_value = {"recovered": 2, "rolled_back": 1}

        result = recover_stale_workflows.run()
        assert result["success"] is True
        assert result["stats"]["recovered"] == 2

    @patch("app.workers.workflow_worker.RecoveryManager")
    @patch("app.workers.workflow_worker.asyncio.run", side_effect=ConnectionError("db down"))
    def test_recover_stale_returns_error_dict_on_failure(self, mock_run, mock_recovery_cls):
        from app.workers.workflow_worker import recover_stale_workflows

        mock_recovery_cls.return_value = MagicMock()
        result = recover_stale_workflows.run()
        assert result["success"] is False
        assert "error" in result


class TestWorkflowWriteAuditEvent:
    @patch("app.workers.workflow_worker.asyncio.run")
    def test_write_audit_event_fire_and_forget(self, mock_run):
        from app.workers.workflow_worker import write_audit_event

        mock_run.return_value = None
        with patch.dict("sys.modules", {"app.core.security.audit": MagicMock()}):
            write_audit_event.run(
                {"event_type": "workflow_started", "payload": {"workflow_id": "wf-1"}}
            )
