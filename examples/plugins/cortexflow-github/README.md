# cortexflow-github

Example CortexFlow plugin: a `github_events` tool that lists recent events
(pushes, PRs, issues) for a GitHub repository via the public REST API.

## Install

```bash
pip install -e ./cortexflow-sdk        # not yet on PyPI
pip install -e examples/plugins/cortexflow-github
```

## Usage

Set `GITHUB_TOKEN` in your environment for authenticated requests (raises the
rate limit from 60/hr to 5000/hr) — optional, the tool works without it.

```python
from cortexflow_github import GitHubEventsTool

tool = GitHubEventsTool()
result = await tool.execute(owner="TheAmitChandra", repo="CortexFlow", limit=5)
print(result.output)
```

Once installed alongside the CortexFlow gateway, `cortex plugin add
cortexflow-github` (or simply having it installed in the same environment)
makes `PluginRegistry.discover()` find it via the `cortexflow.plugins` entry
point declared in `pyproject.toml`.
