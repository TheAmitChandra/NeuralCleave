"""Import all models so Alembic and SQLAlchemy can discover them."""

from app.db.postgres import Base  # noqa: F401
from app.db.models.user import User  # noqa: F401
from app.db.models.agent import Agent  # noqa: F401
from app.db.models.workflow import Workflow  # noqa: F401
from app.db.models.task import Task  # noqa: F401
from app.db.models.tool_call import ToolCall  # noqa: F401
from app.db.models.audit import AuditLog  # noqa: F401
from app.db.models.memory import MemoryEntry  # noqa: F401

__all__ = [
    "Base",
    "User",
    "Agent",
    "Workflow",
    "Task",
    "ToolCall",
    "AuditLog",
    "MemoryEntry",
]
