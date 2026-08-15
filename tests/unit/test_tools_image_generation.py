"""Tests for ImageGenerationTool (fal.ai)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.tools.image_generation import DEFAULT_MODEL, ImageGenerationTool


def _make_response(body: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


def _make_client(resp: MagicMock) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=resp)
    return client


class TestMissingConfiguration:
    @pytest.mark.asyncio
    async def test_raises_if_no_api_key(self) -> None:
        tool = ImageGenerationTool(api_key="")
        result = await tool.execute(prompt="a cat")
        assert result.error == "FAL_KEY not set"

    @pytest.mark.asyncio
    async def test_empty_prompt_returns_error(self) -> None:
        tool = ImageGenerationTool(api_key="fal-test-key")
        result = await tool.execute(prompt="   ")
        assert result.error == "Prompt must not be empty."


class TestSuccess:
    @pytest.mark.asyncio
    async def test_single_image_returns_url_as_output(self) -> None:
        tool = ImageGenerationTool(api_key="fal-test-key")
        resp = _make_response({"images": [{"url": "https://fal.media/cat.png"}], "seed": 42})
        client = _make_client(resp)

        with patch("httpx.AsyncClient", return_value=client):
            result = await tool.execute(prompt="a cat wearing sunglasses")

        assert result.output == "https://fal.media/cat.png"
        assert result.error is None
        assert result.metadata["seed"] == 42

    @pytest.mark.asyncio
    async def test_posts_to_correct_url_and_headers(self) -> None:
        tool = ImageGenerationTool(api_key="fal-test-key")
        resp = _make_response({"images": [{"url": "https://fal.media/x.png"}]})
        client = _make_client(resp)

        with patch("httpx.AsyncClient", return_value=client):
            await tool.execute(prompt="a cat")

        call = client.post.call_args
        assert call.args[0] == f"https://fal.run/{DEFAULT_MODEL}"
        assert call.kwargs["headers"]["Authorization"] == "Key fal-test-key"
        assert call.kwargs["json"]["prompt"] == "a cat"

    @pytest.mark.asyncio
    async def test_multiple_images_returns_list(self) -> None:
        tool = ImageGenerationTool(api_key="fal-test-key")
        resp = _make_response(
            {"images": [{"url": "https://fal.media/a.png"}, {"url": "https://fal.media/b.png"}]}
        )
        client = _make_client(resp)

        with patch("httpx.AsyncClient", return_value=client):
            result = await tool.execute(prompt="two cats")

        assert result.output == ["https://fal.media/a.png", "https://fal.media/b.png"]

    @pytest.mark.asyncio
    async def test_custom_model_overrides_default(self) -> None:
        tool = ImageGenerationTool(api_key="fal-test-key")
        resp = _make_response({"images": [{"url": "https://fal.media/x.png"}]})
        client = _make_client(resp)

        with patch("httpx.AsyncClient", return_value=client):
            result = await tool.execute(prompt="a cat", model="fal-ai/flux/dev")

        call = client.post.call_args
        assert call.args[0] == "https://fal.run/fal-ai/flux/dev"
        assert result.metadata["model"] == "fal-ai/flux/dev"


class TestFailure:
    @pytest.mark.asyncio
    async def test_no_images_in_response_returns_error(self) -> None:
        tool = ImageGenerationTool(api_key="fal-test-key")
        resp = _make_response({"images": []})
        client = _make_client(resp)

        with patch("httpx.AsyncClient", return_value=client):
            result = await tool.execute(prompt="a cat")

        assert result.output is None
        assert "no images" in result.error.lower()

    @pytest.mark.asyncio
    async def test_http_error_is_captured(self) -> None:
        tool = ImageGenerationTool(api_key="fal-test-key")
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(side_effect=RuntimeError("connection reset"))

        with patch("httpx.AsyncClient", return_value=client):
            result = await tool.execute(prompt="a cat")

        assert result.output is None
        assert "connection reset" in result.error
