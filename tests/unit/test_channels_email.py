"""Unit tests for NeuralCleave.channels.email_ — EmailAdapter."""

from __future__ import annotations

import asyncio
import email
import email.policy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.email_ import EmailAdapter, _extract_address, _mime_to_type


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
    assert sent_msg["Subject"] == "NeuralCleave"


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


async def test_dispatch_email_multipart_with_attachment():
    from email.message import EmailMessage as RealEmailMessage

    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    msg = RealEmailMessage()
    msg["From"] = "alice@test.com"
    msg["Subject"] = "With attachment"
    msg["Message-ID"] = "<m3@test.com>"
    msg.set_content("Body text here")
    msg.add_attachment(b"PDF-DATA", maintype="application", subtype="pdf", filename="doc.pdf")

    await adapter._dispatch_email(msg)

    assert len(dispatched) == 1
    assert len(dispatched[0].attachments) == 1
    assert dispatched[0].attachments[0].filename == "doc.pdf"
    assert dispatched[0].attachments[0].type == "document"
    assert "Body text here" in dispatched[0].text


# ---------------------------------------------------------------------------
# send — error paths
# ---------------------------------------------------------------------------


async def test_send_returns_none_if_aiosmtplib_not_installed():
    """Regression: send() must return None when aiosmtplib is missing, not raise."""
    adapter = make_adapter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "aiosmtplib":
            raise ImportError("No module named 'aiosmtplib'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        result = await adapter.send("dest@example.com", "hi")

    assert result is None


async def test_send_smtp_error_returns_none():
    """Regression: send() must return None on SMTP errors, not propagate the exception."""
    adapter = make_adapter()
    mock_mod, mock_send = _mock_aiosmtplib()
    mock_send.side_effect = Exception("SMTP auth failed")

    with patch.dict("sys.modules", {"aiosmtplib": mock_mod}):
        result = await adapter.send("dest@example.com", "hi")

    assert result is None


# ---------------------------------------------------------------------------
# connect() / disconnect()
# ---------------------------------------------------------------------------


async def test_connect_raises_if_no_credentials():
    adapter = EmailAdapter({})
    with pytest.raises(RuntimeError, match="username/password"):
        await adapter.connect()


async def test_connect_success_starts_poll_task(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_imap_check", AsyncMock())
    monkeypatch.setattr(adapter, "_poll_loop", AsyncMock())

    await adapter.connect()

    assert adapter._task is not None
    await adapter.disconnect()


async def test_disconnect_with_no_task_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()  # should not raise


async def test_disconnect_cancels_poll_task():
    adapter = make_adapter()

    async def _never_ending():
        await asyncio.sleep(100)

    adapter._task = asyncio.create_task(_never_ending())

    await adapter.disconnect()

    assert adapter._task is None


# ---------------------------------------------------------------------------
# _poll_loop
# ---------------------------------------------------------------------------


async def test_poll_loop_reraises_cancelled_error(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_imap_check", AsyncMock(side_effect=asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await adapter._poll_loop()


async def test_poll_loop_continues_after_generic_exception(monkeypatch):
    adapter = make_adapter()
    call_count = {"n": 0}

    async def fake_imap_check():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("imap down")
        raise asyncio.CancelledError()

    monkeypatch.setattr(adapter, "_imap_check", fake_imap_check)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    with pytest.raises(asyncio.CancelledError):
        await adapter._poll_loop()

    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# _imap_check
# ---------------------------------------------------------------------------


def _mock_imap_client(**overrides) -> MagicMock:
    client = MagicMock()
    client.wait_hello_from_server = AsyncMock()
    client.login = AsyncMock()
    client.select = AsyncMock()
    client.search = AsyncMock(return_value=(None, [b""]))
    client.fetch = AsyncMock()
    client.logout = AsyncMock()
    for key, value in overrides.items():
        setattr(client, key, value)
    return client


def _mock_aioimaplib_module(client: MagicMock) -> MagicMock:
    mock_module = MagicMock()
    mock_module.IMAP4_SSL = MagicMock(return_value=client)
    return mock_module


async def test_imap_check_raises_if_aioimaplib_not_installed():
    adapter = make_adapter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "aioimaplib":
            raise ImportError("No module named 'aioimaplib'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="pip install aioimaplib"):
            await adapter._imap_check()


async def test_imap_check_no_unseen_messages_logs_out():
    adapter = make_adapter()
    client = _mock_imap_client(search=AsyncMock(return_value=(None, [b""])))

    with patch.dict("sys.modules", {"aioimaplib": _mock_aioimaplib_module(client)}):
        await adapter._imap_check()

    client.logout.assert_called_once()


async def test_imap_check_dispatches_new_messages():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    raw_email = (
        b"From: alice@test.com\r\n"
        b"Subject: Hi\r\n"
        b"Message-ID: <m1@test.com>\r\n"
        b"\r\nHello there"
    )
    client = _mock_imap_client(
        search=AsyncMock(return_value=(None, [b"1"])),
        fetch=AsyncMock(return_value=(None, [None, raw_email])),
    )

    with patch.dict("sys.modules", {"aioimaplib": _mock_aioimaplib_module(client)}):
        await adapter._imap_check()

    assert len(dispatched) == 1
    client.logout.assert_called_once()


async def test_imap_check_logout_called_even_on_search_error():
    """Regression: logout must be called even if search() raises to avoid IMAP connection leak."""
    adapter = make_adapter()
    client = _mock_imap_client(
        search=AsyncMock(side_effect=RuntimeError("IMAP search failed"))
    )

    with patch.dict("sys.modules", {"aioimaplib": _mock_aioimaplib_module(client)}):
        with pytest.raises(RuntimeError, match="IMAP search failed"):
            await adapter._imap_check()

    client.logout.assert_called_once()


async def test_imap_check_fetch_error_for_one_uid_does_not_stop_others():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    raw_email = b"From: bob@test.com\r\nSubject: Hi\r\nMessage-ID: <m2@test.com>\r\n\r\nBody"

    async def fake_fetch(uid, spec):
        if uid == "1":
            raise RuntimeError("fetch failed")
        return (None, [None, raw_email])

    client = _mock_imap_client(
        search=AsyncMock(return_value=(None, [b"1 2"])),
        fetch=fake_fetch,
    )

    with patch.dict("sys.modules", {"aioimaplib": _mock_aioimaplib_module(client)}):
        await adapter._imap_check()

    assert len(dispatched) == 1
