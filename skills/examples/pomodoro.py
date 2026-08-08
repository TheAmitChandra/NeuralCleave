import time

SKILL_METADATA = {
    "name": "pomodoro",
    "description": "Start a Pomodoro timer (25 min work / 5 min break cycle).",
    "version": "1.0.0",
    "trigger": "pomodoro",
}

_sessions: dict = {}


async def run(args: dict) -> str:
    action = args.get("action", "start")
    session_id = args.get("session_id", "default")

    if action == "start":
        work_min = int(args.get("work_min", 25))
        _sessions[session_id] = {"started": time.time(), "work_min": work_min}
        return f"Pomodoro started. Focus for {work_min} minutes. Good luck!"

    if action == "status":
        if session_id not in _sessions:
            return "No active Pomodoro. Use action=start to begin."
        elapsed = (time.time() - _sessions[session_id]["started"]) / 60
        work_min = _sessions[session_id]["work_min"]
        if elapsed >= work_min:
            return f"Pomodoro complete! Take a 5-minute break. ({elapsed:.1f} min elapsed)"
        return f"Pomodoro in progress: {work_min - elapsed:.1f} minutes remaining."

    if action == "stop":
        _sessions.pop(session_id, None)
        return "Pomodoro stopped."

    return "Unknown action. Use start, status, or stop."
