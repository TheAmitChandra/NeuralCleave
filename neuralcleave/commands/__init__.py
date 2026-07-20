"""NeuralCleave slash command system.

Provides cross-channel command handling for /reset, /memory, /model,
/status, /compact, and /voice commands.

Quick start:
    from neuralcleave.commands import CommandHandler

    handler = CommandHandler.make_default()
    result  = await handler.dispatch("/reset", session=session)
    if result.handled:
        await adapter.send(sender_id, result.text)
"""

from neuralcleave.commands.handler import CommandHandler, CommandResult

__all__ = ["CommandHandler", "CommandResult"]
