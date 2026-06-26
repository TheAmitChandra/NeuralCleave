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

## One-time setup (per package, before its first publish)

The workflow uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OpenID Connect) instead of an API token, so no secret needs to be stored in
this repository. Each package needs its trusted publisher registered once on
PyPI's side:

1. Create the project on PyPI (or use "pending publisher" for a
   not-yet-existing project — PyPI supports this directly):
   - Go to <https://pypi.org/manage/account/publishing/>
   - Click "Add a new pending publisher"
   - Fill in:
     - **PyPI project name**: the name from the table above (e.g.
       `cortexflow-sdk`)
     - **Owner**: `TheAmitChandra`
     - **Repository name**: `CortexFlow`
     - **Workflow name**: `publish-pypi.yml`
     - **Environment name**: `pypi`
2. Repeat for each of the 4 package names you intend to publish.
3. In this repo's GitHub Settings → Environments, create an environment
   named `pypi` if it doesn't already exist. Optionally add required
   reviewers here for an extra manual-approval gate before any publish runs.

No PyPI account password or API token is ever given to this repo or to
Claude — trusted publishing exchanges a short-lived OIDC token for each run.

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
