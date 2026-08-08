SKILL_METADATA = {
    "name": "news_briefing",
    "description": "Fetch top news headlines for a topic or country.",
    "version": "1.0.0",
    "trigger": "news",
    "dependencies": ["httpx"],
}

import os
import httpx


async def run(args: dict) -> str:
    key = os.environ.get("NEWSAPI_KEY", "")
    topic = args.get("topic", "technology")
    n = int(args.get("n", 5))
    r = httpx.get(
        "https://newsapi.org/v2/top-headlines",
        params={"q": topic, "pageSize": n, "apiKey": key},
    )
    articles = r.json().get("articles", [])
    if not articles:
        return f"No headlines found for '{topic}'"
    return "\n".join(
        f"- {a['title']} ({a['source']['name']})" for a in articles
    )
