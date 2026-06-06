import json
import os
from pathlib import Path


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "z-ai/glm-4.5-air:free"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_OLLAMA_MODEL = "gemma4:latest"
DEFAULT_UPDATE_MANIFEST_URL = "https://github.com/mtuto81/Scout/releases/latest/download/latest.json"


def get_settings_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "scout" / "settings.json"
    return Path.home() / ".config" / "scout" / "settings.json"


def load_user_settings() -> dict:
    path = get_settings_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def save_user_settings(updates: dict) -> None:
    path = get_settings_path()
    settings = load_user_settings()
    for key, value in updates.items():
        if value is None or value == "":
            settings.pop(key, None)
        else:
            settings[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _setting(key: str, env_name: str, default=None):
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return env_value
    return load_user_settings().get(key, default)


def get_runtime_settings() -> dict:
    backend = str(_setting("backend", "SCOUT_BACKEND", "openrouter")).strip().lower()
    openrouter_model = str(_setting("openrouter_model", "OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL))
    ollama_model = str(_setting("ollama_model", "OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL))
    model = os.environ.get("AI_MODEL") or (ollama_model if backend == "ollama" else openrouter_model)

    return {
        "backend": backend,
        "openrouter_api_key": _setting("openrouter_api_key", "OPENROUTER_API_KEY"),
        "groq_api_key": os.environ.get("GROQ_API_KEY"),
        "tog_api_key": os.environ.get("TOG_API_KEY"),
        "openrouter_base_url": str(_setting("openrouter_base_url", "OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL)),
        "openrouter_model": openrouter_model,
        "ollama_base_url": str(_setting("ollama_base_url", "OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)),
        "ollama_model": ollama_model,
        "ollama_api_key": str(_setting("ollama_api_key", "OLLAMA_API_KEY", "ollama")),
        "model": model,
        "update_manifest_url": str(_setting("update_manifest_url", "SCOUT_UPDATE_MANIFEST_URL", DEFAULT_UPDATE_MANIFEST_URL)).strip(),
        "update_check_interval_seconds": int(_setting("update_check_interval_seconds", "SCOUT_UPDATE_CHECK_INTERVAL_SECONDS", "21600")),
    }


_RUNTIME_SETTINGS = get_runtime_settings()

# Load API keys from environment variables. Never commit real API keys.
OPENROUTER_API_KEY = _RUNTIME_SETTINGS["openrouter_api_key"]
GROQ_API_KEY = _RUNTIME_SETTINGS["groq_api_key"]
TOG_API_KEY = _RUNTIME_SETTINGS["tog_api_key"]

SCOUT_BACKEND = _RUNTIME_SETTINGS["backend"]

OPENROUTER_BASE_URL = _RUNTIME_SETTINGS["openrouter_base_url"]
OPENROUTER_MODEL = _RUNTIME_SETTINGS["openrouter_model"]

OLLAMA_BASE_URL = _RUNTIME_SETTINGS["ollama_base_url"]
OLLAMA_MODEL = _RUNTIME_SETTINGS["ollama_model"]
OLLAMA_API_KEY = _RUNTIME_SETTINGS["ollama_api_key"]

# Backward-compatible model override.
MODEL = _RUNTIME_SETTINGS["model"]

SCOUT_UPDATE_MANIFEST_URL = _RUNTIME_SETTINGS["update_manifest_url"]
SCOUT_UPDATE_CHECK_INTERVAL_SECONDS = _RUNTIME_SETTINGS["update_check_interval_seconds"]


def get_llm_config():
    settings = get_runtime_settings()

    if settings["backend"] == "ollama":
        return {
            "backend": "ollama",
            "base_url": settings["ollama_base_url"],
            "api_key": settings["ollama_api_key"],
            "model": settings["model"],
        }

    if settings["backend"] == "openrouter":
        return {
            "backend": "openrouter",
            "base_url": settings["openrouter_base_url"],
            "api_key": settings["openrouter_api_key"],
            "model": settings["model"],
        }

    raise RuntimeError(f"Unsupported SCOUT_BACKEND '{settings['backend']}'. Use 'openrouter' or 'ollama'.")
