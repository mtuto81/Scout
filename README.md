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

Do not commit real API keys. Use environment variables or a local `.env` file copied from `.env.example`.

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

## GitHub Releases

Use git tags for app updates:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The GitHub Actions workflow builds a Linux archive suitable for attaching to a release.

## In-App Updates

Scout can check a GitHub-hosted update manifest:

```bash
export SCOUT_UPDATE_MANIFEST_URL=https://github.com/OWNER/REPO/releases/latest/download/latest.json
```

The manifest format is shown in:

```text
packaging/linux/latest.example.json
```

The app periodically checks this URL, downloads newer Linux builds, verifies SHA-256 when provided, and stages the update before asking to restart and apply.
