import os

import httpx

SKILL_METADATA = {
    "name": "linear_tasks",
    "description": "List your assigned Linear issues or create a new task.",
    "version": "1.0.0",
    "trigger": "linear",
    "dependencies": ["httpx"],
}

_GQL = "https://api.linear.app/graphql"


async def run(args: dict) -> str:
    key = os.environ.get("LINEAR_API_KEY", "")
    action = args.get("action", "list")
    headers = {"Authorization": key, "Content-Type": "application/json"}

    if action == "create":
        title = args.get("title", "New task")
        team_id = args.get("team_id", "")
        query = """
          mutation($title: String!, $teamId: String!) {
            issueCreate(input: {title: $title, teamId: $teamId}) {
              issue { identifier title url }
            }
          }
        """
        r = httpx.post(
            _GQL,
            json={"query": query, "variables": {"title": title, "teamId": team_id}},
            headers=headers,
        )
        issue = r.json()["data"]["issueCreate"]["issue"]
        return f"Created {issue['identifier']}: {issue['title']} — {issue['url']}"

    query = """
      query {
        viewer {
          assignedIssues(first: 10, filter: {state: {type: {nin: ["completed","cancelled"]}}}) {
            nodes { identifier title state { name } }
          }
        }
      }
    """
    r = httpx.post(_GQL, json={"query": query}, headers=headers)
    issues = r.json()["data"]["viewer"]["assignedIssues"]["nodes"]
    if not issues:
        return "No open assigned issues in Linear"
    return "\n".join(
        f"{i['identifier']} [{i['state']['name']}] {i['title']}" for i in issues
    )
