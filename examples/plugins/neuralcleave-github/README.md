# neuralcleave-github

Example NeuralCleave plugin: a `github_events` tool that lists recent events
(pushes, PRs, issues) for a GitHub repository via the public REST API.

## Install

```bash
pip install -e ./NeuralCleave-sdk        # not yet on PyPI
pip install -e examples/plugins/neuralcleave-github
```

## Usage

Set `GITHUB_TOKEN` in your environment for authenticated requests (raises the
rate limit from 60/hr to 5000/hr) — optional, the tool works without it.

```python
from neuralcleave_github import GitHubEventsTool

tool = GitHubEventsTool()
result = await tool.execute(owner="TheAmitChandra", repo="NeuralCleave", limit=5)
print(result.output)
```

Once installed alongside the NeuralCleave gateway, `cortex plugin add
neuralcleave-github` (or simply having it installed in the same environment)
makes `PluginRegistry.discover()` find it via the `NeuralCleave.plugins` entry
point declared in `pyproject.toml`.
