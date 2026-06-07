"""Pydantic schemas for Events endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WebhookPayload(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class TriggerRegistration(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    trigger_type: str = Field(..., pattern=r"^(webhook|cron|database|monitoring|github|email)$")
    config: dict[str, Any] = Field(default_factory=dict)


class TriggerResponse(BaseModel):
    trigger_id: str
    name: str
    trigger_type: str
    enabled: bool
    config: dict[str, Any]


class EventDispatchResponse(BaseModel):
    trigger_id: str
    topic: str
    dispatched_to: int
    message: str
