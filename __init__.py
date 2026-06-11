"""MAGI Plugin — root entry point for directory-based installation.

When installed via ``pip`` (entry-point ``hermes_agent.plugins``), Hermes
imports ``magi_plugin`` directly and calls ``register(ctx)`` there.

When installed as a directory plugin under ``~/.hermes/plugins/magi/``,
Hermes imports this module and calls ``register(ctx)``. The actual
implementation lives in the ``magi_plugin`` sub-package; this file simply
re-exports ``register``.
"""

from __future__ import annotations

# Re-export registration function from the sub-package.
# (Absolute imports inside ``magi_plugin/__init__.py`` are handled by a
# ``sys.modules`` shim so they resolve correctly when loaded as a directory
# plugin under the ``hermes_plugins`` namespace.)
from .magi_plugin import register

__all__ = ["register"]
