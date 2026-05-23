"""
Unit tests for the CortexFlow Event System.

Coverage:
  - TriggerType enum values
  - TriggerStatus enum values
  - TriggerEvent data class
  - TriggerRegistry CRUD + filtering
  - WebhookTrigger HMAC verification + event building
  - CronTrigger expression validation + event building + Celery schedule
  - DatabaseTrigger channel validation + event building
  - MonitoringTrigger severity routing
  - GitHubTrigger signature + event routing
  - EmailTrigger event building
  - HandlerResult data class
  - WorkflowEventHandler dispatch + audit
  - AgentEventHandler subscriptions + glob matching + notification
  - NotificationEventHandler audit + forwarding
  - EventRouter priority ordering + dispatch + error isolation
"""

from __future__ import annotations

import pytest

from app.core.events.triggers import (
    CronTrigger,
    DatabaseTrigger,
    EmailTrigger,
    GitHubTrigger,
    MonitoringTrigger,
    TriggerEvent,
    TriggerRegistry,
    TriggerStatus,
    TriggerType,
    WebhookTrigger,
)
from app.core.events.handlers import (
    AgentEventHandler,
    EventRouter,
    HandlerResult,
    NotificationEventHandler,
    WorkflowEventHandler,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_event(
    topic: str = "test.topic",
    trigger_type: TriggerType = TriggerType.WEBHOOK,
    payload: dict | None = None,
) -> TriggerEvent:
    return TriggerEvent(
        trigger_id="tid-001",
        trigger_type=trigger_type,
        source="test",
        topic=topic,
        payload=payload or {"key": "value"},
    )


# ===========================================================================
# TriggerType
# ===========================================================================

class TestTriggerType:
    def test_all_values_are_strings(self):
        for t in TriggerType:
            assert isinstance(t.value, str)

    def test_known_types(self):
        types = {t.value for t in TriggerType}
        assert "webhook" in types
        assert "cron" in types
        assert "database" in types
        assert "monitoring" in types
        assert "github" in types
        assert "email" in types


# ===========================================================================
# TriggerStatus
# ===========================================================================

class TestTriggerStatus:
    def test_pending_is_default(self):
        event = _make_event()
        assert event.status == TriggerStatus.PENDING

    def test_status_can_be_updated(self):
        event = _make_event()
        event.status = TriggerStatus.COMPLETED
        assert event.status == TriggerStatus.COMPLETED


# ===========================================================================
# TriggerEvent
# ===========================================================================

class TestTriggerEvent:
    def test_to_dict_contains_all_fields(self):
        event = _make_event()
        d = event.to_dict()
        assert d["trigger_id"] == "tid-001"
        assert d["trigger_type"] == "webhook"
        assert d["source"] == "test"
        assert d["topic"] == "test.topic"
        assert d["status"] == "pending"
        assert "created_at" in d
        assert "payload" in d
        assert "metadata" in d

    def test_metadata_defaults_to_empty(self):
        event = _make_event()
        assert event.metadata == {}


# ===========================================================================
# TriggerRegistry
# ===========================================================================

class TestTriggerRegistry:
    def setup_method(self):
        self.reg = TriggerRegistry()

    def test_register_returns_id(self):
        tid = self.reg.register("my-webhook", TriggerType.WEBHOOK)
        assert isinstance(tid, str) and len(tid) > 0

    def test_count_increases(self):
        assert self.reg.count() == 0
        self.reg.register("t1", TriggerType.WEBHOOK)
        assert self.reg.count() == 1

    def test_get_returns_entry(self):
        tid = self.reg.register("my-cron", TriggerType.CRON, config={"schedule": "* * * * *"})
        entry = self.reg.get(tid)
        assert entry is not None
        assert entry["name"] == "my-cron"
        assert entry["trigger_type"] == "cron"

    def test_get_unknown_returns_none(self):
        assert self.reg.get("nonexistent") is None

    def test_deregister_removes_entry(self):
        tid = self.reg.register("del-me", TriggerType.EMAIL)
        assert self.reg.deregister(tid) is True
        assert self.reg.get(tid) is None

    def test_deregister_nonexistent_returns_false(self):
        assert self.reg.deregister("nope") is False

    def test_enable_disable(self):
        tid = self.reg.register("toggle", TriggerType.WEBHOOK)
        assert self.reg.is_enabled(tid) is True
        assert self.reg.disable(tid) is True
        assert self.reg.is_enabled(tid) is False
        assert self.reg.enable(tid) is True
        assert self.reg.is_enabled(tid) is True

    def test_enable_nonexistent_returns_false(self):
        assert self.reg.enable("ghost") is False

    def test_disable_nonexistent_returns_false(self):
        assert self.reg.disable("ghost") is False

    def test_list_all(self):
        self.reg.register("a", TriggerType.WEBHOOK)
        self.reg.register("b", TriggerType.CRON)
        entries = self.reg.list_all()
        assert len(entries) == 2

    def test_list_by_type(self):
        self.reg.register("a", TriggerType.WEBHOOK)
        self.reg.register("b", TriggerType.CRON)
        self.reg.register("c", TriggerType.WEBHOOK)
        webhook_triggers = self.reg.list_by_type(TriggerType.WEBHOOK)
        assert len(webhook_triggers) == 2
        assert all(t["trigger_type"] == "webhook" for t in webhook_triggers)

    def test_new_trigger_enabled_by_default(self):
        tid = self.reg.register("x", TriggerType.DATABASE)
        assert self.reg.is_enabled(tid) is True


# ===========================================================================
# WebhookTrigger
# ===========================================================================

class TestWebhookTrigger:
    def test_build_event_basic(self):
        wh = WebhookTrigger(source="my-service")
        event = wh.build_event({"data": 1})
        assert event.trigger_type == TriggerType.WEBHOOK
        assert event.source == "my-service"
        assert event.topic == "webhook.received"
        assert event.payload == {"data": 1}

    def test_build_event_custom_topic(self):
        wh = WebhookTrigger()
        event = wh.build_event({}, topic="custom.topic")
        assert event.topic == "custom.topic"

    def test_build_event_metadata(self):
        wh = WebhookTrigger()
        event = wh.build_event({}, metadata={"source_ip": "1.2.3.4"})
        assert event.metadata["source_ip"] == "1.2.3.4"

    def test_verify_signature_no_secret(self):
        wh = WebhookTrigger()
        # No secret → always passes
        assert wh.verify_signature(b"body", "sha256=anything") is True

    def test_verify_signature_valid(self):
        import hashlib
        import hmac as _hmac
        secret = "mysecret"
        body = b'{"event":"ping"}'
        sig = "sha256=" + _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        wh = WebhookTrigger(secret=secret)
        assert wh.verify_signature(body, sig) is True

    def test_verify_signature_invalid(self):
        wh = WebhookTrigger(secret="mysecret")
        assert wh.verify_signature(b"body", "sha256=badsig") is False

    def test_verify_signature_wrong_prefix(self):
        wh = WebhookTrigger(secret="s")
        assert wh.verify_signature(b"body", "md5=abc") is False

    def test_unique_trigger_ids(self):
        wh = WebhookTrigger()
        e1 = wh.build_event({})
        e2 = wh.build_event({})
        assert e1.trigger_id != e2.trigger_id


# ===========================================================================
# CronTrigger
# ===========================================================================

class TestCronTrigger:
    def test_valid_expression(self):
        ct = CronTrigger("daily", "0 0 * * *")
        assert ct.cron_expression == "0 0 * * *"

    def test_invalid_expression_raises(self):
        with pytest.raises(ValueError):
            CronTrigger("bad", "not-a-cron")

    def test_build_event(self):
        ct = CronTrigger("hourly", "0 * * * *")
        event = ct.build_event()
        assert event.trigger_type == TriggerType.CRON
        assert event.topic == "cron.hourly"
        assert event.payload["cron"] == "0 * * * *"

    def test_build_event_metadata(self):
        ct = CronTrigger("t", "* * * * *")
        event = ct.build_event(metadata={"run_id": "r1"})
        assert event.metadata["run_id"] == "r1"

    def test_to_celery_schedule(self):
        ct = CronTrigger("job", "30 6 * * 1")
        schedule = ct.to_celery_schedule()
        assert schedule["schedule"]["minute"] == "30"
        assert schedule["schedule"]["hour"] == "6"
        assert schedule["schedule"]["day_of_week"] == "1"

    def test_complex_expression(self):
        # Every 15 minutes
        ct = CronTrigger("frequent", "*/15 * * * *")
        assert ct.cron_expression == "*/15 * * * *"

    def test_task_name_defaults_to_name(self):
        ct = CronTrigger("my-job", "0 0 * * *")
        assert ct.task_name == "my-job"

    def test_task_name_custom(self):
        ct = CronTrigger("my-job", "0 0 * * *", task_name="custom.task")
        assert ct.task_name == "custom.task"


# ===========================================================================
# DatabaseTrigger
# ===========================================================================

class TestDatabaseTrigger:
    def test_valid_channel(self):
        dt = DatabaseTrigger("agent_updates")
        assert dt.channel == "agent_updates"

    def test_invalid_channel_raises(self):
        with pytest.raises(ValueError):
            DatabaseTrigger("invalid channel!")  # spaces not allowed

    def test_build_event(self):
        dt = DatabaseTrigger("workflow_changes")
        event = dt.build_event('{"action":"insert","row":{"id":1}}')
        assert event.trigger_type == TriggerType.DATABASE
        assert event.topic == "db.workflow_changes"
        assert event.payload["channel"] == "workflow_changes"

    def test_build_event_metadata(self):
        dt = DatabaseTrigger("tasks")
        event = dt.build_event("raw", metadata={"db": "cortexflow"})
        assert event.metadata["db"] == "cortexflow"


# ===========================================================================
# MonitoringTrigger
# ===========================================================================

class TestMonitoringTrigger:
    def setup_method(self):
        self.mt = MonitoringTrigger()

    def test_critical_alert(self):
        payload = {"alerts": [{"labels": {"alertname": "DiskFull", "severity": "critical"}}]}
        event = self.mt.build_event(payload)
        assert event.topic == "monitoring.alert.critical"
        assert event.metadata["severity"] == "critical"

    def test_warning_alert(self):
        payload = {"alerts": [{"labels": {"severity": "warning"}}]}
        event = self.mt.build_event(payload)
        assert event.topic == "monitoring.alert.warning"

    def test_info_alert(self):
        payload = {"alerts": [{"labels": {"severity": "info"}}]}
        event = self.mt.build_event(payload)
        assert event.topic == "monitoring.alert.info"

    def test_unknown_severity(self):
        payload = {"alerts": [{"labels": {"severity": "debug"}}]}
        event = self.mt.build_event(payload)
        assert event.topic == "monitoring.alert.unknown"

    def test_no_alerts_key(self):
        event = self.mt.build_event({})
        assert event.topic == "monitoring.alert.unknown"

    def test_trigger_type(self):
        event = self.mt.build_event({})
        assert event.trigger_type == TriggerType.MONITORING

    def test_metadata_passed_through(self):
        payload = {"alerts": [{"labels": {"severity": "warning"}}]}
        event = self.mt.build_event(payload, metadata={"env": "prod"})
        assert event.metadata["env"] == "prod"
        assert event.metadata["severity"] == "warning"


# ===========================================================================
# GitHubTrigger
# ===========================================================================

class TestGitHubTrigger:
    def setup_method(self):
        self.gh = GitHubTrigger()

    def test_push_event(self):
        event = self.gh.build_event("push", {"ref": "refs/heads/main"})
        assert event.topic == "github.push"
        assert event.trigger_type == TriggerType.GITHUB

    def test_pull_request_event(self):
        event = self.gh.build_event("pull_request", {"action": "opened"})
        assert event.topic == "github.pull_request"

    def test_unknown_event_type(self):
        event = self.gh.build_event("star", {})
        assert event.topic == "github.unknown"

    def test_metadata_github_event(self):
        event = self.gh.build_event("push", {})
        assert event.metadata["github_event"] == "push"

    def test_signature_verification_no_secret(self):
        gh = GitHubTrigger()
        assert gh.verify_signature(b"body", "sha256=anything") is True

    def test_signature_verification_with_secret(self):
        import hashlib
        import hmac as _hmac
        secret = "gh-secret"
        body = b'{"zen":"test"}'
        sig = "sha256=" + _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        gh = GitHubTrigger(secret=secret)
        assert gh.verify_signature(body, sig) is True

    def test_signature_verification_invalid(self):
        gh = GitHubTrigger(secret="s")
        assert gh.verify_signature(b"body", "sha256=bad") is False

    def test_ping_event(self):
        event = self.gh.build_event("ping", {"zen": "Practicality beats purity."})
        assert event.topic == "github.ping"


# ===========================================================================
# EmailTrigger
# ===========================================================================

class TestEmailTrigger:
    def setup_method(self):
        self.et = EmailTrigger(mailbox="inbox")

    def test_build_event(self):
        event = self.et.build_event("alice@example.com", "Hello!")
        assert event.trigger_type == TriggerType.EMAIL
        assert event.topic == "email.received"
        assert event.payload["sender"] == "alice@example.com"
        assert event.payload["subject"] == "Hello!"

    def test_body_preview_truncated(self):
        long_body = "x" * 600
        event = self.et.build_event("a@b.com", "subj", body_preview=long_body)
        assert len(event.payload["body_preview"]) == 500

    def test_source_includes_mailbox(self):
        event = self.et.build_event("a@b.com", "s")
        assert event.source == "email.inbox"

    def test_custom_mailbox(self):
        et = EmailTrigger(mailbox="alerts")
        event = et.build_event("sys@corp.com", "Alert")
        assert event.source == "email.alerts"

    def test_metadata_passed_through(self):
        event = self.et.build_event("a@b.com", "s", metadata={"uid": 42})
        assert event.metadata["uid"] == 42


# ===========================================================================
# HandlerResult
# ===========================================================================

class TestHandlerResult:
    def test_to_dict(self):
        r = HandlerResult(
            handler_name="TestHandler",
            event_id="e-001",
            success=True,
            message="ok",
        )
        d = r.to_dict()
        assert d["handler_name"] == "TestHandler"
        assert d["success"] is True
        assert "processed_at" in d


# ===========================================================================
# WorkflowEventHandler
# ===========================================================================

class TestWorkflowEventHandler:
    def setup_method(self):
        self.handler = WorkflowEventHandler()

    @pytest.mark.asyncio
    async def test_handle_returns_success(self):
        event = _make_event()
        result = await self.handler.handle(event)
        assert result.success is True
        assert "execution_id" in result.data

    @pytest.mark.asyncio
    async def test_handle_logs_dispatch(self):
        event = _make_event()
        await self.handler.handle(event)
        dispatched = self.handler.dispatched()
        assert len(dispatched) == 1
        assert dispatched[0]["topic"] == event.topic

    @pytest.mark.asyncio
    async def test_handle_updates_status(self):
        event = _make_event()
        await self.handler.handle(event)
        assert event.status == TriggerStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_handle_multiple_events(self):
        for _ in range(5):
            await self.handler.handle(_make_event())
        assert len(self.handler.dispatched()) == 5

    def test_clear(self):
        self.handler._dispatch_log.append({"x": 1})
        self.handler.clear()
        assert self.handler.dispatched() == []

    @pytest.mark.asyncio
    async def test_unique_execution_ids(self):
        e1 = _make_event("t1")
        e2 = _make_event("t2")
        r1 = await self.handler.handle(e1)
        r2 = await self.handler.handle(e2)
        assert r1.data["execution_id"] != r2.data["execution_id"]


# ===========================================================================
# AgentEventHandler
# ===========================================================================

class TestAgentEventHandler:
    def setup_method(self):
        self.handler = AgentEventHandler()

    def test_subscribe_and_subscribed_agents(self):
        self.handler.subscribe("agent-1", "github.*")
        agents = self.handler.subscribed_agents("github.push")
        assert "agent-1" in agents

    def test_glob_pattern_matching(self):
        self.handler.subscribe("agent-2", "monitoring.alert.*")
        assert "agent-2" in self.handler.subscribed_agents("monitoring.alert.critical")
        assert "agent-2" not in self.handler.subscribed_agents("github.push")

    def test_wildcard_matches_all(self):
        self.handler.subscribe("agent-3", "*")
        assert "agent-3" in self.handler.subscribed_agents("anything.at.all")

    def test_no_duplicate_subscriptions(self):
        self.handler.subscribe("agent-1", "topic.x")
        self.handler.subscribe("agent-1", "topic.x")
        agents = self.handler.subscribed_agents("topic.x")
        assert agents.count("agent-1") == 1

    def test_unsubscribe_removes_agent(self):
        self.handler.subscribe("agent-4", "db.*")
        assert self.handler.unsubscribe("agent-4", "db.*") is True
        assert "agent-4" not in self.handler.subscribed_agents("db.changes")

    def test_unsubscribe_nonexistent_returns_false(self):
        assert self.handler.unsubscribe("ghost", "nope") is False

    @pytest.mark.asyncio
    async def test_handle_notifies_subscribed_agents(self):
        self.handler.subscribe("agent-A", "test.*")
        self.handler.subscribe("agent-B", "test.*")
        event = _make_event("test.topic")
        result = await self.handler.handle(event)
        assert result.data["count"] == 2
        assert "agent-A" in result.data["agent_ids"]

    @pytest.mark.asyncio
    async def test_handle_no_subscribers(self):
        event = _make_event("unsubscribed.topic")
        result = await self.handler.handle(event)
        assert result.success is True
        assert result.data["count"] == 0

    def test_clear(self):
        self.handler._notifications.append({"x": 1})
        self.handler.clear()
        assert self.handler.notifications() == []


# ===========================================================================
# NotificationEventHandler
# ===========================================================================

class TestNotificationEventHandler:
    def setup_method(self):
        self.handler = NotificationEventHandler(webhook_url="https://ops.example.com/alerts")

    @pytest.mark.asyncio
    async def test_handle_logs_to_audit(self):
        event = _make_event()
        await self.handler.handle(event)
        assert len(self.handler.audit_log()) == 1
        assert self.handler.audit_log()[0]["topic"] == "test.topic"

    @pytest.mark.asyncio
    async def test_critical_alert_forwarded(self):
        event = _make_event(topic="monitoring.alert.critical", trigger_type=TriggerType.MONITORING)
        result = await self.handler.handle(event)
        assert result.data["forwarded"] is True
        assert len(self.handler.forwarded()) == 1

    @pytest.mark.asyncio
    async def test_non_critical_not_forwarded(self):
        event = _make_event(topic="github.push")
        result = await self.handler.handle(event)
        assert result.data["forwarded"] is False
        assert len(self.handler.forwarded()) == 0

    @pytest.mark.asyncio
    async def test_warning_forwarded(self):
        event = _make_event(topic="monitoring.alert.warning")
        await self.handler.handle(event)
        assert len(self.handler.forwarded()) == 1

    @pytest.mark.asyncio
    async def test_no_webhook_url_no_forward(self):
        handler = NotificationEventHandler(webhook_url=None)
        event = _make_event(topic="monitoring.alert.critical")
        result = await handler.handle(event)
        assert result.data["forwarded"] is False

    def test_clear(self):
        self.handler._audit.append({"x": 1})
        self.handler._forwarded.append({"y": 2})
        self.handler.clear()
        assert self.handler.audit_log() == []
        assert self.handler.forwarded() == []

    @pytest.mark.asyncio
    async def test_handle_returns_success(self):
        event = _make_event()
        result = await self.handler.handle(event)
        assert result.success is True


# ===========================================================================
# EventRouter
# ===========================================================================

class TestEventRouter:
    def setup_method(self):
        self.router = EventRouter()

    def test_register_increases_count(self):
        self.router.register("*", NotificationEventHandler())
        assert self.router.registered_count() == 1

    def test_matching_handlers_exact_topic(self):
        handler = NotificationEventHandler()
        self.router.register("github.push", handler)
        matches = self.router.matching_handlers("github.push")
        assert handler in matches

    def test_matching_handlers_glob(self):
        handler = NotificationEventHandler()
        self.router.register("github.*", handler)
        assert handler in self.router.matching_handlers("github.push")
        assert handler not in self.router.matching_handlers("monitoring.alert.critical")

    def test_no_match_returns_empty(self):
        self.router.register("github.*", NotificationEventHandler())
        assert self.router.matching_handlers("email.received") == []

    def test_priority_ordering(self):
        names: list[str] = []

        class NamedHandler:
            def __init__(self, n: str):
                self.name = n
            async def handle(self, event: TriggerEvent) -> HandlerResult:
                names.append(self.name)
                return HandlerResult(handler_name=self.name, event_id=event.trigger_id, success=True)

        low = NamedHandler("low")
        high = NamedHandler("high")
        self.router.register("*", low, priority=0)
        self.router.register("*", high, priority=10)
        handlers = self.router.matching_handlers("any.topic")
        assert handlers[0] is high
        assert handlers[1] is low

    @pytest.mark.asyncio
    async def test_dispatch_calls_all_matching_handlers(self):
        wh = WorkflowEventHandler()
        ah = AgentEventHandler()
        self.router.register("*", wh)
        self.router.register("*", ah)
        event = _make_event()
        results = await self.router.dispatch(event)
        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_dispatch_isolates_handler_errors(self):
        class BrokenHandler:
            name = "BrokenHandler"
            async def handle(self, event: TriggerEvent) -> HandlerResult:
                raise RuntimeError("boom")

        good = WorkflowEventHandler()
        self.router.register("*", BrokenHandler(), priority=10)
        self.router.register("*", good, priority=0)
        results = await self.router.dispatch(_make_event())
        assert len(results) == 2
        failed = next(r for r in results if not r.success)
        assert "RuntimeError" in failed.message
        succeeded = next(r for r in results if r.success)
        assert succeeded.success is True

    @pytest.mark.asyncio
    async def test_dispatch_no_handlers_returns_empty(self):
        results = await self.router.dispatch(_make_event())
        assert results == []

    @pytest.mark.asyncio
    async def test_dispatch_workflow_handler_stores_execution(self):
        wh = WorkflowEventHandler()
        self.router.register("*", wh)
        event = _make_event("test.fire")
        await self.router.dispatch(event)
        assert len(wh.dispatched()) == 1
