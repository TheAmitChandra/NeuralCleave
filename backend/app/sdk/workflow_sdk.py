"""Workflow Step SDK — NeuralCleave plugin interface for custom workflow steps.

Custom workflow steps let integrators inject their own logic into the
NeuralCleave workflow engine without touching internal implementation details.

Public API
──────────
  WorkflowStepSDK        Abstract base class for a custom workflow step
  WorkflowStepRegistry   Singleton registry — maps step names to implementations
  workflow_step          Decorator for registering a function as a workflow step

Quick start::

    from app.sdk.workflow_sdk import workflow_step

    @workflow_step(
        name="send_slack_notification",
        description="Send a Slack message when a workflow node completes.",
    )
    async def send_slack(inputs: dict) -> dict:
        webhook = inputs["webhook_url"]
        message = inputs["message"]
        # ... call Slack webhook
        return {"sent": True}

Or using the class API::

    from app.sdk.workflow_sdk import WorkflowStepSDK, WorkflowStepRegistry

    class MyStep(WorkflowStepSDK):
        step_name = "my_custom_step"
        description = "Does something custom in a workflow."

        async def execute(self, inputs: dict) -> dict:
            return {"result": inputs.get("value", "") + "_processed"}

        async def on_error(self, exc: Exception) -> dict:
            return {"error": str(exc), "recovered": False}

    WorkflowStepRegistry.register(MyStep)
"""

from __future__ import annotations

import abc
import inspect
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class WorkflowStepSDK(abc.ABC):
    """Abstract base class for a custom NeuralCleave workflow step.

    Sub-class this, set :attr:`step_name` and :attr:`description`, then
    implement :meth:`execute`.  Optionally override :meth:`on_error` to
    provide recovery logic instead of propagating the exception.
    """

    #: Unique identifier used to reference this step inside DAG definitions.
    #: Must be set on every concrete subclass.
    step_name: str = ""

    #: Human-readable description shown in the UI and API.
    description: str = ""

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Run the step logic.

        Parameters
        ----------
        inputs:
            Key/value pairs supplied by the workflow engine — typically the
            merged outputs of upstream nodes plus any static ``parameters``
            defined in the DAG.

        Returns
        -------
        A dict of outputs that will be forwarded to downstream nodes.
        """

    async def on_error(self, exc: Exception) -> dict[str, Any]:
        """Optional error hook — called when :meth:`execute` raises.

        The default implementation re-raises the exception.  Override to
        return a recovery payload instead (e.g. a safe default result).

        Parameters
        ----------
        exc:
            The exception raised by :meth:`execute`.
        """
        raise exc

    # ------------------------------------------------------------------
    # Internal — called by the scheduler
    # ------------------------------------------------------------------

    async def __call__(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Entry point used by the workflow scheduler."""
        try:
            result = await self.execute(inputs)
            logger.info(
                "workflow_step.completed",
                step_name=self.step_name,
                output_keys=list(result.keys()) if isinstance(result, dict) else [],
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "workflow_step.error",
                step_name=self.step_name,
                error=str(exc),
            )
            return await self.on_error(exc)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class WorkflowStepRegistry:
    """Singleton registry mapping step names to :class:`WorkflowStepSDK` classes.

    Usage::

        WorkflowStepRegistry.register(MyStep)
        cls = WorkflowStepRegistry.get("my_custom_step")
        step = cls()
        result = await step(inputs)
    """

    _registry: dict[str, type[WorkflowStepSDK]] = {}

    @classmethod
    def register(cls, step_class: type[WorkflowStepSDK]) -> type[WorkflowStepSDK]:
        """Register a :class:`WorkflowStepSDK` subclass.

        Parameters
        ----------
        step_class:
            Concrete subclass to register.  Must have a non-empty
            :attr:`~WorkflowStepSDK.step_name`.

        Returns the class unchanged (allows use as a class decorator).
        """
        if not step_class.step_name:
            raise ValueError(
                f"WorkflowStepSDK subclass {step_class.__name__!r} must define step_name."
            )
        if step_class.step_name in cls._registry:
            logger.warning(
                "workflow_step_registry.overwrite",
                step_name=step_class.step_name,
                old=cls._registry[step_class.step_name].__name__,
                new=step_class.__name__,
            )
        cls._registry[step_class.step_name] = step_class
        logger.info("workflow_step_registry.registered", step_name=step_class.step_name)
        return step_class

    @classmethod
    def unregister(cls, step_name: str) -> None:
        """Remove a step from the registry."""
        cls._registry.pop(step_name, None)

    @classmethod
    def get(cls, step_name: str) -> type[WorkflowStepSDK] | None:
        """Return the step class for ``step_name``, or ``None`` if not found."""
        return cls._registry.get(step_name)

    @classmethod
    def list_steps(cls) -> list[str]:
        """Return a sorted list of all registered step names."""
        return sorted(cls._registry.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations — useful for test teardown."""
        cls._registry.clear()


# ---------------------------------------------------------------------------
# @workflow_step decorator
# ---------------------------------------------------------------------------


def workflow_step(
    name: str,
    description: str = "",
) -> Callable[[Callable[..., Any]], type[WorkflowStepSDK]]:
    """Decorator that promotes a plain async function into a registered workflow step.

    The decorated function becomes the ``execute`` method of a dynamically
    created :class:`WorkflowStepSDK` subclass, which is automatically
    registered in :class:`WorkflowStepRegistry`.

    Parameters
    ----------
    name:
        Step name (unique identifier in DAG definitions).
    description:
        Human-readable description shown in the UI.

    Example::

        @workflow_step(name="call_external_api", description="Calls an external REST API.")
        async def call_api(inputs: dict) -> dict:
            resp = await httpx.AsyncClient().get(inputs["url"])
            return {"status": resp.status_code, "body": resp.text}

    After decoration, ``call_api`` is replaced by the auto-generated subclass.
    """

    def decorator(fn: Callable[..., Any]) -> type[WorkflowStepSDK]:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(
                f"@workflow_step requires an async function; {fn.__name__!r} is synchronous."
            )

        # Dynamically build a WorkflowStepSDK subclass
        step_cls = type(
            fn.__name__,
            (WorkflowStepSDK,),
            {
                "step_name": name,
                "description": description or fn.__doc__ or "",
                "execute": staticmethod(fn),
                "__module__": fn.__module__,
                "__qualname__": fn.__qualname__,
                "__doc__": fn.__doc__,
            },
        )

        WorkflowStepRegistry.register(step_cls)
        logger.info("workflow_step.decorated", step_name=name, fn=fn.__name__)

        return step_cls

    return decorator
