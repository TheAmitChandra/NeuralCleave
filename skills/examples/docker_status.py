import docker

SKILL_METADATA = {
    "name": "docker_status",
    "description": "List running Docker containers with their status and ports.",
    "version": "1.0.0",
    "trigger": "docker",
    "dependencies": ["docker"],
}


async def run(args: dict) -> str:
    client = docker.from_env()
    containers = client.containers.list()
    if not containers:
        return "No running containers"
    lines = []
    for c in containers:
        ports = ", ".join(
            f"{h[0]['HostPort']}->{p}" for p, h in c.ports.items() if h
        ) or "no ports"
        lines.append(f"{c.name} ({c.status}) [{ports}]")
    return "\n".join(lines)
