SKILL_METADATA = {
    "name": "jira_tickets",
    "description": "List your Jira tickets assigned to you or search by JQL.",
    "version": "1.0.0",
    "trigger": "jira",
    "dependencies": ["httpx"],
}

import os
import httpx


async def run(args: dict) -> str:
    url = os.environ.get("JIRA_URL", "").rstrip("/")
    user = os.environ.get("JIRA_USER", "")
    token = os.environ.get("JIRA_TOKEN", "")
    jql = args.get(
        "jql",
        "assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC",
    )
    r = httpx.get(
        f"{url}/rest/api/3/search",
        params={"jql": jql, "maxResults": 10, "fields": "summary,status,priority"},
        auth=(user, token),
    )
    issues = r.json().get("issues", [])
    if not issues:
        return "No Jira tickets found"
    return "\n".join(
        f"{i['key']} [{i['fields']['status']['name']}] {i['fields']['summary']}"
        for i in issues
    )
