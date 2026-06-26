# Publishing to PyPI

This repo ships four independently-publishable Python packages:

| Package | Directory | PyPI name |
|---|---|---|
| Plugin SDK | `cortexflow-sdk/` | `cortexflow-sdk` |
| GitHub plugin | `examples/plugins/cortexflow-github/` | `cortexflow-github` |
| Notion plugin | `examples/plugins/cortexflow-notion/` | `cortexflow-notion` |
| Google Calendar plugin | `examples/plugins/cortexflow-google-calendar/` | `cortexflow-google-calendar` |

All four are published on PyPI (first published 2026-06-26 via a PyPI API
token; that token, `PYPI_API_TOKEN`, is still stored as a `pypi`-environment
secret but is no longer used now that Trusted Publishing is registered —
see below).

Publishing is handled by `.github/workflows/publish-pypi.yml`. It never
triggers on a routine push to `main` — publishing a version is irreversible
(a version number can be yanked but never deleted or reused) — but it does
trigger automatically when a **GitHub Release is published**, since cutting
a release is itself the deliberate action. `workflow_dispatch` remains as a
manual fallback with the same package-choice dropdown as before.

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

**Preferred: cut a GitHub Release.** The release's tag prefix decides which
package gets published:

| Tag prefix | Package |
|---|---|
| `sdk-v*` | `cortexflow-sdk` |
| `github-plugin-v*` | `cortexflow-github` |
| `notion-plugin-v*` | `cortexflow-notion` |
| `calendar-plugin-v*` | `cortexflow-google-calendar` |

1. Bump the `version` field in the package's `pyproject.toml` and merge to
   `main`.
2. Go to the repo's Releases page → "Draft a new release".
3. Tag: e.g. `sdk-v0.1.2` (must match the version you bumped to, and match
   one of the prefixes above so the workflow can resolve the package).
4. Publish the release — `publish-pypi.yml` triggers automatically, builds
   the sdist + wheel, runs `twine check`, then uploads via
   `pypa/gh-action-pypi-publish`.

**Fallback: manual trigger.** Actions tab → "Publish to PyPI" → "Run
workflow" → choose the package from the dropdown → run. Useful for
re-running a publish without cutting a new release (e.g. retrying after a
transient failure).

## Local verification (recommended before triggering the workflow)

```bash
cd cortexflow-sdk            # or examples/plugins/<name>
python -m pip install build twine
python -m build
python -m twine check dist/*
```
