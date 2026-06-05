"""Events API — webhook ingestion and trigger management.

Provides:
  POST /events/webhook/{source}       — receive inbound webhooks from external services
  POST /events/webhook/github         — GitHub-specific webhook with HMAC verification
  POST /events/webhook/alertmanager   — Prometheus Alertmanager webhook
  GET  /events/triggers               — list registered triggers
  POST /events/triggers               — register a new trigger
  DELETE /events/triggers/{trigger_id}— deregister a trigger
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from app.schemas.events import (
    EventDispatchResponse,
    TriggerRegistration,
    TriggerResponse,
    WebhookPayload,
)

from app.core.events.handlers import EventRouter, NotificationEventHandler, WorkflowEventHandler
from app.core.events.triggers import (
    GitHubTrigger,
    MonitoringTrigger,
    TriggerEvent,
    TriggerRegistry,
    TriggerType,
    WebhookTrigger,
)
from app.core.security.permission_engine import get_current_user
from app.config import get_settings
from app.db.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/events")
settings = get_settings()

# ---------------------------------------------------------------------------
# Process-level singletons
# ---------------------------------------------------------------------------

_trigger_registry = TriggerRegistry()
_event_router = EventRouter()

# Wire default handlers (lowest priority = notification catch-all)
_wf_handler = WorkflowEventHandler()
_notify_handler = NotificationEventHandler()
_event_router.register("*", _wf_handler, priority=10)
_event_router.register("*", _notify_handler, priority=0)

# Default trigger registrations
_trigger_registry.register("default-webhook", TriggerType.WEBHOOK, config={"source": "generic"})





# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dispatch_summary(event: TriggerEvent, results: list) -> dict:
    successes = sum(1 for r in results if r.success)
    return {
        "trigger_id": event.trigger_id,
        "topic": event.topic,
        "dispatched_to": successes,
        "message": f"Event dispatched to {successes} handler(s)",
    }


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------

@router.post("/webhook/{source}", response_model=EventDispatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    source: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generic webhook receiver — any authenticated source."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}

    trigger = WebhookTrigger(source=source)
    event = trigger.build_event(
        payload=payload if isinstance(payload, dict) else {"raw": payload},
        topic=f"webhook.{source}",
    )
    logger.info("webhook_received", source=source, trigger_id=event.trigger_id)
    results = await _event_router.dispatch(event)
    return _dispatch_summary(event, results)


@router.post("/webhook/github", response_model=EventDispatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def receive_github_webhook(
    request: Request,
    x_github_event: str = Header(default="unknown"),
    x_hub_signature_256: str = Header(default=""),
    current_user: User = Depends(get_current_user),
) -> dict:
    """GitHub webhook endpoint with HMAC-SHA256 signature verification."""
    body = await request.body()

    gh_secret = settings.GITHUB_WEBHOOK_SECRET or None
    gh_trigger = GitHubTrigger(secret=gh_secret)

    if gh_secret and not gh_trigger.verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub webhook signature")

    try:
        import json  # noqa: PLC0415
        payload = json.loads(body)
    except Exception:  # noqa: BLE001
        payload = {}

    event = gh_trigger.build_event(event_type=x_github_event, payload=payload)
    logger.info("github_webhook_received", event_type=x_github_event, trigger_id=event.trigger_id)
    results = await _event_router.dispatch(event)
    return _dispatch_summary(event, results)


@router.post("/webhook/alertmanager", response_model=EventDispatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def receive_alertmanager_webhook(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Prometheus Alertmanager webhook endpoint."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}

    mt = MonitoringTrigger()
    event = mt.build_event(payload if isinstance(payload, dict) else {})
    logger.info("alertmanager_webhook_received", topic=event.topic, trigger_id=event.trigger_id)
    results = await _event_router.dispatch(event)
    return _dispatch_summary(event, results)


# ---------------------------------------------------------------------------
# Trigger management endpoints
# ---------------------------------------------------------------------------

@router.get("/triggers", response_model=list[TriggerResponse])
async def list_triggers(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List all registered event triggers."""
    return [
        {
            "trigger_id": t["trigger_id"],
            "name": t["name"],
            "trigger_type": t["trigger_type"],
            "enabled": t["enabled"],
            "config": t["config"],
        }
        for t in _trigger_registry.list_all()
    ]


@router.post("/triggers", response_model=TriggerResponse, status_code=status.HTTP_201_CREATED)
async def register_trigger(
    body: TriggerRegistration,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Register a new event trigger."""
    trigger_id = _trigger_registry.register(
        name=body.name,
        trigger_type=TriggerType(body.trigger_type),
        config=body.config,
    )
    entry = _trigger_registry.get(trigger_id)
    logger.info("trigger_registered", trigger_id=trigger_id, name=body.name)
    return {
        "trigger_id": trigger_id,
        "name": body.name,
        "trigger_type": body.trigger_type,
        "enabled": True,
        "config": body.config,
    }


@router.delete("/triggers/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def deregister_trigger(
    trigger_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Deregister an event trigger."""
    removed = _trigger_registry.deregister(trigger_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
    logger.info("trigger_deregistered", trigger_id=trigger_id)
