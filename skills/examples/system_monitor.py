import psutil

SKILL_METADATA = {
    "name": "system_monitor",
    "description": "Report CPU usage, memory usage, and disk space.",
    "version": "1.0.0",
    "trigger": "system status",
    "dependencies": ["psutil"],
}


async def run(args: dict) -> str:
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return (
        f"CPU: {cpu}%\n"
        f"Memory: {mem.percent}% used ({mem.used // 1024**2} MB / {mem.total // 1024**2} MB)\n"
        f"Disk: {disk.percent}% used ({disk.used // 1024**3} GB / {disk.total // 1024**3} GB)"
    )
