# Publishing to PyPI

This repo ships four independently-publishable Python packages:

| Package | Directory | PyPI name |
|---|---|---|
| Plugin SDK | `cortexflow-sdk/` | `cortexflow-sdk` |
| GitHub plugin | `examples/plugins/cortexflow-github/` | `cortexflow-github` |
| Notion plugin | `examples/plugins/cortexflow-notion/` | `cortexflow-notion` |
| Google Calendar plugin | `examples/plugins/cortexflow-google-calendar/` | `cortexflow-google-calendar` |

All four are published on PyPI as of 2026-06-26, at version 0.1.0, uploaded
via a PyPI API token (`PYPI_API_TOKEN`, added as a `pypi`-environment secret
through the GitHub UI — never shared in chat or committed).

Publishing is handled by `.github/workflows/publish-pypi.yml`, a
**manual-only** (`workflow_dispatch`) GitHub Actions workflow. It is never
triggered automatically by a push or tag, because publishing a version to
PyPI is irreversible — a version number can be yanked but never deleted or
reused.

## Trusted Publishing (current setup)

The workflow now authenticates via
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC)
instead of the API token — token uploads never carry PyPI's verified
provenance/attestation badge, but OIDC-published releases do. The
`PYPI_API_TOKEN` secret is left in place but unused, in case of rollback.

Because all 4 projects already exist on PyPI (no more "pending publisher"
flow needed), each one is registered individually under its own project
settings:

1. For each package, go to
   `https://pypi.org/manage/project/<package-name>/settings/publishing/`
   (e.g. `https://pypi.org/manage/project/cortexflow-sdk/settings/publishing/`)
2. Under "Add a new publisher", fill in:
   - **Owner**: `TheAmitChandra`
   - **Repository name**: `CortexFlow`
   - **Workflow name**: `publish-pypi.yml`
   - **Environment name**: `pypi`
3. Repeat for all 4: `cortexflow-sdk`, `cortexflow-github`,
   `cortexflow-notion`, `cortexflow-google-calendar`.

Until a project has this registered, a workflow run publishing that
project will fail at the upload step (no token fallback is wired up).
Releases already published via the token (the initial 0.1.0 of all 4) keep
their existing PyPI listing — only the *next* publish for each project goes
through OIDC and picks up the attestation badge.

Optionally, add required reviewers to the `pypi` GitHub Environment
(Settings → Environments → `pypi` → Deployment protection rules) for an
extra manual-approval gate before any publish run.

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
