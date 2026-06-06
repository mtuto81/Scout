import os

# Load API keys from environment variables. Never commit real API keys.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TOG_API_KEY = os.environ.get("TOG_API_KEY")

SCOUT_BACKEND = os.environ.get("SCOUT_BACKEND", "openrouter").strip().lower()

OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "z-ai/glm-4.5-air:free")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:latest")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama")

# Backward-compatible model override.
MODEL = os.environ.get("AI_MODEL") or (OLLAMA_MODEL if SCOUT_BACKEND == "ollama" else OPENROUTER_MODEL)

SCOUT_UPDATE_MANIFEST_URL = os.environ.get(
    "SCOUT_UPDATE_MANIFEST_URL",
    "https://github.com/mtuto81/Scout/releases/latest/download/latest.json",
).strip()
SCOUT_UPDATE_CHECK_INTERVAL_SECONDS = int(os.environ.get("SCOUT_UPDATE_CHECK_INTERVAL_SECONDS", "21600"))


def get_llm_config():
    if SCOUT_BACKEND == "ollama":
        return {
            "backend": "ollama",
            "base_url": OLLAMA_BASE_URL,
            "api_key": OLLAMA_API_KEY,
            "model": MODEL,
        }

    if SCOUT_BACKEND == "openrouter":
        return {
            "backend": "openrouter",
            "base_url": OPENROUTER_BASE_URL,
            "api_key": OPENROUTER_API_KEY,
            "model": MODEL,
        }

    raise RuntimeError(f"Unsupported SCOUT_BACKEND '{SCOUT_BACKEND}'. Use 'openrouter' or 'ollama'.")
