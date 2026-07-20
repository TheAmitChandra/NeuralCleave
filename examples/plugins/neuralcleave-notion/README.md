# neuralcleave-notion

Example NeuralCleave plugin: a `notion_search` tool that searches Notion pages
and databases shared with your Notion integration.

## Install

```bash
pip install -e ./NeuralCleave-sdk        # not yet on PyPI
pip install -e examples/plugins/neuralcleave-notion
```

## Setup

1. Create a Notion integration at https://www.notion.so/my-integrations
2. Share the pages/databases you want searchable with that integration
3. Set `NOTION_TOKEN` in your environment to the integration's secret

## Usage

```python
from neuralcleave_notion import NotionSearchTool

tool = NotionSearchTool(token="secret_...")
result = await tool.execute(query="Q3 roadmap", limit=5)
print(result.output)
```

Once installed alongside the NeuralCleave gateway, `PluginRegistry.discover()`
finds it via the `NeuralCleave.plugins` entry point declared in
`pyproject.toml`.
