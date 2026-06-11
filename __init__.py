"""MAGI Plugin — root entry point for directory-based installation.

When installed via ``pip`` (entry-point ``hermes_agent.plugins``), Hermes
imports ``magi_plugin`` directly and calls ``register(ctx)`` there.

When installed as a directory plugin under ``~/.hermes/plugins/magi/``,
Hermes imports this module and calls ``register(ctx)``. This file simply
re-exports the registration function from the package.
"""

from __future__ import annotations

# Re-export everything from the package so directory-based loading works.
from magi_plugin import register

__all__ = ["register"]
