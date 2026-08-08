SKILL_METADATA = {
    "name": "hackernews_top",
    "description": "Fetch the top N stories from Hacker News.",
    "version": "1.0.0",
    "trigger": "hacker news",
    "dependencies": ["httpx"],
}

import httpx


async def run(args: dict) -> str:
    n = int(args.get("n", 10))
    ids = httpx.get(
        "https://hacker-news.firebaseio.com/v0/topstories.json"
    ).json()[:n]
    lines = []
    for story_id in ids:
        story = httpx.get(
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        ).json()
        url = story.get("url", "news.ycombinator.com")
        lines.append(f"[{story.get('score', 0)}pts] {story.get('title', '')} — {url}")
    return "\n".join(lines)
