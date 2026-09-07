# Contributing to NeuralCleave

Thanks for your interest in contributing. Before you open a PR, please read this.

## License note

NeuralCleave is source-available under the [Business Source License 1.1](LICENSE) — free for non-production use, with production use requiring a commercial license until the 2030-06-26 change date (after which it converts to Apache 2.0). **By submitting a PR, you agree that your contribution is licensed under the same terms as the rest of the project.** There is no separate CLA to sign.

## Before you start

For anything beyond a small fix (new channel adapter, new LLM provider, architectural change), please open an issue first to discuss the approach — it saves you from doing work that doesn't get merged.

## Development setup

```bash
git clone https://github.com/TheAmitChandra/NeuralCleave.git
cd NeuralCleave
pip install -e ".[dev]"
```

## Running tests

```bash
pytest                                              # root backend suite
pytest tests/unit/test_memory_retrieval.py -v                 # single module
pytest -k "telegram" -v                             # by keyword
pytest --cov=neuralcleave --cov-report=term-missing      # with coverage
```

For frontend changes, run `npm ci`, `npm run lint`, `npm run type-check`, `npx vitest run`, and `npm run build` from `frontend/`. Use `npm run build:tauri` for static desktop export. See [development guidance](docs/agent-skills/neuralcleave-development/references/development.md) for the maintained workflow.

## Pull requests

- Keep PRs focused — one logical change per PR.
- Add or update tests for any behavior change.
- Make sure `pytest` and `ruff` pass locally before opening the PR (CI uses `ruff check neuralcleave tests --select E,F,W,I --ignore E501`).
- Fill out the PR template completely.

## Reporting bugs / requesting features

Use the [issue templates](.github/ISSUE_TEMPLATE/) — bug report or feature request. For security vulnerabilities, see [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Code of conduct

Participation in this project is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
