"""MAGI model registry for Hermes-native configuration.

Reads model assignments from Hermes config.yaml (magi.models.<mage>)
and falls back to environment variables and built-in defaults.

Original production defaults (cross-lineage diversity proven in
v2.6.0 for Ollama cloud tier "Máximo"):

* melchior : qwen3.5:397b-cloud   (Scientist / theoretical analysis)
* balthasar: gpt-oss:120b-cloud   (Pragmatist / practical trade-offs)
* caspar   : deepseek-v4-pro:cloud (Critic / adversarial review)
"""

from __future__ import annotations

import os
import sys
import tomllib
from types import MappingProxyType
from typing import Any, Mapping

AGENTS = ("melchior", "balthasar", "caspar")

#: Production-proven default models for Ollama cloud tier "Máximo"
#: (cross-lineage: Qwen + GPT-OSS + DeepSeek).
DEFAULT_MODELS: Mapping[str, str] = MappingProxyType(
    {
        "melchior": "qwen3.5:397b-cloud",
        "balthasar": "gpt-oss:120b-cloud",
        "caspar": "deepseek-v4-pro:cloud",
    }
)

DEFAULT_HOST = "http://localhost:11434/v1"
DEFAULT_TIMEOUT = 900  # per-agent; orchestrator uses this as ceiling
#: Synced from MAGI-Claude v4.0.2 (run_magi.py default --timeout 900)

#: Maximum bytes for any on-disk input MAGI will ingest.
MAX_INPUT_SIZE: int = 10 * 1024 * 1024  # 10 MB

#: Warn threshold (estimated tokens) — chars / 4 heuristic.
WARN_INPUT_TOKENS: int = 150_000

_KNOWN_TOP_KEYS = {"base_url", "api_key", "models", "structured"}


def _normalize_base_url(raw: str) -> str:
    raw = raw.rstrip("/")
    if "://" not in raw:
        raw = f"http://{raw}"
    tail = raw.split("://", 1)[1]
    if "/" not in tail:
        raw = f"{raw}/v1"
    return raw


def _load_toml(path: str) -> dict[str, Any]:
    """Load a TOML config file, returning empty dict if not found."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        print(f"WARNING: malformed TOML at {path}: {exc}", file=sys.stderr)
        return {}
    for key in set(data) - _KNOWN_TOP_KEYS:
        print(f"WARNING: unknown key '{key}' in {path} (ignored)", file=sys.stderr)
    return data


def resolve_ollama_config(
    *,
    global_path: str | None = None,
    repo_path: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve Ollama configuration from defaults + global/repo TOML + env.

    Precedence per key (high → low):
    1. MAGI-specific env vars (MAGI_OLLAMA_*).
    2. Repo-level TOML (.hermes/magi-ollama.toml).
    3. Global TOML (~/.hermes/magi-ollama.toml).
    4. Generic env fallbacks (OLLAMA_HOST, OLLAMA_API_KEY).
    5. Built-in defaults.

    Returns:
        Dict with keys: base_url, api_key, models (dict), structured.
    """
    if env is None:
        env = os.environ
    if global_path is None:
        global_path = os.path.expanduser("~/.hermes/magi-ollama.toml")
    if repo_path is None:
        repo_path = os.path.join(os.getcwd(), ".hermes", "magi-ollama.toml")

    g = _load_toml(global_path)
    r = _load_toml(repo_path)

    # base_url
    if env.get("MAGI_OLLAMA_HOST"):
        raw_host = env["MAGI_OLLAMA_HOST"]
    elif r.get("base_url"):
        raw_host = r["base_url"]
    elif g.get("base_url"):
        raw_host = g["base_url"]
    elif env.get("OLLAMA_HOST"):
        raw_host = env["OLLAMA_HOST"]
    else:
        raw_host = DEFAULT_HOST
    base_url = _normalize_base_url(raw_host)

    # api_key (presence-based; empty MAGI env => explicit None)
    if "MAGI_OLLAMA_API_KEY" in env:
        api_key = env["MAGI_OLLAMA_API_KEY"] or None
    elif r.get("api_key") is not None:
        api_key = r["api_key"] or None
    elif g.get("api_key") is not None:
        api_key = g["api_key"] or None
    elif env.get("OLLAMA_API_KEY"):
        api_key = env["OLLAMA_API_KEY"]
    else:
        api_key = None

    # structured mode
    structured = (
        env.get("MAGI_OLLAMA_STRUCTURED")
        or r.get("structured")
        or g.get("structured")
        or "schema"
    )

    # models per mage
    g_models = g.get("models", {}) or {}
    r_models = r.get("models", {}) or {}
    models: dict[str, str] = {}
    for mage in AGENTS:
        ekey = f"MAGI_OLLAMA_MODEL_{mage.upper()}"
        if env.get(ekey):
            models[mage] = env[ekey]
        elif r_models.get(mage):
            models[mage] = r_models[mage]
        elif g_models.get(mage):
            models[mage] = g_models[mage]
        else:
            models[mage] = DEFAULT_MODELS[mage]

    return {
        "base_url": base_url,
        "api_key": api_key,
        "models": models,
        "structured": structured,
    }


def get_model(agent: str) -> str:
    """Return the model identifier for *agent*.

    Resolution order:
    1. ``magi.models.<agent>`` in Hermes config.yaml
    2. ``MAGIMODEL_<AGENT>`` environment variable (uppercase)
    3. ``magi.ollama.default_model`` in config.yaml
    4. ``MAGIMODEL_DEFAULT`` environment variable
    5. Built-in default from resolve_ollama_config
    """
    # Try Hermes config.yaml first (backward compat)
    try:
        import yaml
    except ImportError:
        yaml = None

    if yaml is not None:
        home = os.path.expanduser(os.environ.get("HERMES_HOME", "~/.hermes"))
        cfg_path = os.path.join(home, "config.yaml")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                magi = cfg.get("magi", {})
                per_mage = magi.get("models", {})
                if agent in per_mage and per_mage[agent]:
                    return str(per_mage[agent])
                default = magi.get("ollama", {}).get("default_model")
                if default:
                    return str(default)
            except Exception:
                pass

    env_key = f"MAGIMODEL_{agent.upper()}"
    if os.environ.get(env_key):
        return os.environ[env_key]
    if os.environ.get("MAGIMODEL_DEFAULT"):
        return os.environ["MAGIMODEL_DEFAULT"]

    # Fall back to TOML-based resolution (the modern path)
    return resolve_ollama_config()["models"][agent]


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
    try:
        import yaml
    except ImportError:
        yaml = None

    if yaml is not None:
        home = os.path.expanduser(os.environ.get("HERMES_HOME", "~/.hermes"))
        cfg_path = os.path.join(home, "config.yaml")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                host = cfg.get("magi", {}).get("ollama", {}).get("host")
                if host:
                    return _normalize_base_url(str(host))
            except Exception:
                pass

    env_host = os.environ.get("OLLAMA_HOST")
    if env_host:
        return _normalize_base_url(env_host)

    return DEFAULT_HOST


def get_timeout() -> int:
    """Return per-agent timeout in seconds (default 300)."""
    try:
        import yaml
    except ImportError:
        yaml = None

    if yaml is not None:
        home = os.path.expanduser(os.environ.get("HERMES_HOME", "~/.hermes"))
        cfg_path = os.path.join(home, "config.yaml")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                val = cfg.get("magi", {}).get("ollama", {}).get("timeout", DEFAULT_TIMEOUT)
                return int(val)
            except Exception:
                pass

    env_timeout = os.environ.get("MAGIMODEL_TIMEOUT")
    if env_timeout:
        try:
            return int(env_timeout)
        except ValueError:
            pass
    return DEFAULT_TIMEOUT
