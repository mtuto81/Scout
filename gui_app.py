import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
from gui.agent_worker import AgentWorker
from gui.main_windows import MainWindow

app = QApplication(sys.argv)
main_window = MainWindow()

agent_thread = QThread()
agent_worker = AgentWorker(None)
agent_worker.moveToThread(agent_thread)
agent_thread.started.connect(agent_worker.init)

main_window.prompt_submitted.connect(agent_worker.submit_query)
main_window.stop_requested.connect(agent_worker.cancel_current_request)
agent_worker.result_ready.connect(main_window.show_agent_response)
agent_worker.error.connect(main_window.show_error)
agent_worker.flow_event.connect(main_window.append_flow_event)
agent_worker.busy_state_changed.connect(main_window.set_busy)
agent_worker.stopped.connect(main_window.show_stopped)
agent_worker.command_confirmation_requested.connect(main_window.show_command_confirmation)
main_window.command_confirmation_resolved.connect(agent_worker.resolve_command_confirmation)

app.aboutToQuit.connect(agent_thread.quit)
app.aboutToQuit.connect(agent_thread.wait)

agent_thread.start()

main_window.show()
sys.exit(app.exec())
