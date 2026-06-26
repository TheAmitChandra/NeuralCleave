# Example CortexFlow plugins

Three working plugins demonstrating [`cortexflow-sdk`](../../cortexflow-sdk),
called for in [`docs/IMPLEMENTATION_PLAN_v2.md`](../../docs/IMPLEMENTATION_PLAN_v2.md)
Phase 3 ("Example plugins: GitHub Events, Notion integration, Google
Calendar"). Each is a standalone, independently installable package with its
own `pyproject.toml`, `cortexflow.plugins` entry point, and test suite.

| Plugin | Tool | API |
|---|---|---|
| [`cortexflow-github`](cortexflow-github/) | `github_events` | GitHub REST API |
| [`cortexflow-notion`](cortexflow-notion/) | `notion_search` | Notion API |
| [`cortexflow-google-calendar`](cortexflow-google-calendar/) | `calendar_list_events` | Google Calendar API v3 |

## Pattern used by all three

Every plugin here follows the same shape:

```
cortexflow-<name>/
├── pyproject.toml          # declares the cortexflow.plugins entry point
├── README.md
├── src/cortexflow_<name>/
│   ├── __init__.py         # re-exports Plugin + Tool
│   ├── plugin.py           # Plugin subclass, reads its API key/token from env
│   └── tool.py             # Tool subclass, does the actual HTTP call
└── tests/
    ├── test_plugin.py
    └── test_tool.py
```

- The `Tool.execute()` method never raises — network/HTTP/missing-dependency
  failures are caught and returned as `ToolResult(error=...)`.
- The `Plugin` reads its credential from an environment variable
  (`GITHUB_TOKEN`, `NOTION_TOKEN`, `GOOGLE_CALENDAR_ACCESS_TOKEN`) in
  `__init__` and hands it to the `Tool` it constructs — credentials never
  live in the tool's class body.
- Tests mock `httpx.AsyncClient` rather than hitting the real API, following
  the same pattern used throughout the main `cortexflow` test suite.

## Try one locally

```bash
pip install -e ./cortexflow-sdk
pip install -e examples/plugins/cortexflow-github
pytest examples/plugins/cortexflow-github/tests/
```
