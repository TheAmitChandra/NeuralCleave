"""GoogleCalendarPlugin — registers GoogleCalendarEventsTool with the gateway."""

from __future__ import annotations

import os

from NeuralCleave_sdk import Plugin, PluginMetadata

from neuralcleave_google_calendar.tool import GoogleCalendarEventsTool


class GoogleCalendarPlugin(Plugin):
    """Adds a calendar_list_events tool.

    Reads GOOGLE_CALENDAR_ACCESS_TOKEN from the environment — a short-lived
    OAuth2 access token, not a long-lived API key. Refreshing that token is
    left to the operator (e.g. a cron job calling Google's OAuth2 token
    endpoint with a stored refresh token).
    """

    metadata = PluginMetadata(
        name="neuralcleave-google-calendar",
        version="0.1.0",
        plugin_type="tool",
        description="List upcoming Google Calendar events.",
        permissions=["network"],
        homepage="https://github.com/TheAmitChandra/NeuralCleave",
    )

    def __init__(self) -> None:
        self._access_token = os.getenv("GOOGLE_CALENDAR_ACCESS_TOKEN")

    def get_tools(self):
        return [GoogleCalendarEventsTool(access_token=self._access_token)]
