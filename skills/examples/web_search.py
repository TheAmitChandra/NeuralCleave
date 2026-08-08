SKILL_METADATA = {
    "name": "web_search",
    "description": "Search the web using DuckDuckGo Instant Answer API (no key required).",
    "version": "1.0.0",
    "trigger": "search",
    "dependencies": ["httpx"],
}

import httpx


async def run(args: dict) -> str:
    query = args.get("query", "")
    r = httpx.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
    )
    data = r.json()
    abstract = data.get("AbstractText", "")
    related = [t["Text"] for t in data.get("RelatedTopics", [])[:5] if "Text" in t]
    if abstract:
        return abstract
    if related:
        return "\n".join(related)
    return f"No instant answer for '{query}'. Try a more specific query."
