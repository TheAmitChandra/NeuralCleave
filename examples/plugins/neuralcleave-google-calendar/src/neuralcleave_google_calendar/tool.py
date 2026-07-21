"""GoogleCalendarEventsTool — lists upcoming events from a Google Calendar."""

from __future__ import annotations

import datetime

from neuralcleave_sdk import Tool, ToolResult

_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class GoogleCalendarEventsTool(Tool):
    """Lists upcoming events from a Google Calendar via the Calendar API v3.

    Requires an OAuth2 access token with the
    ``https://www.googleapis.com/auth/calendar.readonly`` scope — obtaining
    that token (the OAuth consent flow) is out of scope for this tool.
    """

    name = "calendar_list_events"
    description = "List upcoming events from a Google Calendar."
    parameters = {
        "calendar_id": {
            "type": "str",
            "description": "Calendar ID, or 'primary' for the user's main calendar",
            "required": False,
        },
        "limit": {"type": "int", "description": "Max events to return (default 10)", "required": False},
    }
    permissions = ["network"]

    def __init__(self, access_token: str | None = None) -> None:
        self._access_token = access_token

    async def execute(self, calendar_id: str = "primary", limit: int = 10, **_) -> ToolResult:
        if not self._access_token:
            return ToolResult(
                tool=self.name, output=None, error="GOOGLE_CALENDAR_ACCESS_TOKEN not set",
            )

        try:
            import httpx
        except ImportError:
            return ToolResult(tool=self.name, output=None, error="pip install httpx")

        url = _EVENTS_URL.format(calendar_id=calendar_id)
        headers = {"Authorization": f"Bearer {self._access_token}"}
        params = {
            "timeMin": _now_iso(),
            "maxResults": min(limit, 100),
            "singleEvents": "true",
            "orderBy": "startTime",
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, params=params, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

        events = [
            {
                "summary": e.get("summary", "(no title)"),
                "start": (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date", ""),
                "link": e.get("htmlLink", ""),
            }
            for e in data.get("items", [])[:limit]
        ]
        return ToolResult(
            tool=self.name,
            output=events,
            metadata={"calendar_id": calendar_id, "count": len(events)},
        )
