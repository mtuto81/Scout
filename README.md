# Scout

Scout is a native Linux IT assistant built with PySide6. It can use an online OpenRouter-compatible backend or a local Ollama backend.

## Run From Source

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-linux.txt
./scripts/scout
```

## Build Linux Executable

```bash
python build_linux_executable.py
```

Output:

```text
dist/Scout/Scout
```

## Desktop Launcher

```bash
python install_linux_desktop.py
```

## Configuration
In the desktop app, open Settings and save your OpenRouter API key there. Scout stores it locally in:

```text
~/.config/scout/settings.json
```

Environment variables still override saved settings.

For OpenRouter:

```bash
export SCOUT_BACKEND=openrouter
export OPENROUTER_API_KEY=your_key_here
```

For Ollama:

```bash
export SCOUT_BACKEND=ollama
export OLLAMA_MODEL=gemma4:latest
```



## In-App Updates
