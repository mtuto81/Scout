# Scout on Linux

Scout is a PySide6 desktop app with the existing async agent as the backend.

## Install Dependencies

Use a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-linux.txt
```

For the online backend, set your API key outside git:

```bash
export OPENROUTER_API_KEY=your_key_here
```

Or open Scout Settings and save the OpenRouter API key in the app. It is stored locally in:

```text
~/.config/scout/settings.json
```

Conversations are stored locally in:

```text
~/.local/share/scout/conversations.sqlite3
```

For local Ollama:

```bash
export SCOUT_BACKEND=ollama
```

For direct local llama.cpp:

```bash
export SCOUT_BACKEND=local
export SCOUT_LOCAL_MODEL_PATH=/path/to/model.gguf
```

## Run

```bash
./scripts/scout
```

Or directly:

```bash
python gui_app.py
```

## Use Ollama Locally

Start Ollama, then run Scout with:

```bash
SCOUT_BACKEND=ollama ./scripts/scout
```

The model is controlled by `OLLAMA_MODEL` or `AI_MODEL`.

## Use llama.cpp Directly

Set `SCOUT_BACKEND=local`, point `SCOUT_LOCAL_MODEL_PATH` at a GGUF file, then run Scout. The app starts a local OpenAI-compatible sidecar on `127.0.0.1` and talks to it through the existing agent client.

## Install Desktop Launcher

## Build Linux Executable

Build a Linux executable with PyInstaller:

```bash
python build_linux_executable.py
```

Output:

```text
dist/Scout/Scout
```

Run it:

```bash
./dist/Scout/Scout
```

This executable bundles Python and the project dependencies. The target machine should not need Python installed, but it still needs normal Linux desktop libraries required by Qt.

For distribution, keep the whole folder together:

```text
dist/Scout/
  Scout
  _internal/
```

To publish on GitHub Releases:

```bash
tar -C dist -czf Scout-linux-x86_64.tar.gz Scout
sha256sum Scout-linux-x86_64.tar.gz
```

The included GitHub Actions workflow can build this archive automatically from a version tag.
It also builds:

```text
Scout-linux-x86_64-installer.run
```

Users install with:

```bash
chmod +x Scout-linux-x86_64-installer.run
./Scout-linux-x86_64-installer.run
```

## In-App Updates

Scout checks for updates only when this environment variable is set:

```bash
export SCOUT_UPDATE_MANIFEST_URL=https://github.com/OWNER/REPO/releases/latest/download/latest.json
```

The manifest should look like:

```json
{
  "name": "Scout",
  "version": "0.1.0",
  "platform": "linux-x86_64",
  "release_url": "https://github.com/OWNER/REPO/releases/tag/v0.1.0",
  "download_url": "https://github.com/OWNER/REPO/releases/download/v0.1.0/Scout-linux-x86_64.tar.gz",
  "sha256": "release-archive-sha256",
  "installer_url": "https://github.com/OWNER/REPO/releases/download/v0.1.0/Scout-linux-x86_64-installer.run",
  "installer_sha256": "installer-sha256"
}
```

The settings icon in Scout manually checks for updates. Automatic checks run every six hours by default.

Python installer:

```bash
python install_linux_desktop.py
```

Shell installer:

```bash
./scripts/install_linux_desktop.sh
```

This installs:

```text
~/.local/share/applications/scout.desktop
```

Then open Scout from your desktop app menu. On KDE, you can bind a shortcut in:

```text
System Settings -> Keyboard -> Shortcuts -> Add Application
```

## Notes

- The launcher runs the repo copy of Scout.
- If `.venv/bin/python` exists, the launcher uses it.
- Otherwise it falls back to `python` from your shell path.
