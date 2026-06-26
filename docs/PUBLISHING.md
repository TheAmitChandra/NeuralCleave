# Publishing to PyPI

This repo ships four independently-publishable Python packages:

| Package | Directory | PyPI name |
|---|---|---|
| Plugin SDK | `cortexflow-sdk/` | `cortexflow-sdk` |
| GitHub plugin | `examples/plugins/cortexflow-github/` | `cortexflow-github` |
| Notion plugin | `examples/plugins/cortexflow-notion/` | `cortexflow-notion` |
| Google Calendar plugin | `examples/plugins/cortexflow-google-calendar/` | `cortexflow-google-calendar` |

All four build and pass `twine check` today (`python -m build <dir>` then
`python -m twine check <dir>/dist/*`). None have been published yet — all
four names are unregistered on PyPI as of 2026-06-26.

Publishing is handled by `.github/workflows/publish-pypi.yml`, a
**manual-only** (`workflow_dispatch`) GitHub Actions workflow. It is never
triggered automatically by a push or tag, because publishing a version to
PyPI is irreversible — a version number can be yanked but never deleted or
reused.

## One-time setup (already done)

The workflow authenticates with a PyPI API token stored as the
`PYPI_API_TOKEN` secret, scoped to this repo's `pypi` GitHub Environment
(Settings → Environments → `pypi` → Environment secrets). The token value
was added directly via the GitHub UI and was never shared in chat, pasted
into a commit, or stored anywhere in this repository.

A single account-level (or "all projects") PyPI API token covers all four
packages — there's no per-package registration step like Trusted Publishing
would require. If the token is ever scoped to a specific project instead,
it will need to be regenerated as an account-wide token (or one token per
project) before publishing a package for the first time, since a
project-scoped token can't be created until the project already exists on
PyPI.

Optionally, add required reviewers to the `pypi` environment
(Settings → Environments → `pypi` → Deployment protection rules) for an
extra manual-approval gate before any publish run can use the secret.

## Publishing a release

1. Bump the `version` field in the package's `pyproject.toml`.
2. Go to the repo's Actions tab → "Publish to PyPI" → "Run workflow".
3. Choose the package from the dropdown and run.
4. The workflow builds the sdist + wheel, runs `twine check`, then uploads
   via `pypa/gh-action-pypi-publish`.

## Local verification (recommended before triggering the workflow)

```bash
cd cortexflow-sdk            # or examples/plugins/<name>
python -m pip install build twine
python -m build
python -m twine check dist/*
```
