from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from config import get_runtime_settings
from gui.conversation_store import ConversationStore
from gui.dialogs.settings_dialog import SettingsDialog
from gui.dialogs.confirm_dialog import CommandConfirmDialog
from gui.transcript import CHAT_CSS, message_html, system_note_html
from gui.window_styles import MAIN_WINDOW_STYLE
from gui.widgets.conversation_row import ConversationRowWidget
from gui.widgets.prompt_edit import PromptEdit

try:
    import qtawesome as qta
except Exception:
    qta = None


class MainWindow(QMainWindow):
    prompt_submitted = Signal(str, int)
    stop_requested = Signal()
    command_confirmation_resolved = Signal(bool)
    file_operation_confirmation_resolved = Signal(bool)
    update_check_requested = Signal()
    update_download_requested = Signal(dict)
    update_apply_requested = Signal(dict)
    settings_saved = Signal()
    tool_approval_mode_changed = Signal(str)
    conversation_context_changed = Signal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scout")
        self.resize(1180, 760)
        self.setMinimumSize(960, 620)
        self.setFont(QFont("Inter", 10))

        self._left_panel_visible = True
        self._sidebar_expanded_width = 260
        self._sidebar_collapsed_width = 54
        self._store = ConversationStore()
        self._current_conversation_id = None
        self._loading_conversation = False
        self._active_request_conversation_id = None

        self._build_ui()
        self._apply_button_icons()
        self._connect_signals()
        self._apply_styles()

        self._busy = False
        self._stop_message_shown = False
        self._load_conversations()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        self.sidebar_panel = self._build_sidebar()
        self.sidebar_panel.setFixedWidth(self._sidebar_expanded_width)

        content_layout.addWidget(self.sidebar_panel)
        content_layout.addWidget(self._build_chat_panel(), 1)
        root_layout.addLayout(content_layout, 1)

        self.setCentralWidget(root)
        self._build_bottom_alert()

    def _build_bottom_alert(self) -> None:
        self.bottom_alert = QFrame(self.centralWidget())
        self.bottom_alert.setObjectName("bottomAlert")
        self.bottom_alert.setVisible(False)

        alert_layout = QHBoxLayout(self.bottom_alert)
        alert_layout.setContentsMargins(14, 10, 10, 10)
        alert_layout.setSpacing(10)

        self.bottom_alert_label = QLabel()
        self.bottom_alert_label.setObjectName("bottomAlertLabel")
        self.bottom_alert_label.setWordWrap(True)

        self.bottom_alert_close = QPushButton("x")
        self.bottom_alert_close.setObjectName("bottomAlertClose")
        self.bottom_alert_close.setToolTip("Dismiss")
        self.bottom_alert_close.setAccessibleName("Dismiss alert")
        self.bottom_alert_close.setFixedSize(26, 26)
        self.bottom_alert_close.clicked.connect(self.bottom_alert.hide)

        alert_layout.addWidget(self.bottom_alert_label, 1)
        alert_layout.addWidget(self.bottom_alert_close, 0, Qt.AlignTop)

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("sidePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        heading = QLabel("Conversations")
        heading.setObjectName("panelHeading")

        self.menu_button = QPushButton()
        self.menu_button.setObjectName("secondaryButton")
        self.menu_button.setToolTip("Show or hide conversations")
        self.menu_button.setAccessibleName("Show or hide conversations")
        self.menu_button.setFixedSize(34, 34)

        heading_layout = QHBoxLayout()
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(8)
        heading_layout.addWidget(self.menu_button)
        heading_layout.addWidget(heading, 1)

        self.conversation_list = QListWidget()
        self.conversation_list.setObjectName("conversationList")

        self.new_chat_button = QPushButton("New conversation")
        self.new_chat_button.setObjectName("primaryButton")
        self.new_chat_button.setToolTip("New conversation")
        self.new_chat_button.setAccessibleName("New conversation")
        self.new_chat_button.setFixedHeight(42)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setObjectName("secondaryButton")
        self.settings_button.setToolTip("Settings")
        self.settings_button.setAccessibleName("Settings")
        self.settings_button.setFixedHeight(42)

        self._sidebar_expanded_widgets = (
            heading,
            self.conversation_list,
        )

        layout.addLayout(heading_layout)
        layout.addWidget(self.conversation_list, 1)
        layout.addStretch(1)
        layout.addWidget(self.new_chat_button)
        layout.addWidget(self.settings_button)
        return panel

    def _build_chat_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("chatPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.chat_browser = QTextBrowser()
        self.chat_browser.setObjectName("chatBrowser")
        self.chat_browser.setOpenExternalLinks(True)
        self.chat_browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.chat_browser.setStyleSheet("background: #414B56; border: 0;")
        self.chat_browser.viewport().setStyleSheet("background: #414B56;")

        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(8)

        self.prompt_edit = PromptEdit()
        self.prompt_edit.setObjectName("promptEdit")
        self.prompt_edit.setPlaceholderText("Ask me anything.")

        runtime = get_runtime_settings()
        self.input_model_label = QLabel(f"{runtime['backend']}: {runtime['model']}")
        self.input_model_label.setObjectName("inputModelLabel")

        self.tool_approval_combo = QComboBox()
        self.tool_approval_combo.setObjectName("toolApprovalCombo")
        self.tool_approval_combo.setToolTip("Tool execution approval")
        self.tool_approval_combo.setAccessibleName("Tool execution approval")
        self.tool_approval_combo.addItem("Ask approval", "ask")
        self.tool_approval_combo.addItem("Approve all", "approve_all")
        self.tool_approval_combo.setFixedHeight(28)

        input_meta_layout = QHBoxLayout()
        input_meta_layout.setContentsMargins(0, 0, 0, 0)
        input_meta_layout.setSpacing(8)
        input_meta_layout.addWidget(self.input_model_label)
        input_meta_layout.addStretch(1)
        input_meta_layout.addWidget(self.tool_approval_combo)

        input_text_layout = QVBoxLayout()
        input_text_layout.setContentsMargins(0, 0, 0, 0)
        input_text_layout.setSpacing(6)
        input_text_layout.addWidget(self.prompt_edit)
        input_text_layout.addLayout(input_meta_layout)

        self.send_button = QPushButton()
        self.send_button.setObjectName("primaryButton")
        self.send_button.setToolTip("Send")
        self.send_button.setAccessibleName("Send")
        self.send_button.setFixedSize(42, 42)

        input_layout.addLayout(input_text_layout, 1)
        input_layout.addWidget(self.send_button, 0, Qt.AlignTop)

        layout.addWidget(self.chat_browser, 1)
        layout.addWidget(input_frame)
        return panel

    def _connect_signals(self) -> None:
        self.send_button.clicked.connect(self._submit_prompt)
        self.prompt_edit.submit_requested.connect(self._submit_prompt)
        self.new_chat_button.clicked.connect(self._new_conversation)
        self.menu_button.clicked.connect(self._toggle_left_panel)
        self.settings_button.clicked.connect(self._open_settings_dialog)
        self.tool_approval_combo.currentIndexChanged.connect(self._emit_tool_approval_mode)
        self.conversation_list.currentItemChanged.connect(self._conversation_selected)

    def _submit_prompt(self) -> None:
        if self._busy:
            conversation_id = self._active_request_conversation_id
            self.stop_requested.emit()
            self.append_flow_event("Stop requested.", conversation_id or -1)
            self.show_stopped(conversation_id)
            return

        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            return

        if self._current_conversation_id is None:
            self._create_conversation(select=True)

        conversation_id = self._current_conversation_id
        self._emit_conversation_context(conversation_id)
        self._active_request_conversation_id = conversation_id
        self.prompt_edit.clear()
        self.append_message("user", prompt)
        self._store.add_message(conversation_id, "user", prompt)
        title = self._store.maybe_title_from_first_user_message(conversation_id, prompt)
        if title:
            self._update_conversation_title(conversation_id, title)
        self.set_busy(True)
        self.prompt_submitted.emit(prompt, conversation_id)

    def _emit_tool_approval_mode(self) -> None:
        self.tool_approval_mode_changed.emit(self.tool_approval_combo.currentData())
        if self.tool_approval_combo.currentData() == "approve_all":
            self.append_system_note("Tool execution approval: approve all.")
        else:
            self.append_system_note("Tool execution approval: ask approval.")

    def _new_conversation(self) -> None:
        self._create_conversation(select=True)

    def _create_conversation(self, select: bool) -> int:
        conversation_id = self._store.create_conversation()
        self._load_conversations(select_conversation_id=conversation_id)
        if select:
            self.chat_browser.clear()
            self.append_system_note("New conversation started.")
        return conversation_id

    def _load_conversations(self, select_conversation_id: int | None = None) -> None:
        self._loading_conversation = True
        self.conversation_list.clear()

        conversations = self._store.list_conversations()
        for conversation in conversations:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, conversation["id"])
            item.setSizeHint(QSize(0, 42))
            self.conversation_list.addItem(item)

            row = ConversationRowWidget(conversation["id"], conversation["title"], self.conversation_list)
            row.activated.connect(self._select_conversation_by_id)
            row.delete_requested.connect(self._delete_conversation)
            self.conversation_list.setItemWidget(item, row)

        self._loading_conversation = False

        if not conversations:
            conversation_id = self._store.create_conversation()
            self._load_conversations(select_conversation_id=conversation_id)
            return

        target_id = select_conversation_id or conversations[0]["id"]
        self._update_conversation_row_selection(target_id)
        for row in range(self.conversation_list.count()):
            item = self.conversation_list.item(row)
            if item.data(Qt.UserRole) == target_id:
                self.conversation_list.setCurrentRow(row)
                return

    def _conversation_selected(self, current, previous) -> None:
        if self._loading_conversation or current is None:
            return

        conversation_id = current.data(Qt.UserRole)
        if conversation_id == self._current_conversation_id:
            return

        self._current_conversation_id = conversation_id
        self._update_conversation_row_selection(conversation_id)
        self.chat_browser.clear()
        for message in self._store.get_messages(conversation_id):
            if message["role"] in ("user", "assistant"):
                self.append_message(message["role"], message["content"], persist=False)
        self._emit_conversation_context(conversation_id)

    def _select_conversation_by_id(self, conversation_id: int) -> None:
        for row in range(self.conversation_list.count()):
            item = self.conversation_list.item(row)
            if item.data(Qt.UserRole) == conversation_id:
                self.conversation_list.setCurrentRow(row)
                return

    def _delete_conversation(self, conversation_id: int) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Conversation",
            "Delete this conversation?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if not self._store.delete_conversation(conversation_id):
            return

        if self._current_conversation_id == conversation_id:
            self._current_conversation_id = None
            self.chat_browser.clear()

        self._load_conversations()

    def _update_conversation_title(self, conversation_id: int, title: str) -> None:
        for row in range(self.conversation_list.count()):
            item = self.conversation_list.item(row)
            if item.data(Qt.UserRole) != conversation_id:
                continue
            widget = self.conversation_list.itemWidget(item)
            if widget and hasattr(widget, "set_title"):
                widget.set_title(title)
            break

    def _emit_conversation_context(self, conversation_id: int) -> None:
        messages = [
            {"role": message["role"], "content": message["content"]}
            for message in self._store.get_messages(conversation_id)
            if message["role"] in ("user", "assistant")
        ]
        self.conversation_context_changed.emit(messages)

    def _update_conversation_row_selection(self, selected_id: int | None) -> None:
        for row in range(self.conversation_list.count()):
            item = self.conversation_list.item(row)
            widget = self.conversation_list.itemWidget(item)
            if widget and hasattr(widget, "set_selected"):
                widget.set_selected(item.data(Qt.UserRole) == selected_id)

    def append_message(self, role: str, content: str, persist: bool = False) -> None:
        alignment = Qt.AlignRight if role == "user" else Qt.AlignHCenter
        self._append_chat_html(message_html(role, content), alignment)
        if persist and self._current_conversation_id is not None:
            self._store.add_message(self._current_conversation_id, role, content)

    def append_system_note(self, content: str) -> None:
        self._append_chat_html(system_note_html(content), Qt.AlignHCenter)

    def append_flow_event(self, content: str, conversation_id: int = -1) -> None:
        if conversation_id != -1 and conversation_id != self._current_conversation_id:
            return
        self.append_system_note(content)

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self)
        dialog.update_check_requested.connect(self.update_check_requested.emit)
        if dialog.exec() == QDialog.Accepted:
            runtime = get_runtime_settings()
            self.input_model_label.setText(f"{runtime['backend']}: {runtime['model']}")
            self.settings_saved.emit()
            self.append_system_note("Settings saved.")

    def show_update_status(self, message: str) -> None:
        self.show_bottom_alert(f"Update: {message}")

    def show_no_update(self, message: str) -> None:
        self.show_bottom_alert(message)

    def show_update_error(self, message: str) -> None:
        self.show_bottom_alert(f"Update error: {message}")

    def show_bottom_alert(self, message: str) -> None:
        self.bottom_alert_label.setText(message)
        self.bottom_alert.setVisible(True)
        self._position_bottom_alert()
        self.bottom_alert.raise_()

    def _position_bottom_alert(self) -> None:
        if not hasattr(self, "bottom_alert"):
            return
        parent = self.centralWidget()
        if not parent:
            return

        max_width = max(280, parent.width() - 32)
        width = min(560, max_width)
        self.bottom_alert.setFixedWidth(width)
        height = max(48, self.bottom_alert.sizeHint().height())
        x = (parent.width() - width) // 2
        y = parent.height() - height - 18
        self.bottom_alert.setGeometry(x, y, width, height)

    def show_update_available(self, manifest: dict) -> None:
        latest = manifest.get("version", "unknown")
        current = manifest.get("current_version", "unknown")
        release_url = manifest.get("release_url", "")
        message = f"Scout {latest} is available. Current version: {current}."
        if release_url:
            message += f"\n\nRelease: {release_url}"

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Scout update available")
        dialog.setText(message)
        dialog.setInformativeText("Download and stage this update now?")
        dialog.setIcon(QMessageBox.Information)
        download_button = dialog.addButton("Download", QMessageBox.AcceptRole)
        dialog.addButton("Later", QMessageBox.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == download_button:
            self.update_download_requested.emit(manifest)

    def show_update_downloaded(self, download_info: dict) -> None:
        version = download_info.get("version", "unknown")

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Scout update ready")
        dialog.setText(f"Scout {version} has been downloaded and verified.")
        dialog.setInformativeText("Restart Scout now and apply the update?")
        dialog.setIcon(QMessageBox.Information)
        apply_button = dialog.addButton("Restart and apply", QMessageBox.AcceptRole)
        dialog.addButton("Later", QMessageBox.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == apply_button:
            self.update_apply_requested.emit(download_info)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_bottom_alert()

    def show_command_confirmation(self, command: str) -> None:
        dialog = CommandConfirmDialog(command, self)
        self.command_confirmation_resolved.emit(dialog.exec() == QDialog.Accepted)

    def show_file_operation_confirmation(self, description: str) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Confirm file operation")
        dialog.setText("Scout wants to perform this file operation:")
        dialog.setInformativeText(description)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dialog.setDefaultButton(QMessageBox.No)
        self.file_operation_confirmation_resolved.emit(dialog.exec() == QMessageBox.Yes)

    def show_agent_response(self, response: str, conversation_id: int) -> None:
        self._store.add_message(conversation_id, "assistant", response)
        if conversation_id == self._current_conversation_id:
            self.append_message("assistant", response)
        else:
            self._load_conversations(select_conversation_id=self._current_conversation_id)
        self.set_busy(False)
        self._active_request_conversation_id = None

    def show_error(self, message: str, conversation_id: int = -1) -> None:
        if conversation_id == -1 or conversation_id == self._current_conversation_id:
            self.append_system_note(f"Error: {message}")
        self.set_busy(False)
        if conversation_id == self._active_request_conversation_id:
            self._active_request_conversation_id = None

    def show_stopped(self, conversation_id: int | None = None) -> None:
        if self._stop_message_shown:
            return
        if conversation_id is not None and conversation_id != self._current_conversation_id:
            self.set_busy(False)
            if conversation_id == self._active_request_conversation_id:
                self._active_request_conversation_id = None
            return
        self._stop_message_shown = True
        self.append_system_note("Request stopped.")
        self.set_busy(False)
        if conversation_id == self._active_request_conversation_id:
            self._active_request_conversation_id = None

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self._stop_message_shown = False
        self.prompt_edit.setEnabled(not busy)
        self.send_button.setEnabled(True)
        self.send_button.setObjectName("stopButton" if busy else "primaryButton")
        self.send_button.setToolTip("Stop" if busy else "Send")
        self.send_button.setAccessibleName("Stop" if busy else "Send")
        self.send_button.setIcon(
            self._icon(
                "fa5s.stop" if busy else "fa5s.paper-plane",
                QStyle.StandardPixmap.SP_BrowserStop if busy else QStyle.StandardPixmap.SP_ArrowForward,
                "#FFFFFF",
            )
        )
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)

    def _apply_button_icons(self) -> None:
        self.menu_button.setIcon(self._icon("fa5s.bars", QStyle.StandardPixmap.SP_TitleBarMenuButton))
        self.new_chat_button.setIcon(self._icon("fa5s.plus", QStyle.StandardPixmap.SP_FileIcon, "#FFFFFF"))
        self.settings_button.setIcon(self._icon("fa5s.cog", QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.send_button.setIcon(self._icon("fa5s.paper-plane", QStyle.StandardPixmap.SP_ArrowForward, "#FFFFFF"))
        icon_size = QSize(18, 18)
        for button in (self.menu_button, self.new_chat_button, self.settings_button, self.send_button):
            button.setIconSize(icon_size)

    def _icon(self, icon_name: str, fallback: QStyle.StandardPixmap, color: str = "#F4F4F5"):
        if qta:
            try:
                return qta.icon(icon_name, color=color)
            except Exception:
                pass
        return self._standard_icon(fallback)

    def _standard_icon(self, icon: QStyle.StandardPixmap):
        return self.style().standardIcon(icon)

    def _init_chat_document(self) -> None:
        if self.chat_browser.document().characterCount() > 1:
            return
        self.chat_browser.setHtml(
            f"<!doctype html><html><head><style>{CHAT_CSS}</style></head><body></body></html>"
        )

    def _append_chat_html(self, html: str, alignment: Qt.AlignmentFlag = Qt.AlignLeft) -> None:
        self._init_chat_document()
        cursor = self.chat_browser.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self.chat_browser.document().characterCount() > 1:
            cursor.insertBlock()

        block_format = QTextBlockFormat()
        block_format.setAlignment(alignment)
        cursor.setBlockFormat(block_format)
        cursor.insertHtml(html)

        cursor.insertBlock()
        reset_format = QTextBlockFormat()
        reset_format.setAlignment(Qt.AlignLeft)
        cursor.setBlockFormat(reset_format)
        scrollbar = self.chat_browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _toggle_left_panel(self) -> None:
        self._left_panel_visible = not self._left_panel_visible
        self._sync_sidebar_state()

    def _sync_sidebar_state(self) -> None:
        self.sidebar_panel.setFixedWidth(
            self._sidebar_expanded_width
            if self._left_panel_visible
            else self._sidebar_collapsed_width
        )
        for widget in self._sidebar_expanded_widgets:
            widget.setVisible(self._left_panel_visible)
        if self._left_panel_visible:
            self.new_chat_button.setText("New conversation")
            self.settings_button.setText("Settings")
            for button in (self.new_chat_button, self.settings_button):
                button.setMinimumSize(0, 42)
                button.setMaximumSize(16777215, 42)
        else:
            self.new_chat_button.setText("")
            self.settings_button.setText("")
            for button in (self.new_chat_button, self.settings_button):
                button.setFixedSize(34, 34)

    def _apply_styles(self) -> None:
        self.setStyleSheet(MAIN_WINDOW_STYLE)
