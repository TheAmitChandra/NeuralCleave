import os

import httpx

SKILL_METADATA = {
    "name": "spotify_now_playing",
    "description": "Show the currently playing Spotify track.",
    "version": "1.0.0",
    "trigger": "spotify",
    "dependencies": ["httpx"],
}


async def run(args: dict) -> str:
    token = os.environ.get("SPOTIFY_ACCESS_TOKEN", "")
    r = httpx.get(
        "https://api.spotify.com/v1/me/player/currently-playing",
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 204:
        return "Nothing is playing right now"
    if r.status_code != 200:
        return f"Spotify error: {r.status_code}"
    data = r.json()
    if not data or not data.get("item"):
        return "Nothing is playing right now"
    item = data["item"]
    artists = ", ".join(a["name"] for a in item["artists"])
    return f"Now playing: {item['name']} by {artists} ({item['album']['name']})"
