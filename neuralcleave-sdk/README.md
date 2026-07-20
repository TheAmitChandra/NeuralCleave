# neuralcleave-sdk

Typed interfaces for building [NeuralCleave](https://github.com/TheAmitChandra/NeuralCleave) plugins — without installing the full gateway.

NeuralCleave's gateway depends on FastAPI, Redis, Qdrant, and SDKs for all 14
supported channels. None of that is needed to *write* a plugin — only to
*run* the gateway that loads it. This package contains just the three base
classes a plugin author needs, with zero third-party dependencies.

## Install

```bash
pip install neuralcleave-sdk
```

## Writing a plugin

Every plugin package registers a `Plugin` subclass via a `NeuralCleave.plugins`
entry point:

```python
# my_plugin/plugin.py
from neuralcleave_sdk import Plugin, PluginMetadata, Tool, ToolResult


class WeatherTool(Tool):
    name = "get_weather"
    description = "Get the current weather for a city."
    parameters = {
        "city": {"type": "str", "description": "City name", "required": True},
    }
    permissions = ["network"]

    async def execute(self, city: str) -> ToolResult:
        # ... call a weather API ...
        return ToolResult(tool=self.name, output=f"Sunny in {city}")


class WeatherPlugin(Plugin):
    metadata = PluginMetadata(
        name="NeuralCleave-weather",
        version="1.0.0",
        plugin_type="tool",
        description="Adds a get_weather tool.",
        permissions=["network"],
    )

    def get_tools(self):
        return [WeatherTool()]
```

```toml
# my_plugin/pyproject.toml
[project.entry-points."NeuralCleave.plugins"]
NeuralCleave-weather = "my_plugin.plugin:WeatherPlugin"
```

Once published to PyPI and installed alongside the NeuralCleave gateway,
`cortex plugin add NeuralCleave-weather` discovers and loads it.

## Plugin types

| `plugin_type` | Implement | Contributes |
|---|---|---|
| `tool` | `get_tools()` | One or more `Tool` instances |
| `channel` | `get_channel_adapter()` | A `ChannelAdapter` instance |
| `tts` / `stt` / `memory` | — | Loaded by name; see gateway docs |
| `generic` | `on_load()` / `on_unload()` | Lifecycle hooks only |

## Writing a channel adapter plugin

```python
from neuralcleave_sdk import ChannelAdapter, InboundMessage


class MyChannelAdapter(ChannelAdapter):
    channel_id = "my_channel"

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def send(self, target, text, *, reply_to=None, attachments=None):
        ...

    async def _on_platform_event(self, raw_event: dict) -> None:
        await self._dispatch(InboundMessage(
            channel=self.channel_id,
            sender_id=raw_event["user_id"],
            sender_name=raw_event["user_name"],
            text=raw_event["text"],
        ))
```

## License

MIT
