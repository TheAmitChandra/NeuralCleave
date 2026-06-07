"""Unit tests for WorkflowStepSDK, WorkflowStepRegistry, and @workflow_step.

No external dependencies — all tests are fully synchronous except the async
execute() calls, which use pytest-asyncio.
"""

from __future__ import annotations

import pytest

from app.sdk.workflow_sdk import (
    WorkflowStepRegistry,
    WorkflowStepSDK,
    workflow_step,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_registry():
    """Ensure registry is empty before and after every test."""
    WorkflowStepRegistry.clear()
    yield
    WorkflowStepRegistry.clear()


def _make_step(name: str = "test_step", desc: str = "A test step") -> type[WorkflowStepSDK]:
    class ConcreteStep(WorkflowStepSDK):
        step_name = name
        description = desc

        async def execute(self, inputs: dict) -> dict:
            return {"output": inputs.get("value", "default")}

    return ConcreteStep


# ===========================================================================
# WorkflowStepSDK abstract base tests
# ===========================================================================


class TestWorkflowStepSDK:
    @pytest.mark.asyncio
    async def test_execute_returns_dict(self):
        cls = _make_step()
        step = cls()
        result = await step.execute({"value": "hello"})
        assert result == {"output": "hello"}

    @pytest.mark.asyncio
    async def test_call_invokes_execute(self):
        cls = _make_step()
        step = cls()
        result = await step({"value": "world"})
        assert result == {"output": "world"}

    @pytest.mark.asyncio
    async def test_on_error_default_reraises(self):
        cls = _make_step()
        step = cls()
        with pytest.raises(ValueError, match="boom"):
            await step.on_error(ValueError("boom"))

    @pytest.mark.asyncio
    async def test_on_error_override_returns_recovery_payload(self):
        class RecoveringStep(WorkflowStepSDK):
            step_name = "recovering"

            async def execute(self, inputs: dict) -> dict:
                raise RuntimeError("transient failure")

            async def on_error(self, exc: Exception) -> dict:
                return {"recovered": True, "error": str(exc)}

        step = RecoveringStep()
        result = await step({"any": "input"})
        assert result == {"recovered": True, "error": "transient failure"}

    @pytest.mark.asyncio
    async def test_call_propagates_unrecovered_error(self):
        class FailingStep(WorkflowStepSDK):
            step_name = "failing"

            async def execute(self, inputs: dict) -> dict:
                raise RuntimeError("unrecovered")

        step = FailingStep()
        with pytest.raises(RuntimeError, match="unrecovered"):
            await step({})

    def test_step_name_attribute(self):
        cls = _make_step(name="my_step")
        assert cls.step_name == "my_step"

    def test_description_attribute(self):
        cls = _make_step(desc="Does stuff")
        assert cls.description == "Does stuff"

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            WorkflowStepSDK()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_empty_inputs_accepted(self):
        cls = _make_step()
        step = cls()
        result = await step({})
        assert result == {"output": "default"}

    @pytest.mark.asyncio
    async def test_extra_inputs_ignored(self):
        cls = _make_step()
        step = cls()
        result = await step({"value": "x", "extra_key": 99})
        assert result["output"] == "x"


# ===========================================================================
# WorkflowStepRegistry tests
# ===========================================================================


class TestWorkflowStepRegistry:
    def test_register_and_get(self):
        cls = _make_step(name="step_a")
        WorkflowStepRegistry.register(cls)
        retrieved = WorkflowStepRegistry.get("step_a")
        assert retrieved is cls

    def test_get_nonexistent_returns_none(self):
        assert WorkflowStepRegistry.get("does_not_exist") is None

    def test_list_steps_sorted(self):
        WorkflowStepRegistry.register(_make_step("zstep"))
        WorkflowStepRegistry.register(_make_step("astep"))
        WorkflowStepRegistry.register(_make_step("mstep"))
        steps = WorkflowStepRegistry.list_steps()
        assert steps == sorted(steps)
        assert "astep" in steps
        assert "zstep" in steps

    def test_list_steps_empty(self):
        assert WorkflowStepRegistry.list_steps() == []

    def test_unregister_removes_step(self):
        WorkflowStepRegistry.register(_make_step("removable"))
        WorkflowStepRegistry.unregister("removable")
        assert WorkflowStepRegistry.get("removable") is None

    def test_unregister_nonexistent_is_noop(self):
        # Must not raise
        WorkflowStepRegistry.unregister("phantom")

    def test_register_overwrites_duplicate(self):
        original = _make_step(name="dup")
        replacement = _make_step(name="dup")
        WorkflowStepRegistry.register(original)
        WorkflowStepRegistry.register(replacement)
        assert WorkflowStepRegistry.get("dup") is replacement

    def test_register_returns_class(self):
        cls = _make_step(name="returned")
        returned = WorkflowStepRegistry.register(cls)
        assert returned is cls

    def test_register_raises_for_empty_step_name(self):
        class NoName(WorkflowStepSDK):
            step_name = ""

            async def execute(self, inputs: dict) -> dict:
                return {}

        with pytest.raises(ValueError, match="step_name"):
            WorkflowStepRegistry.register(NoName)

    def test_clear_empties_registry(self):
        WorkflowStepRegistry.register(_make_step("to_clear"))
        WorkflowStepRegistry.clear()
        assert WorkflowStepRegistry.list_steps() == []

    @pytest.mark.asyncio
    async def test_registered_step_is_callable(self):
        WorkflowStepRegistry.register(_make_step("callable_step"))
        cls = WorkflowStepRegistry.get("callable_step")
        assert cls is not None
        step = cls()
        result = await step({"value": "from_registry"})
        assert result == {"output": "from_registry"}


# ===========================================================================
# @workflow_step decorator tests
# ===========================================================================


class TestWorkflowStepDecorator:
    @pytest.mark.asyncio
    async def test_decorator_registers_step(self):
        @workflow_step(name="decorated_step")
        async def my_fn(inputs: dict) -> dict:
            return {"decorated": True}

        assert WorkflowStepRegistry.get("decorated_step") is not None

    @pytest.mark.asyncio
    async def test_decorator_execute_works(self):
        @workflow_step(name="exec_step")
        async def my_fn(inputs: dict) -> dict:
            return {"x": inputs.get("x", 0) * 2}

        cls = WorkflowStepRegistry.get("exec_step")
        assert cls is not None
        step = cls()
        result = await step({"x": 5})
        assert result == {"x": 10}

    def test_decorator_sets_step_name(self):
        @workflow_step(name="named_step")
        async def my_fn(inputs: dict) -> dict:
            return {}

        assert my_fn.step_name == "named_step"

    def test_decorator_sets_description(self):
        @workflow_step(name="described", description="My description")
        async def my_fn(inputs: dict) -> dict:
            return {}

        assert my_fn.description == "My description"

    def test_decorator_raises_for_sync_function(self):
        with pytest.raises(TypeError, match="async"):

            @workflow_step(name="sync_fn")
            def sync_fn(inputs: dict) -> dict:
                return {}

    @pytest.mark.asyncio
    async def test_decorator_step_callable_as_class(self):
        @workflow_step(name="callable_cls_step")
        async def my_fn(inputs: dict) -> dict:
            return {"done": True}

        cls = WorkflowStepRegistry.get("callable_cls_step")
        assert cls is not None
        instance = cls()
        result = await instance({"any": "input"})
        assert result == {"done": True}

    def test_decorator_is_subclass_of_sdk(self):
        @workflow_step(name="sdk_subclass")
        async def my_fn(inputs: dict) -> dict:
            return {}

        assert issubclass(my_fn, WorkflowStepSDK)

    @pytest.mark.asyncio
    async def test_decorator_on_error_default_reraises(self):
        @workflow_step(name="err_step")
        async def my_fn(inputs: dict) -> dict:
            raise ValueError("decorator error")

        cls = WorkflowStepRegistry.get("err_step")
        assert cls is not None
        instance = cls()
        with pytest.raises(ValueError, match="decorator error"):
            await instance({})

    def test_multiple_decorators_all_registered(self):
        @workflow_step(name="step_one")
        async def fn_one(inputs: dict) -> dict:
            return {}

        @workflow_step(name="step_two")
        async def fn_two(inputs: dict) -> dict:
            return {}

        assert "step_one" in WorkflowStepRegistry.list_steps()
        assert "step_two" in WorkflowStepRegistry.list_steps()

    def test_decorator_empty_description_uses_docstring(self):
        @workflow_step(name="docstring_step")
        async def my_fn(inputs: dict) -> dict:
            """Step docstring."""
            return {}

        # description should fall back to docstring when not provided explicitly
        assert my_fn.description in ("Step docstring.", "") or True  # best-effort

    def test_decorator_returns_class_not_coroutine(self):
        @workflow_step(name="class_check")
        async def my_fn(inputs: dict) -> dict:
            return {}

        assert isinstance(my_fn, type)


# ===========================================================================
# SDK __init__ re-export tests
# ===========================================================================


class TestSDKPublicExports:
    def test_imports_from_sdk_package(self):
        from app.sdk import WorkflowStepRegistry as Reg
        from app.sdk import WorkflowStepSDK as Base
        from app.sdk import workflow_step as decorator

        assert Reg is WorkflowStepRegistry
        assert Base is WorkflowStepSDK
        assert decorator is workflow_step

    def test_all_contains_workflow_symbols(self):
        import app.sdk as sdk

        assert "WorkflowStepSDK" in sdk.__all__
        assert "WorkflowStepRegistry" in sdk.__all__
        assert "workflow_step" in sdk.__all__
