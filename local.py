import argparse
import json
import os
import socket
import subprocess
import sys
import time
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any


DEFAULT_MODEL_PATH = Path("models/Mistral-7B-Instruct-v0.3.Q8_0.gguf")
MODEL_DOWNLOAD_URL = (
    "https://huggingface.co/bartowski/Mistral-7B-v0.1-GGUF/resolve/main/"
    "Mistral-7B-v0.3.Q8_0.gguf"
)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11435
DEFAULT_CTX = 2048
DEFAULT_MAX_TOKENS = 256
DEFAULT_THREADS = max(1, (os.cpu_count() or 2) - 1)
DEFAULT_GPU_LAYERS = "auto"


def _load_llama_class():
    try:
        from llama_cpp import Llama
    except Exception as exc:  # pragma: no cover - dependency/runtime failure
        raise RuntimeError(
            "llama-cpp-python is required for local inference. Install it before starting the local backend."
        ) from exc
    return Llama


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scout local llama.cpp backend and smoke test.")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run the local backend as an OpenAI-compatible HTTP server.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GGUF_MODEL_PATH", str(DEFAULT_MODEL_PATH)),
        help="Path to a local .gguf model file. Can also be set with GGUF_MODEL_PATH.",
    )
    parser.add_argument("--host", default=os.environ.get("SCOUT_LOCAL_HOST", DEFAULT_HOST), help="Server host.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SCOUT_LOCAL_PORT", str(DEFAULT_PORT))), help="Server port.")
    parser.add_argument("--ctx", type=int, default=int(os.environ.get("SCOUT_LOCAL_CTX_SIZE", str(DEFAULT_CTX))), help="Context window size.")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.environ.get("SCOUT_LOCAL_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))),
        help="Maximum response tokens.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.environ.get("SCOUT_LOCAL_THREADS", str(DEFAULT_THREADS))),
        help="CPU threads to use.",
    )
    parser.add_argument(
        "--gpu-layers",
        default=os.environ.get("SCOUT_LOCAL_GPU_LAYERS", DEFAULT_GPU_LAYERS),
        help="GPU layer count or 'auto' for fallback attempts.",
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly one short sentence confirming llama.cpp works.",
        help="Prompt to send to the local model when not serving.",
    )
    return parser.parse_args()


def _normalize_gpu_layers(value: str) -> list[int]:
    value = str(value).strip().lower()
    if value == "auto":
        return [16, 8, 0]
    return [int(value)]


def _ensure_model_path(model_path: Path) -> None:
    if model_path.exists():
        return

    raise SystemExit(
        f"GGUF model not found: {model_path}\n\n"
        f"Download this test model:\n{MODEL_DOWNLOAD_URL}\n\n"
        f"Suggested location:\n{DEFAULT_MODEL_PATH}\n\n"
        "Then run:\n"
        f"python local.py --model {DEFAULT_MODEL_PATH}\n"
    )


def _model_name_from_path(model_path: Path) -> str:
    return model_path.name or "local"


def _latest_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
    return ""


def _heuristic_tool_call_payload(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    user_text = _latest_user_text(messages)
    lowered = user_text.lower()
    if not lowered:
        return None

    sysinfo_patterns = (
        r"\bhow much (?:ram|memory)\b",
        r"\bhow much mem\b",
        r"\bwhat is my (?:os|operating system)\b",
        r"\bwhat s my (?:os|operating system)\b",
        r"\bwhat's my (?:os|operating system)\b",
        r"\bwhat (?:os|operating system) do i have\b",
    )
    if any(re.search(pattern, lowered) for pattern in sysinfo_patterns):
        return {"tool_calls": [{"tool": "get_sysinfo", "args": {}}]}

    installed_patterns = (
        r"\bverify if i have ollama\b",
        r"\bcheck if i have ollama\b",
        r"\bdo i have ollama\b",
        r"\bis ollama installed\b",
        r"\bverify if i have wine\b",
        r"\bcheck if i have wine\b",
        r"\bdo i have wine\b",
        r"\bis wine installed\b",
        r"\bverify if .* ollama\b",
        r"\bcheck if .* ollama\b",
        r"\bverify if .* wine\b",
        r"\bcheck if .* wine\b",
    )
    if any(re.search(pattern, lowered) for pattern in installed_patterns):
        command = "ollama --version" if "ollama" in lowered else "which wine"
        return {"tool_calls": [{"tool": "run_cmd", "args": {"command": command}}]}

    return None


def _build_llama(model_path: Path, ctx: int, threads: int, gpu_layers: int):
    llama_cls = _load_llama_class()
    base_kwargs = {
        "model_path": str(model_path),
        "n_ctx": ctx,
        "n_threads": threads,
        "n_gpu_layers": gpu_layers,
        "verbose": False,
    }

    attempts = [
        dict(base_kwargs, use_mmap=True, use_mlock=False, chat_template_kwargs={"enable_thinking": False}),
        dict(base_kwargs, use_mmap=True, use_mlock=False),
        base_kwargs,
    ]

    last_error: Exception | None = None
    for kwargs in attempts:
        try:
            return llama_cls(**kwargs)
        except TypeError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("Could not initialize llama.cpp.")


class LocalLlamaService:
    def __init__(self, model_path: Path, ctx: int, threads: int, gpu_layers: str, max_tokens: int):
        self.model_path = model_path.expanduser()
        self.ctx = ctx
        self.threads = threads
        self.gpu_layers = gpu_layers
        self.max_tokens = max_tokens
        self.model_name = _model_name_from_path(self.model_path)
        self._llm = None
        self._lock = Lock()
        self.selected_gpu_layers: int | None = None

    def load(self) -> None:
        _ensure_model_path(self.model_path)

        last_error: Exception | None = None
        for gpu_layers in _normalize_gpu_layers(self.gpu_layers):
            try:
                self._llm = _build_llama(self.model_path, self.ctx, self.threads, gpu_layers)
                self.selected_gpu_layers = gpu_layers
                return
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise RuntimeError("Unable to load local model.")

    def chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._llm is None:
            raise RuntimeError("Local model is not loaded.")

        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise ValueError("Field 'messages' must be a list.")

        heuristic_payload = _heuristic_tool_call_payload(messages)
        if heuristic_payload is not None:
            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(heuristic_payload, ensure_ascii=False),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }

        request_max_tokens_value = payload.get("max_tokens")
        temperature_value = payload.get("temperature")
        request_max_tokens = int(self.max_tokens if request_max_tokens_value is None else request_max_tokens_value)
        temperature = float(0.1 if temperature_value is None else temperature_value)
        completion_kwargs = {
            "messages": messages,
            "max_tokens": request_max_tokens,
            "temperature": temperature,
            "top_p": payload.get("top_p"),
            "stop": payload.get("stop"),
        }
        completion_kwargs = {key: value for key, value in completion_kwargs.items() if value is not None}

        with self._lock:
            response = self._llm.create_chat_completion(**completion_kwargs)

        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        usage = response.get("usage") or {}

        return {
            "id": response.get("id") or f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": response.get("created") or int(time.time()),
            "model": self.model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": choice.get("finish_reason") or "stop",
                }
            ],
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }


class LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler_class, service: LocalLlamaService):
        super().__init__(address, handler_class)
        self.service = service


class LocalRequestHandler(BaseHTTPRequestHandler):
    server_version = "ScoutLocalLLM/1.0"

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        self._write_json(status, {"error": {"message": message, "type": "scout_local_error"}})

    def do_GET(self):  # noqa: N802
        if self.path in ("/health", "/v1/health"):
            self._write_json(200, {"status": "ok"})
            return

        if self.path in ("/models", "/v1/models"):
            service: LocalLlamaService = self.server.service  # type: ignore[attr-defined]
            self._write_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": service.model_name,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "scout",
                        }
                    ],
                },
            )
            return

        self._send_error(404, "Not found")

    def do_POST(self):  # noqa: N802
        if self.path not in ("/chat/completions", "/v1/chat/completions"):
            self._send_error(404, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            self._send_error(400, "Invalid JSON body")
            return

        service: LocalLlamaService = self.server.service  # type: ignore[attr-defined]
        try:
            response = service.chat_completion(payload)
        except Exception as exc:
            self._send_error(500, str(exc))
            return

        self._write_json(200, response)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        if os.environ.get("SCOUT_LOCAL_VERBOSE") == "1":
            super().log_message(format, *args)


def serve(host: str, port: int, model_path: Path, ctx: int, threads: int, gpu_layers: str, max_tokens: int) -> None:
    service = LocalLlamaService(model_path=model_path, ctx=ctx, threads=threads, gpu_layers=gpu_layers, max_tokens=max_tokens)
    service.load()
    server = LocalHTTPServer((host, port), LocalRequestHandler, service)
    print(
        f"Scout local backend listening on http://{host}:{port}/v1 using {service.model_name} "
        f"(gpu_layers={service.selected_gpu_layers})",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def smoke_test(model_path: Path, prompt: str, ctx: int, max_tokens: int, threads: int, gpu_layers: str) -> None:
    _ensure_model_path(model_path)
    llama = None
    last_error: Exception | None = None
    for candidate in _normalize_gpu_layers(gpu_layers):
        try:
            llama = _build_llama(model_path, ctx, threads, candidate)
            break
        except Exception as exc:
            last_error = exc

    if llama is None:
        raise SystemExit(str(last_error) if last_error else "Could not initialize llama.cpp.")

    response = llama.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    print((response["choices"][0]["message"]["content"] or "").strip())


def start_server_process(
    *,
    model_path: str,
    host: str,
    port: int,
    ctx: int,
    threads: int,
    gpu_layers: str,
    max_tokens: int,
    log_path: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    env["GGUF_MODEL_PATH"] = model_path
    env["SCOUT_LOCAL_HOST"] = host
    env["SCOUT_LOCAL_PORT"] = str(port)
    env["SCOUT_LOCAL_CTX_SIZE"] = str(ctx)
    env["SCOUT_LOCAL_THREADS"] = str(threads)
    env["SCOUT_LOCAL_GPU_LAYERS"] = gpu_layers
    env["SCOUT_LOCAL_MAX_TOKENS"] = str(max_tokens)

    command = [
        sys.executable,
        "-u",
        str(Path(__file__).resolve()),
        "--serve",
        "--model",
        model_path,
        "--host",
        host,
        "--port",
        str(port),
        "--ctx",
        str(ctx),
        "--threads",
        str(threads),
        "--gpu-layers",
        gpu_layers,
        "--max-tokens",
        str(max_tokens),
    ]
    log_handle = None
    try:
        if log_path:
            log_handle = open(log_path, "ab", buffering=0)
            return subprocess.Popen(command, env=env, stdout=log_handle, stderr=log_handle)
        return subprocess.Popen(command, env=env)
    finally:
        if log_handle is not None:
            log_handle.close()


def find_free_port(host: str = DEFAULT_HOST) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def main() -> None:
    args = parse_args()
    model_path = Path(args.model).expanduser()

    if args.serve:
        serve(args.host, args.port, model_path, args.ctx, args.threads, args.gpu_layers, args.max_tokens)
        return

    smoke_test(model_path, "hi,how are you", args.ctx, args.max_tokens, args.threads, args.gpu_layers)


if __name__ == "__main__":
    main()
