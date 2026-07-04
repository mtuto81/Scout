import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
from gui.agent_worker import AgentWorker
from gui.main_windows import MainWindow
from gui.updater import UpdateManager

app = QApplication(sys.argv)
main_window = MainWindow()
update_manager = UpdateManager()

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
agent_worker.file_operation_confirmation_requested.connect(main_window.show_file_operation_confirmation)
main_window.file_operation_confirmation_resolved.connect(agent_worker.resolve_file_operation_confirmation)
main_window.settings_saved.connect(agent_worker.reload_agent)
main_window.tool_approval_mode_changed.connect(agent_worker.set_tool_approval_mode)
main_window.conversation_context_changed.connect(agent_worker.load_conversation_context)

main_window.update_check_requested.connect(update_manager.check_now)
main_window.update_download_requested.connect(update_manager.download_update)
main_window.update_apply_requested.connect(update_manager.apply_update)
update_manager.status.connect(main_window.show_update_status)
update_manager.no_update.connect(main_window.show_no_update)
update_manager.error.connect(main_window.show_update_error)
update_manager.update_available.connect(main_window.show_update_available)
update_manager.downloaded.connect(main_window.show_update_downloaded)
update_manager.restart_requested.connect(app.quit)

app.aboutToQuit.connect(agent_worker.cleanup)
app.aboutToQuit.connect(agent_thread.quit)
app.aboutToQuit.connect(agent_thread.wait)

agent_thread.start()
update_manager.start_listener()

main_window.show()
sys.exit(app.exec())
