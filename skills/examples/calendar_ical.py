SKILL_METADATA = {
    "name": "calendar_ical",
    "description": "List upcoming events from an iCal URL (Google Calendar, Fastmail, etc.).",
    "version": "1.0.0",
    "trigger": "calendar",
    "dependencies": ["httpx", "icalendar"],
}

import httpx
from icalendar import Calendar
from datetime import datetime, timezone, timedelta


async def run(args: dict) -> str:
    url = args.get("url", "")
    days = int(args.get("days", 7))
    if not url:
        return "Provide an iCal URL via the `url` argument"
    r = httpx.get(url, follow_redirects=True)
    cal = Calendar.from_ical(r.content)
    now = datetime.now(tz=timezone.utc)
    cutoff = now + timedelta(days=days)
    events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        dtstart = component.get("DTSTART").dt
        if not hasattr(dtstart, "tzinfo"):
            dtstart = datetime.combine(dtstart, datetime.min.time(), tzinfo=timezone.utc)
        if now <= dtstart <= cutoff:
            events.append((dtstart, str(component.get("SUMMARY", "Untitled"))))
    events.sort(key=lambda x: x[0])
    if not events:
        return f"No events in the next {days} days"
    return "\n".join(
        f"{dt.strftime('%a %b %d %H:%M')} - {s}" for dt, s in events[:15]
    )
