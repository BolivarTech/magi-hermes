#!/usr/bin/env python3
"""MAGI model registry for Hermes-native configuration.

Reads model assignments from Hermes config.yaml (magi.models.<mage>).
Falls back to environment variables and built-in defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

AGENTS = ("melchior", "balthasar", "caspar")
DEFAULT_MODEL = "llama3.1:latest"
DEFAULT_HOST = "http://localhost:11434/v1"


def _load_hermes_yaml() -> dict[str, Any]:
    """Best-effort read of Hermes config.yaml without external deps."""
    try:
        import yaml
    except ImportError:
        return {}
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    cfg_path = home / "config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        with cfg_path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_model(agent: str) -> str:
    """Return the model identifier for *agent*.

    Resolution order:
    1. ``magi.models.<agent>`` in Hermes config.yaml
    2. ``MAGIMODEL_<AGENT>`` environment variable (uppercase)
    3. ``magi.ollama.default_model`` in config.yaml
    4. ``MAGIMODEL_DEFAULT`` environment variable
    5. Built-in default ``llama3.1:latest``
    """
    cfg = _load_hermes_yaml()
    magi = cfg.get("magi", {})
    per_mage = magi.get("models", {})
    if agent in per_mage and per_mage[agent]:
        return str(per_mage[agent])
    env_key = f"MAGIMODEL_{agent.upper()}"
    if os.environ.get(env_key):
        return os.environ[env_key]
    default = magi.get("ollama", {}).get("default_model")
    if default:
        return str(default)
    if os.environ.get("MAGIMODEL_DEFAULT"):
        return os.environ["MAGIMODEL_DEFAULT"]
    return DEFAULT_MODEL


def get_models() -> dict[str, str]:
    """Return a mapping of agent name -> model identifier."""
    return {agent: get_model(agent) for agent in AGENTS}


def get_host() -> str:
    """Return the OpenAI-compatible endpoint URL.

    Resolution order:
    1. ``magi.ollama.host`` in Hermes config.yaml
    2. ``OLLAMA_HOST`` environment variable
    3. Built-in default ``http://localhost:11434/v1``
    """
    cfg = _load_hermes_yaml()
    host = cfg.get("magi", {}).get("ollama", {}).get("host")
    if host:
        return str(host)
    env_host = os.environ.get("OLLAMA_HOST")
    if env_host:
        if not env_host.startswith("http"):
            env_host = f"http://{env_host}"
        if not env_host.rstrip("/").endswith("/v1"):
            env_host = f"{env_host.rstrip('/')}/v1"
        return env_host
    return DEFAULT_HOST


def get_timeout() -> int:
    """Return per-agent timeout in seconds (default 300)."""
    cfg = _load_hermes_yaml()
    val = cfg.get("magi", {}).get("ollama", {}).get("timeout", 300)
    return int(val)
