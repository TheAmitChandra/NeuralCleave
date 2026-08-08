import httpx

SKILL_METADATA = {
    "name": "translate",
    "description": "Translate text to any language using LibreTranslate (free, no API key).",
    "version": "1.0.0",
    "trigger": "translate",
    "dependencies": ["httpx"],
}


async def run(args: dict) -> str:
    text = args.get("text", "")
    target = args.get("target", "es")
    source = args.get("source", "auto")
    r = httpx.post(
        "https://libretranslate.com/translate",
        json={"q": text, "source": source, "target": target, "format": "text"},
        headers={"Content-Type": "application/json"},
    )
    return r.json().get("translatedText", "Translation failed")
