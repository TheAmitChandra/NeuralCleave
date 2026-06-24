"""Unit tests for cortexflow.voice.tts — TTSEngine."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.voice.tts import TTSEngine

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_default_voice_id():
    t = TTSEngine()
    assert t._el_voice == TTSEngine.DEFAULT_ELEVENLABS_VOICE


def test_prefer_local_default_false():
    t = TTSEngine()
    assert t._prefer_local is False


def test_prefer_local_true():
    t = TTSEngine(prefer_local=True)
    assert t._prefer_local is True


def test_custom_elevenlabs_params():
    t = TTSEngine(elevenlabs_api_key="sk-el", elevenlabs_voice_id="voice-xyz")
    assert t._el_key == "sk-el"
    assert t._el_voice == "voice-xyz"


def test_env_key_fallback(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "env-el-key")
    t = TTSEngine()
    assert t._el_key == "env-el-key"


# ---------------------------------------------------------------------------
# _elevenlabs — no API key raises
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_elevenlabs_no_key_raises():
    t = TTSEngine(elevenlabs_api_key="")
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        await t._elevenlabs("hello")


# ---------------------------------------------------------------------------
# _elevenlabs — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_elevenlabs_returns_bytes():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"fake-mp3-bytes"

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        t = TTSEngine(elevenlabs_api_key="sk-test")
        result = await t._elevenlabs("Hello world")

    assert result == b"fake-mp3-bytes"


# ---------------------------------------------------------------------------
# _kokoro — missing package raises
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kokoro_missing_package_raises():
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "kokoro":
            raise ImportError("No module named 'kokoro'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        t = TTSEngine()
        with pytest.raises(RuntimeError, match="pip install kokoro"):
            await t._kokoro("hello")


# ---------------------------------------------------------------------------
# synthesize — fallback chain stops at first success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_uses_first_working_provider():
    t = TTSEngine(elevenlabs_api_key="sk-test")

    async def mock_elevenlabs(text: str) -> bytes:
        return b"el-audio"

    t._elevenlabs = mock_elevenlabs
    result = await t.synthesize("Say something")
    assert result == b"el-audio"


@pytest.mark.asyncio
async def test_synthesize_falls_back_to_kokoro_on_elevenlabs_failure():
    t = TTSEngine(elevenlabs_api_key="sk-test")

    async def mock_elevenlabs(text: str) -> bytes:
        raise RuntimeError("ElevenLabs down")

    async def mock_kokoro(text: str) -> bytes:
        return b"kokoro-audio"

    t._elevenlabs = mock_elevenlabs
    t._kokoro = mock_kokoro
    result = await t.synthesize("Say something")
    assert result == b"kokoro-audio"


@pytest.mark.asyncio
async def test_synthesize_raises_if_all_providers_fail():
    t = TTSEngine()

    async def fail(text: str) -> bytes:
        raise RuntimeError("provider failed")

    t._elevenlabs = fail
    t._kokoro = fail
    t._system = fail

    with pytest.raises(RuntimeError, match="All TTS providers failed"):
        await t.synthesize("hello")


# ---------------------------------------------------------------------------
# synthesize — writes output_path when provided
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_writes_output_path(tmp_path):
    t = TTSEngine()

    async def mock_system(text: str) -> bytes:
        return b"wav-bytes"

    t._elevenlabs = AsyncMock(side_effect=RuntimeError("no key"))
    t._kokoro = AsyncMock(side_effect=RuntimeError("no kokoro"))
    t._system = mock_system

    out = tmp_path / "speech.wav"
    await t.synthesize("hello", output_path=out)
    assert out.exists()
    assert out.read_bytes() == b"wav-bytes"


# ---------------------------------------------------------------------------
# prefer_local reverses chain order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefer_local_tries_kokoro_first():
    t = TTSEngine(prefer_local=True)
    call_order: list[str] = []

    async def mock_kokoro(text: str) -> bytes:
        call_order.append("kokoro")
        return b"kokoro"

    async def mock_elevenlabs(text: str) -> bytes:
        call_order.append("elevenlabs")
        return b"el"

    t._kokoro = mock_kokoro
    t._elevenlabs = mock_elevenlabs

    await t.synthesize("hi")
    assert call_order[0] == "kokoro"


# ---------------------------------------------------------------------------
# use_voice
# ---------------------------------------------------------------------------


def test_use_voice_switches_active_voice_id():
    t = TTSEngine(elevenlabs_voice_id="original-voice")
    t.use_voice("cloned-voice-id")
    assert t._el_voice == "cloned-voice-id"


# ---------------------------------------------------------------------------
# clone_voice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clone_voice_no_key_raises():
    t = TTSEngine(elevenlabs_api_key="")
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        await t.clone_voice("My Voice", [b"sample"])


@pytest.mark.asyncio
async def test_clone_voice_no_samples_raises():
    t = TTSEngine(elevenlabs_api_key="sk-test")
    with pytest.raises(ValueError, match="at least one audio sample"):
        await t.clone_voice("My Voice", [])


@pytest.mark.asyncio
async def test_clone_voice_returns_voice_id():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"voice_id": "abc123"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        t = TTSEngine(elevenlabs_api_key="sk-test")
        voice_id = await t.clone_voice("My Voice", [b"sample-bytes"])

    assert voice_id == "abc123"


@pytest.mark.asyncio
async def test_clone_voice_sends_name_and_description():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"voice_id": "v1"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        t = TTSEngine(elevenlabs_api_key="sk-test")
        await t.clone_voice("My Voice", [b"sample"], description="a test voice")

    call_kwargs = mock_client.post.call_args[1]
    assert call_kwargs["data"]["name"] == "My Voice"
    assert call_kwargs["data"]["description"] == "a test voice"


@pytest.mark.asyncio
async def test_clone_voice_sends_one_file_per_sample():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"voice_id": "v2"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        t = TTSEngine(elevenlabs_api_key="sk-test")
        await t.clone_voice("My Voice", [b"sample-1", b"sample-2", b"sample-3"])

    call_kwargs = mock_client.post.call_args[1]
    assert len(call_kwargs["files"]) == 3


@pytest.mark.asyncio
async def test_clone_voice_does_not_switch_active_voice():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"voice_id": "new-voice"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        t = TTSEngine(elevenlabs_api_key="sk-test")
        original_voice = t._el_voice
        await t.clone_voice("My Voice", [b"sample"])

    assert t._el_voice == original_voice
