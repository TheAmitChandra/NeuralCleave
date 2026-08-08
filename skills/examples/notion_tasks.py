import os

import httpx

SKILL_METADATA = {
    "name": "notion_tasks",
    "description": "List incomplete tasks from a Notion database.",
    "version": "1.0.0",
    "trigger": "notion",
    "dependencies": ["httpx"],
}


async def run(args: dict) -> str:
    token = os.environ.get("NOTION_TOKEN", "")
    db_id = os.environ.get("NOTION_DATABASE_ID", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    body = {
        "filter": {"property": "Status", "status": {"does_not_equal": "Done"}},
        "page_size": 10,
    }
    r = httpx.post(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        json=body,
        headers=headers,
    )
    results = r.json().get("results", [])
    if not results:
        return "No incomplete tasks in Notion"
    lines = []
    for page in results:
        props = page.get("properties", {})
        title_prop = next((v for v in props.values() if v.get("type") == "title"), None)
        title = (
            title_prop["title"][0]["plain_text"]
            if title_prop and title_prop["title"]
            else "Untitled"
        )
        lines.append(title)
    return "\n".join(lines)
