import feedparser
import httpx

SKILL_METADATA = {
    "name": "daily_digest",
    "description": "Fetch top headlines from RSS feeds for a morning digest.",
    "version": "1.0.0",
    "trigger": "digest",
    "dependencies": ["httpx", "feedparser"],
}

_FEEDS = {
    "HN": "https://news.ycombinator.com/rss",
    "TheVerge": "https://www.theverge.com/rss/index.xml",
    "ArsTechnica": "http://feeds.arstechnica.com/arstechnica/index",
}


async def run(args: dict) -> str:
    feeds = args.get("feeds", list(_FEEDS.keys()))
    n = int(args.get("n", 5))
    lines = []
    for name in feeds:
        url = _FEEDS.get(name, name)
        try:
            r = httpx.get(url, timeout=8, follow_redirects=True)
            parsed = feedparser.parse(r.text)
            for entry in parsed.entries[:n]:
                lines.append(f"[{name}] {entry.title}")
        except Exception as e:
            lines.append(f"[{name}] Error: {e}")
    return "\n".join(lines) if lines else "No items fetched"
