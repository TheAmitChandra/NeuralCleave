import httpx

SKILL_METADATA = {
    "name": "weather",
    "description": "Fetch current weather for any city using Open-Meteo (free, no API key).",
    "version": "1.0.0",
    "trigger": "weather",
    "dependencies": ["httpx"],
}


async def run(args: dict) -> str:
    city = args.get("city", "London")
    geo = httpx.get(
        f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
    ).json()
    results = geo.get("results")
    if not results:
        return f"City not found: {city}"
    loc = results[0]
    w = httpx.get(
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={loc['latitude']}&longitude={loc['longitude']}&current_weather=true"
    ).json()["current_weather"]
    return f"Weather in {city}: {w['temperature']}°C, wind {w['windspeed']} km/h"
