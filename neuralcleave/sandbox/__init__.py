"""NeuralCleave sandbox package — isolated execution backends.

Three backends are available:

``local``
    Runs commands on the host in a restricted subprocess (same machine,
    same user, configurable allowed-path list). Default when no sandbox
    config is present.

``docker``
    Wraps every command in ``docker run --rm``. The container is
    ephemeral (``--rm``), network-isolated (``--network none`` by
    default), and memory/CPU-capped. Requires Docker to be installed.

``ssh``
    Forwards execution to a remote host over SSH. Uses ``asyncssh``
    when available; falls back to the ``ssh`` CLI binary. Gives
    per-channel isolation on a dedicated VM or container host.

Usage::

    from neuralcleave.sandbox import SandboxManager

    mgr = SandboxManager.docker(image="python:3.12-slim")
    result = await mgr.execute("python -c 'print(1+1)'")
    print(result.stdout)  # "2"
    print(result.success) # True
"""

from neuralcleave.sandbox.base import Sandbox, SandboxResult
from neuralcleave.sandbox.docker import DockerSandbox
from neuralcleave.sandbox.local import LocalSandbox
from neuralcleave.sandbox.manager import SandboxManager
from neuralcleave.sandbox.ssh import SSHSandbox

__all__ = [
    "Sandbox",
    "SandboxResult",
    "LocalSandbox",
    "DockerSandbox",
    "SSHSandbox",
    "SandboxManager",
]
