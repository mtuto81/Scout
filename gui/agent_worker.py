import asyncio
import threading

from PySide6.QtCore import QObject, Signal, Slot

from agent import AsyncAIAgent


class AgentWorker(QObject):
    result_ready = Signal(str)
    error = Signal(str)
    flow_event = Signal(str)
    busy_state_changed = Signal(bool)
    stopped = Signal()
    command_confirmation_requested = Signal(str)

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

    @Slot()
    def init(self):
        try:
            self._install_command_confirm_callback()
            self.agent = AsyncAIAgent(event_callback=self._emit_flow_event)
        except Exception as exc:
            self.error.emit(str(exc))

    @Slot()
    def reload_agent(self):
        with self._lock:
            if self._busy:
                self.error.emit("Settings saved, but the agent is busy. Restart Scout or wait before testing the new key.")
                return

        try:
            self._install_command_confirm_callback()
            self.agent = AsyncAIAgent(event_callback=self._emit_flow_event)
            self.flow_event.emit("Agent settings reloaded.")
        except Exception as exc:
            self.error.emit(str(exc))

    @Slot(str)
    def submit_query(self, query: str):
        with self._lock:
            if self._busy:
                self.error.emit("Agent is currently busy. Please wait.")
                return
            if not self.agent:
                self.error.emit("Agent is not initialized.")
                return

            self._busy = True
            self._cancel_event.clear()
            self.busy_state_changed.emit(True)

            self._job_thread = threading.Thread(
                target=self._run_query_job,
                args=(query,),
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
            else "Tool execution approval set to ask approval."
        )

    def _run_query_job(self, query: str):
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
            loop.close()
            self.busy_state_changed.emit(False)
            if stopped_to_emit:
                self.stopped.emit()
            elif error_to_emit is not None:
                self.error.emit(error_to_emit)
            elif response_to_emit is not None:
                self.result_ready.emit(response_to_emit)

    @Slot()
    def cancel_current_request(self):
        with self._lock:
            if not self._busy:
                return
            self._cancel_event.set()

    def _emit_flow_event(self, message: str) -> None:
        self.flow_event.emit(message)

    def _install_command_confirm_callback(self) -> None:
        try:
            from tools.cmd import set_confirm_callback
        except Exception as exc:
            self.flow_event.emit(f"Could not install command confirmation callback: {exc}")
            return

        set_confirm_callback(self._confirm_command)

    def _confirm_command(self, command: str) -> bool:
        with self._lock:
            approval_mode = self._tool_approval_mode

        if approval_mode == "approve_all":
            self.flow_event.emit(f"Auto-approved command: {command}")
            return True

        self._confirm_result = False
        self._confirm_event.clear()
        self.command_confirmation_requested.emit(command)
        self._confirm_event.wait()
        return self._confirm_result

    @Slot(bool)
    def resolve_command_confirmation(self, approved: bool) -> None:
        self._confirm_result = approved
        self._confirm_event.set()
