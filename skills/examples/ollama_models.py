import httpx

SKILL_METADATA = {
    "name": "ollama_models",
    "description": "List installed Ollama models or pull a new one.",
    "version": "1.0.0",
    "trigger": "ollama",
    "dependencies": ["httpx"],
}

_BASE = "http://localhost:11434"


async def run(args: dict) -> str:
    action = args.get("action", "list")

    if action == "list":
        r = httpx.get(f"{_BASE}/api/tags")
        models = r.json().get("models", [])
        if not models:
            return "No Ollama models installed"
        return "\n".join(m["name"] for m in models)

    if action == "pull":
        name = args.get("model", "llama3")
        r = httpx.post(f"{_BASE}/api/pull", json={"name": name}, timeout=300)
        return f"Pulled {name}" if r.status_code == 200 else f"Pull failed: {r.text}"

    return "Unknown action. Use list or pull."
