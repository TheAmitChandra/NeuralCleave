"""Image generation tool — fal.ai's synchronous API, plain httpx (no SDK).

Closes NeuralCleave's media-generation gap from zero to one. fal.ai was
chosen over a local diffusers pipeline because it needs no GPU, no multi-GB
model download, and no heavier dependency than the httpx client every other
lightweight tool in this package already uses (see web_search.py) — one
HTTP call in, an image URL out.

Requires a fal.ai API key (``FAL_KEY`` environment variable, or pass one
explicitly). Uses the ``fal.run`` synchronous endpoint, which blocks until
the image is ready — no queue polling needed.

Usage::

    tool = ImageGenerationTool()
    result = await tool.execute(prompt="a cat wearing sunglasses, studio photo")
    print(result.output)   # image URL
"""

from __future__ import annotations

import logging
import os
from typing import Any

from neuralcleave.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_FAL_RUN_URL = "https://fal.run"
DEFAULT_MODEL = "fal-ai/flux/schnell"


class ImageGenerationTool(Tool):
    """Generate an image from a text prompt via fal.ai."""

    name = "image_generation"
    description = (
        "Generate an image from a text description. Use when the user asks "
        "you to create, draw, generate, or make an image, picture, or "
        "illustration."
    )
    parameters = {
        "prompt": {
            "type": "str",
            "description": "Description of the image to generate.",
            "required": True,
        },
        "model": {
            "type": "str",
            "description": f"fal.ai model id to use. Defaults to {DEFAULT_MODEL!r}.",
            "required": False,
        },
    }
    permissions = ["network"]

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key or os.getenv("FAL_KEY", "")
        self._model = model

    async def execute(self, prompt: str = "", model: str | None = None, **_: Any) -> ToolResult:
        if not self._api_key:
            return ToolResult(tool=self.name, output=None, error="FAL_KEY not set")

        stripped = (prompt or "").strip()
        if not stripped:
            return ToolResult(tool=self.name, output=None, error="Prompt must not be empty.")

        try:
            import httpx  # type: ignore[import]
        except ImportError:
            return ToolResult(tool=self.name, output=None, error="pip install httpx")

        target_model = model or self._model
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{_FAL_RUN_URL}/{target_model}",
                    headers={"Authorization": f"Key {self._api_key}"},
                    json={"prompt": stripped},
                    timeout=60.0,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("image_generation.fal_run model=%s error=%s", target_model, exc)
            return ToolResult(tool=self.name, output=None, error=str(exc))

        images = data.get("images") or []
        urls = [img.get("url", "") for img in images if img.get("url")]
        if not urls:
            return ToolResult(tool=self.name, output=None, error="fal.ai returned no images.")

        return ToolResult(
            tool=self.name,
            output=urls[0] if len(urls) == 1 else urls,
            metadata={"model": target_model, "urls": urls, "seed": data.get("seed")},
        )
