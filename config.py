import hashlib
import json
import os
from pathlib import Path


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "google/gemma-4-26b-a4b-it:free"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_OLLAMA_MODEL = "gemma4:latest"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:11435/v1"
DEFAULT_LOCAL_MODEL_PATH = ""
DEFAULT_LOCAL_CTX_SIZE = 4096
DEFAULT_LOCAL_MAX_TOKENS = 768
DEFAULT_LOCAL_THREADS = max(1, (os.cpu_count() or 2) - 1)
DEFAULT_LOCAL_GPU_LAYERS = "auto"
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
            if key == "openrouter_api_key":
                settings.pop("openrouter_api_key_sha256", None)
        else:
            settings[key] = value
            if key == "openrouter_api_key":
                settings["openrouter_api_key_sha256"] = hash_secret(value)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def short_secret_hash(value: str | None) -> str:
    if not value:
        return ""
    digest = value if len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower()) else hash_secret(value)
    return f"sha256:{digest[:12]}"


def _setting(key: str, env_name: str, default=None):
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return env_value
    return load_user_settings().get(key, default)


def _int_setting(key: str, env_name: str, default: int) -> int:
    value = _setting(key, env_name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _local_model_label(model_path: str | None) -> str:
    if not model_path:
        return "local"
    return Path(str(model_path)).name or "local"


def get_runtime_settings() -> dict:
    backend = str(_setting("backend", "SCOUT_BACKEND", "openrouter")).strip().lower()
    openrouter_model = str(_setting("openrouter_model", "OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL))
    ollama_model = str(_setting("ollama_model", "OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL))
    local_model_path = str(_setting("local_model_path", "SCOUT_LOCAL_MODEL_PATH", DEFAULT_LOCAL_MODEL_PATH)).strip()
    local_model = os.environ.get("AI_MODEL") or _local_model_label(local_model_path)
    model = os.environ.get("AI_MODEL") or (
        local_model if backend == "local" else ollama_model if backend == "ollama" else openrouter_model
    )

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
        "local_base_url": str(_setting("local_base_url", "SCOUT_LOCAL_BASE_URL", DEFAULT_LOCAL_BASE_URL)),
        "local_model_path": local_model_path,
        "local_ctx_size": _int_setting("local_ctx_size", "SCOUT_LOCAL_CTX_SIZE", DEFAULT_LOCAL_CTX_SIZE),
        "local_max_tokens": _int_setting("local_max_tokens", "SCOUT_LOCAL_MAX_TOKENS", DEFAULT_LOCAL_MAX_TOKENS),
        "local_threads": _int_setting("local_threads", "SCOUT_LOCAL_THREADS", DEFAULT_LOCAL_THREADS),
        "local_gpu_layers": str(_setting("local_gpu_layers", "SCOUT_LOCAL_GPU_LAYERS", DEFAULT_LOCAL_GPU_LAYERS)).strip() or "auto",
        "local_api_key": str(_setting("local_api_key", "SCOUT_LOCAL_API_KEY", "local")),
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

LOCAL_BASE_URL = _RUNTIME_SETTINGS["local_base_url"]
LOCAL_MODEL_PATH = _RUNTIME_SETTINGS["local_model_path"]
LOCAL_CTX_SIZE = _RUNTIME_SETTINGS["local_ctx_size"]
LOCAL_MAX_TOKENS = _RUNTIME_SETTINGS["local_max_tokens"]
LOCAL_THREADS = _RUNTIME_SETTINGS["local_threads"]
LOCAL_GPU_LAYERS = _RUNTIME_SETTINGS["local_gpu_layers"]
LOCAL_API_KEY = _RUNTIME_SETTINGS["local_api_key"]

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

    if settings["backend"] == "local":
        return {
            "backend": "local",
            "base_url": settings["local_base_url"],
            "api_key": settings["local_api_key"],
            "model": settings["model"],
        }

    if settings["backend"] == "openrouter":
        return {
            "backend": "openrouter",
            "base_url": settings["openrouter_base_url"],
            "api_key": settings["openrouter_api_key"],
            "model": settings["model"],
        }

    raise RuntimeError(f"Unsupported SCOUT_BACKEND '{settings['backend']}'. Use 'openrouter', 'ollama', or 'local'.")
