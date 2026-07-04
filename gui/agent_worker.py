import asyncio
import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from agent import AsyncAIAgent
from config import get_runtime_settings
from local import find_free_port, start_server_process
import requests


class AgentWorker(QObject):
    result_ready = Signal(str, int)
    error = Signal(str, int)
    flow_event = Signal(str, int)
    busy_state_changed = Signal(bool)
    stopped = Signal(int)
    command_confirmation_requested = Signal(str)
    file_operation_confirmation_requested = Signal(str)

    def __init__(self, agent: AsyncAIAgent | None):
        super().__init__()
        self.agent = agent
        self._busy = False
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._job_thread = None
        self._loop = None
        self._task = None
        self._confirm_event = threading.Event()
        self._confirm_result = False
        self._tool_approval_mode = "ask"
        self._conversation_context = []
        self._pending_conversation_context = None
        self._active_conversation_id = None
        self._local_process = None
        self._local_base_url = None
        self._local_log_path = None
        self._last_activity_time = time.monotonic()
        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._check_idle_timeout)
        self._idle_timer.setInterval(30000)

    @Slot()
    def init(self):
        try:
            self._prepare_backend_runtime()
            self._install_command_confirm_callback()
            self._install_file_confirm_callback()
            self.agent = AsyncAIAgent(event_callback=self._emit_flow_event)
            self._apply_conversation_context()
            self._idle_timer.start()
        except Exception as exc:
            self.error.emit(str(exc), -1)

    @Slot()
    def reload_agent(self):
        with self._lock:
            if self._busy:
                self.error.emit(
                    "Settings saved, but the agent is busy. Restart Scout or wait before retrying.",
                    self._active_conversation_id or -1,
                )
                return

        try:
            self._prepare_backend_runtime()
            self._install_command_confirm_callback()
            self._install_file_confirm_callback()
            self.agent = AsyncAIAgent(event_callback=self._emit_flow_event)
            self._apply_conversation_context()
            self.flow_event.emit("Agent settings reloaded.", -1)
        except Exception as exc:
            self.error.emit(str(exc), -1)

    @Slot()
    def cleanup(self):
        self._idle_timer.stop()
        with self._lock:
            self._cancel_event.set()
        self._stop_local_backend()

    @Slot(str, int)
    def submit_query(self, query: str, conversation_id: int):
        with self._lock:
            if self._busy:
                self.error.emit("Agent is currently busy. Please wait.", conversation_id)
                return
            if not self.agent:
                self.error.emit("Agent is not initialized.", conversation_id)
                return

            self._busy = True
            self._active_conversation_id = conversation_id
            self._cancel_event.clear()
            self._last_activity_time = time.monotonic()
            self.busy_state_changed.emit(True)

            self._job_thread = threading.Thread(
                target=self._run_query_job,
                args=(query, conversation_id),
                daemon=True,
            )
            self._job_thread.start()

    @Slot(str)
    def set_tool_approval_mode(self, mode: str):
        normalized = mode if mode in ("ask", "approve_all") else "ask"
        with self._lock:
            self._tool_approval_mode = normalized
        self.flow_event.emit(
            "Tool execution approval set to approve all."
            if normalized == "approve_all"
            else "Tool execution approval set to ask approval.",
            -1,
        )

    @Slot(list)
    def load_conversation_context(self, messages: list):
        cleaned_messages = self._clean_conversation_messages(messages)

        with self._lock:
            if self._busy:
                self._pending_conversation_context = cleaned_messages
                return
            agent = self.agent

        if not agent:
            return

        self._conversation_context = cleaned_messages
        self._apply_conversation_context()

    def _clean_conversation_messages(self, messages: list) -> list:
        cleaned_messages = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role in ("user", "assistant") and isinstance(content, str):
                cleaned_messages.append({"role": role, "content": content})
        return cleaned_messages

    def _apply_conversation_context(self) -> None:
        if not self.agent:
            return
        self.agent.conversation_history = list(self._conversation_context)

    def _run_query_job(self, query: str, conversation_id: int):
        loop = asyncio.new_event_loop()
        response_to_emit = None
        error_to_emit = None
        stopped_to_emit = False
        with self._lock:
            self._loop = loop

        try:
            asyncio.set_event_loop(loop)
            task = loop.create_task(self.agent.get_ai_response(query))
            with self._lock:
                self._task = task

            while not task.done():
                loop.run_until_complete(asyncio.sleep(0.05))
                if self._cancel_event.is_set() and not task.done():
                    task.cancel()

            response = task.result()
            if self._cancel_event.is_set():
                stopped_to_emit = True
            else:
                response_to_emit = response
        except asyncio.CancelledError:
            stopped_to_emit = True
        except Exception as exc:
            if self._cancel_event.is_set():
                stopped_to_emit = True
            else:
                error_to_emit = str(exc)
        finally:
            with self._lock:
                self._busy = False
                self._cancel_event.clear()
                self._job_thread = None
                self._loop = None
                self._task = None
                pending_context = self._pending_conversation_context
                self._pending_conversation_context = None
                if pending_context is not None:
                    self._conversation_context = pending_context
                self._active_conversation_id = None
                self._last_activity_time = time.monotonic()
            loop.close()
            if pending_context is not None:
                self._apply_conversation_context()
            self.busy_state_changed.emit(False)
            if stopped_to_emit:
                self.stopped.emit(conversation_id)
            elif error_to_emit is not None:
                self.error.emit(error_to_emit, conversation_id)
            elif response_to_emit is not None:
                self.result_ready.emit(response_to_emit, conversation_id)

    @Slot()
    def cancel_current_request(self):
        with self._lock:
            if not self._busy:
                return
            self._cancel_event.set()

    def _emit_flow_event(self, message: str) -> None:
        with self._lock:
            conversation_id = self._active_conversation_id or -1
        self.flow_event.emit(message, conversation_id)

    def _install_command_confirm_callback(self) -> None:
        try:
            from tools.cmd import set_confirm_callback
        except Exception as exc:
            self._emit_flow_event(f"Could not install command confirmation callback: {exc}")
            return

        set_confirm_callback(self._confirm_command)

    def _install_file_confirm_callback(self) -> None:
        try:
            from tools.fs_crud import set_confirm_callback as set_fs_confirm
        except Exception as exc:
            self._emit_flow_event(f"Could not install file operation confirmation callback: {exc}")
            return

        set_fs_confirm(self._confirm_file_operation)

    def _prepare_backend_runtime(self) -> None:
        runtime = get_runtime_settings()
        backend = runtime.get("backend")

        if backend != "local":
            self._stop_local_backend()
            os.environ.pop("SCOUT_LOCAL_BASE_URL", None)
            return

        self._stop_local_backend()
        local_model_path = str(runtime.get("local_model_path") or "").strip()
        if not local_model_path:
            raise RuntimeError("Local backend is selected, but no GGUF model path is configured.")

        host = "127.0.0.1"
        port = find_free_port(host)
        gpu_layers = str(runtime.get("local_gpu_layers") or "auto").strip() or "auto"
        ctx_size = int(runtime.get("local_ctx_size") or 4096)
        max_tokens = int(runtime.get("local_max_tokens") or 768)
        threads = int(runtime.get("local_threads") or 1)

        log_path = Path("/tmp") / f"scout-local-{port}.log"
        self._local_process = start_server_process(
            model_path=local_model_path,
            host=host,
            port=port,
            ctx=ctx_size,
            threads=threads,
            gpu_layers=gpu_layers,
            max_tokens=max_tokens,
            log_path=str(log_path),
        )
        self._local_log_path = log_path
        self._local_base_url = f"http://{host}:{port}/v1"
        os.environ["SCOUT_LOCAL_BASE_URL"] = self._local_base_url

        try:
            self._wait_for_local_backend(self._local_base_url, timeout_seconds=180)
        except Exception:
            self._stop_local_backend()
            raise

    def _wait_for_local_backend(self, base_url: str, timeout_seconds: int = 180) -> None:
        deadline = time.monotonic() + timeout_seconds
        health_url = f"{base_url.rstrip('/')}/health"

        while time.monotonic() < deadline:
            process = self._local_process
            if process and process.poll() is not None:
                raise RuntimeError(self._read_local_log_tail() or "Local backend process exited before it became ready.")

            try:
                response = requests.get(health_url, timeout=1.0)
                if response.ok:
                    return
            except Exception:
                pass

            time.sleep(0.5)

        raise RuntimeError(self._read_local_log_tail() or "Timed out waiting for the local backend to start.")

    def _read_local_log_tail(self, max_lines: int = 40) -> str:
        if not self._local_log_path or not self._local_log_path.exists():
            return ""

        try:
            lines = self._local_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return ""

        tail = lines[-max_lines:]
        return "\n".join(tail).strip()

    def _stop_local_backend(self) -> None:
        process = self._local_process
        self._local_process = None
        self._local_base_url = None
        self._local_log_path = None
        os.environ.pop("SCOUT_LOCAL_BASE_URL", None)

        if not process:
            return

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except Exception:
                    process.kill()
                    process.wait(timeout=10)
        except Exception:
            pass

    def _check_idle_timeout(self) -> None:
        with self._lock:
            if not self._local_process:
                return
            if self._busy:
                return
            idle_time = time.monotonic() - self._last_activity_time
            if idle_time < 60:
                return
            self._emit_flow_event("Local backend stopped after 1 minute of idle time.")
            self._stop_local_backend()

    def _confirm_command(self, command: str) -> bool:
        with self._lock:
            approval_mode = self._tool_approval_mode

        if approval_mode == "approve_all":
            self._emit_flow_event(f"Auto-approved command: {command}")
            return True

        self._confirm_result = False
        self._confirm_event.clear()
        self.command_confirmation_requested.emit(command)
        if not self._confirm_event.wait(timeout=300):
            self._emit_flow_event("Command approval timed out.")
            return False
        return self._confirm_result

    def _confirm_file_operation(self, description: str) -> bool:
        with self._lock:
            approval_mode = self._tool_approval_mode

        if approval_mode == "approve_all":
            self._emit_flow_event(f"Auto-approved file operation: {description}")
            return True

        self._confirm_result = False
        self._confirm_event.clear()
        self.file_operation_confirmation_requested.emit(description)
        if not self._confirm_event.wait(timeout=300):
            self._emit_flow_event("File operation approval timed out.")
            return False
        return self._confirm_result

    @Slot(bool)
    def resolve_command_confirmation(self, approved: bool) -> None:
        self._confirm_result = approved
        self._confirm_event.set()

    @Slot(bool)
    def resolve_file_operation_confirmation(self, approved: bool) -> None:
        self._confirm_result = approved
        self._confirm_event.set()
