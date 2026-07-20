# cortexflow-google-calendar

Example CortexFlow plugin: a `calendar_list_events` tool that lists upcoming
events from a Google Calendar via Calendar API v3.

## Install

```bash
pip install -e ./cortexflow-sdk        # not yet on PyPI
pip install -e examples/plugins/cortexflow-google-calendar
```

## Setup

This tool expects an OAuth2 **access token** with the
`https://www.googleapis.com/auth/calendar.readonly` scope, set as
`GOOGLE_CALENDAR_ACCESS_TOKEN`. Obtaining and refreshing that token (the
OAuth consent flow against Google's identity service) is outside this
plugin's scope — wire it up via your own token-refresh job or a library like
`google-auth-oauthlib`.

## Usage

```python
from cortexflow_google_calendar import GoogleCalendarEventsTool

tool = GoogleCalendarEventsTool(access_token="ya29....")
result = await tool.execute(calendar_id="primary", limit=5)
print(result.output)
```

Once installed alongside the CortexFlow gateway, `PluginRegistry.discover()`
finds it via the `cortexflow.plugins` entry point declared in
`pyproject.toml`.
