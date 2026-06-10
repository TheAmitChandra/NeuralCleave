"""Unit tests for cortexflow.channels.email_ — EmailAdapter."""

from __future__ import annotations

import email
import email.policy
from unittest.mock import AsyncMock, MagicMock, patch

from cortexflow.channels.email_ import EmailAdapter, _extract_address, _mime_to_type


def make_adapter(**overrides) -> EmailAdapter:
    cfg = {
        "username": "bot@example.com",
        "password": "secret",
        "imap_host": "imap.example.com",
        "smtp_host": "smtp.example.com",
        **overrides,
    }
    return EmailAdapter(cfg)


def _make_email(
    from_: str = "alice@test.com",
    subject: str = "Test Subject",
    body: str = "Hello email body.",
) -> email.message.Message:
    raw = (
        f"From: {from_}\r\n"
        f"Subject: {subject}\r\n"
        f"Message-ID: <msg-001@test.com>\r\n"
        f"\r\n"
        f"{body}"
    )
    return email.message_from_string(raw, policy=email.policy.default)


# ---------------------------------------------------------------------------
# Construction & _resolve
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "email"
    assert adapter._imap_host == "imap.example.com"
    assert adapter._smtp_host == "smtp.example.com"
    assert adapter._poll_interval == 60
    assert adapter._task is None


def test_construction_default_ports():
    adapter = make_adapter()
    assert adapter._imap_port == 993
    assert adapter._smtp_port == 587


def test_construction_default_mailbox():
    adapter = make_adapter()
    assert adapter._mailbox == "INBOX"


def test_resolve_env_var(monkeypatch):
    monkeypatch.setenv("EMAIL_USER_TEST", "env-user@test.com")
    adapter = EmailAdapter({"username": "ENV:EMAIL_USER_TEST", "password": "pw"})
    assert adapter._username == "env-user@test.com"


def test_resolve_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("EMAIL_NO_SUCH", raising=False)
    adapter = EmailAdapter({"username": "ENV:EMAIL_NO_SUCH", "password": "pw"})
    assert adapter._username == ""


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    assert "username" in schema["required"]
    assert "password" in schema["required"]


def test_config_schema_has_imap_smtp_properties():
    schema = make_adapter().get_config_schema()
    assert "imap_host" in schema["properties"]
    assert "smtp_host" in schema["properties"]
    assert "poll_interval" in schema["properties"]


# ---------------------------------------------------------------------------
# _extract_address
# ---------------------------------------------------------------------------


def test_extract_address_angle_brackets():
    assert _extract_address("Alice <alice@test.com>") == "alice@test.com"


def test_extract_address_plain():
    assert _extract_address("alice@test.com") == "alice@test.com"


def test_extract_address_strips_whitespace():
    assert _extract_address("  bob@test.com  ") == "bob@test.com"


# ---------------------------------------------------------------------------
# _mime_to_type
# ---------------------------------------------------------------------------


def test_mime_to_type_image():
    assert _mime_to_type("image/png") == "image"


def test_mime_to_type_audio():
    assert _mime_to_type("audio/mpeg") == "audio"


def test_mime_to_type_video():
    assert _mime_to_type("video/mp4") == "video"


def test_mime_to_type_document():
    assert _mime_to_type("application/pdf") == "document"


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


def _mock_aiosmtplib() -> tuple[MagicMock, MagicMock]:
    """Return (mock_module, mock_send) and inject the module into sys.modules."""
    mock_send = AsyncMock()
    mock_module = MagicMock()
    mock_module.send = mock_send
    return mock_module, mock_send


async def test_send_success():
    adapter = make_adapter()
    mock_mod, mock_send = _mock_aiosmtplib()
    with patch.dict("sys.modules", {"aiosmtplib": mock_mod}):
        result = await adapter.send("dest@example.com", "Hello email!")
    assert result is None  # SMTP doesn't return a message ID
    mock_send.assert_called_once()


async def test_send_with_reply_to_sets_headers():
    adapter = make_adapter()
    mock_mod, mock_send = _mock_aiosmtplib()
    with patch.dict("sys.modules", {"aiosmtplib": mock_mod}):
        await adapter.send("dest@example.com", "Reply body", reply_to="<orig@test.com>")
    sent_msg = mock_send.call_args[0][0]
    assert sent_msg["In-Reply-To"] == "<orig@test.com>"
    assert sent_msg["References"] == "<orig@test.com>"


async def test_send_no_reply_to_uses_default_subject():
    adapter = make_adapter()
    mock_mod, mock_send = _mock_aiosmtplib()
    with patch.dict("sys.modules", {"aiosmtplib": mock_mod}):
        await adapter.send("dest@example.com", "Hello")
    sent_msg = mock_send.call_args[0][0]
    assert sent_msg["Subject"] == "CortexFlow"


async def test_send_with_reply_uses_re_subject():
    adapter = make_adapter()
    mock_mod, mock_send = _mock_aiosmtplib()
    with patch.dict("sys.modules", {"aiosmtplib": mock_mod}):
        await adapter.send("dest@example.com", "Hello", reply_to="<orig@test.com>")
    sent_msg = mock_send.call_args[0][0]
    assert "Re:" in sent_msg["Subject"]


# ---------------------------------------------------------------------------
# _dispatch_email
# ---------------------------------------------------------------------------


async def test_dispatch_email_simple_text():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    parsed = _make_email(from_="alice@test.com", subject="Hi", body="Hello from Alice")
    await adapter._dispatch_email(parsed)

    assert len(dispatched) == 1
    assert dispatched[0].sender_id == "alice@test.com"
    assert "Hello from Alice" in dispatched[0].text
    assert dispatched[0].channel == "email"


async def test_dispatch_email_subject_included_in_text():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    parsed = _make_email(subject="Important question", body="Please answer")
    await adapter._dispatch_email(parsed)

    assert "Important question" in dispatched[0].text
    assert "Please answer" in dispatched[0].text


async def test_dispatch_email_reply_to_id():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    raw = (
        "From: bob@test.com\r\n"
        "Subject: Re: Something\r\n"
        "Message-ID: <reply-001@test.com>\r\n"
        "In-Reply-To: <orig-001@test.com>\r\n"
        "\r\nThis is a reply."
    )
    parsed = email.message_from_string(raw, policy=email.policy.default)
    await adapter._dispatch_email(parsed)

    assert dispatched[0].reply_to_id == "<orig-001@test.com>"


async def test_dispatch_email_no_handler_is_safe():
    adapter = make_adapter()
    # No handler registered — should not raise
    parsed = _make_email()
    await adapter._dispatch_email(parsed)
