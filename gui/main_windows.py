import os
import re
from html import escape

from PySide6.QtCore import QObject, QTimer, QSize, Qt, Signal, Slot
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from config import MODEL, SCOUT_BACKEND, get_settings_path, get_runtime_settings, load_user_settings, save_user_settings

try:
    import qtawesome as qta
except Exception:
    qta = None

try:
    import markdown
except Exception:
    markdown = None


def _load_webengine_dialog_classes():
    try:
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except Exception:
        return None, None
    return QWebChannel, QWebEngineView


class PromptEdit(QPlainTextEdit):
    submit_requested = Signal()

    def __init__(self):
        super().__init__()
        self.document().setDocumentMargin(0)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(42)
        self.setMaximumHeight(96)
        self.textChanged.connect(self._resize_to_content)
        QTimer.singleShot(0, self._resize_to_content)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        is_enter = event.key() in (Qt.Key_Return, Qt.Key_Enter)
        if is_enter and not event.modifiers() & Qt.ShiftModifier:
            self.submit_requested.emit()
            return
        super().keyPressEvent(event)

    def _resize_to_content(self) -> None:
        document_height = int(self.document().size().height())
        margins = self.contentsMargins()
        target_height = max(42, min(96, document_height + margins.top() + margins.bottom() + 18))
        self.setFixedHeight(target_height)


class MainWindow(QMainWindow):
    prompt_submitted = Signal(str)
    stop_requested = Signal()
    command_confirmation_resolved = Signal(bool)
    update_check_requested = Signal()
    update_download_requested = Signal(dict)
    update_apply_requested = Signal(dict)
    settings_saved = Signal()
    tool_approval_mode_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scout")
        self.resize(1180, 760)
        self.setMinimumSize(960, 620)
        self.setFont(QFont("Inter", 10))

        self._chat_items = []
        self._left_panel_visible = True

        self._build_ui()
        self._apply_button_icons()
        self._connect_signals()
        self._apply_styles()

        self._conversation_count = 0
        self._busy = False
        self._stop_message_shown = False
        self._new_conversation()
        self.set_status("")

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        self.sidebar_panel = self._build_sidebar()
        self.sidebar_panel.setFixedWidth(260)

        content_layout.addWidget(self.sidebar_panel)
        content_layout.addWidget(self._build_chat_panel(), 1)
        root_layout.addLayout(content_layout, 1)

        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("sidePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        heading = QLabel("Conversations")
        heading.setObjectName("panelHeading")

        self.conversation_list = QListWidget()
        self.conversation_list.setObjectName("conversationList")

        self.new_chat_button = QPushButton()
        self.new_chat_button.setObjectName("primaryButton")
        self.new_chat_button.setToolTip("New conversation")
        self.new_chat_button.setAccessibleName("New conversation")
        self.new_chat_button.setFixedHeight(42)

        self.settings_button = QPushButton()
        self.settings_button.setObjectName("secondaryButton")
        self.settings_button.setToolTip("Settings")
        self.settings_button.setAccessibleName("Settings")
        self.settings_button.setFixedHeight(42)

        layout.addWidget(heading)
        layout.addWidget(self.conversation_list, 1)
        layout.addWidget(self.new_chat_button)
        layout.addWidget(self.settings_button)
        return panel

    def _build_chat_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("chatPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.menu_button = QPushButton()
        self.menu_button.setObjectName("secondaryButton")
        self.menu_button.setToolTip("Show or hide conversations")
        self.menu_button.setAccessibleName("Show or hide conversations")
        self.menu_button.setFixedSize(42, 38)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusPill")

        header_layout.addWidget(self.menu_button)
        header_layout.addStretch(1)
        header_layout.addWidget(self.status_label)

        self.chat_browser = QTextBrowser()
        self.chat_browser.setObjectName("chatBrowser")
        self.chat_browser.setOpenExternalLinks(True)
        self.chat_browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(8)

        self.prompt_edit = PromptEdit()
        self.prompt_edit.setObjectName("promptEdit")
        self.prompt_edit.setPlaceholderText("Ask the agent...")

        self.input_model_label = QLabel(f"{SCOUT_BACKEND}: {MODEL}")
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

        layout.addLayout(header_layout)
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

    def _submit_prompt(self) -> None:
        if self._busy:
            self.stop_requested.emit()
            self.append_system_note("Stop requested.")
            self.show_stopped()
            return

        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            return

        self.prompt_edit.clear()
        self.append_message("user", prompt)
        self.set_busy(True)
        self.prompt_submitted.emit(prompt)

    def _emit_tool_approval_mode(self) -> None:
        self.tool_approval_mode_changed.emit(self.tool_approval_combo.currentData())
        if self.tool_approval_combo.currentData() == "approve_all":
            self.append_system_note("Tool execution approval: approve all.")
        else:
            self.append_system_note("Tool execution approval: ask approval.")

    def _new_conversation(self) -> None:
        self._conversation_count += 1
        title = f"New chat {self._conversation_count}"
        self.conversation_list.addItem(title)
        self.conversation_list.setCurrentRow(self.conversation_list.count() - 1)
        self._chat_items = []
        self._render_chat_html()
        self.append_system_note("New conversation started.")

    def append_message(self, role: str, content: str) -> None:
        css_class = "userMessage" if role == "user" else "agentMessage"
        content_html = self._message_content_html(role, content)
        html = (
            f"<div class='messageRow {role}Row'>"
            f"<div class='message {css_class}'>"
            f"<div class='messageText'>{content_html}</div>"
            "</div>"
            "</div>"
        )
        self._append_chat_html(html)

    def append_system_note(self, content: str) -> None:
        html = f"<div class='systemNote'>{escape(content)}</div>"
        self._append_chat_html(html)

    def append_tool_log(self, content: str) -> None:
        self.append_system_note(f"Tool: {content}")

    def append_pdf_note(self, content: str) -> None:
        self.append_system_note(f"PDF: {content}")

    def append_log(self, content: str) -> None:
        self.append_system_note(content)

    def append_flow_event(self, content: str) -> None:
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
        self.append_system_note(f"Update: {message}")

    def show_no_update(self, message: str) -> None:
        self.append_system_note(message)

    def show_update_error(self, message: str) -> None:
        self.append_system_note(f"Update error: {message}")

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

    def show_command_confirmation(self, command: str) -> None:
        dialog = CommandConfirmDialog(command, self)
        self.command_confirmation_resolved.emit(dialog.exec() == QDialog.Accepted)

    def show_agent_response(self, response: str) -> None:
        self.append_message("assistant", response)
        self.set_busy(False)

    def show_error(self, message: str) -> None:
        self.append_system_note(f"Error: {message}")
        self.append_log(f"Error: {message}")
        self.set_busy(False)

    def show_stopped(self) -> None:
        if self._stop_message_shown:
            return
        self._stop_message_shown = True
        self.append_system_note("Request stopped.")
        self.set_busy(False)

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
        self.set_status("Thinking..." if busy else "")

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))

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

    def _message_content_html(self, role: str, content: str) -> str:
        if role == "assistant":
            return self._markdown_to_html(content)
        return escape(content).replace("\n", "<br>")

    def _markdown_to_html(self, content: str) -> str:
        if markdown:
            return markdown.markdown(
                content,
                extensions=["fenced_code", "tables", "nl2br"],
                output_format="html5",
            )
        return self._basic_markdown_to_html(content)

    def _basic_markdown_to_html(self, content: str) -> str:
        escaped = escape(content)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"(?m)^### (.+)$", r"<h3>\1</h3>", escaped)
        escaped = re.sub(r"(?m)^## (.+)$", r"<h2>\1</h2>", escaped)
        escaped = re.sub(r"(?m)^# (.+)$", r"<h1>\1</h1>", escaped)
        return escaped.replace("\n", "<br>")

    def _append_chat_html(self, html: str) -> None:
        self._chat_items.append(html)
        self._render_chat_html()
        scrollbar = self.chat_browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _render_chat_html(self) -> None:
        items_html = "\n".join(self._chat_items)
        self.chat_browser.setHtml(
            f"""
            <!doctype html>
            <html>
            <head>
            <style>
                body {{
                    margin: 0;
                    background: #1E242A;
                    color: #F4F4F5;
                    font-family: Inter, "Segoe UI", Roboto, Arial, sans-serif;
                }}
                table.chatWrap {{
                    margin-left: auto;
                    margin-right: auto;
                }}
                .messageRow {{
                    margin: 12px 0;
                }}
                .userRow {{
                    text-align: right;
                }}
                .assistantRow {{
                    text-align: center;
                }}
                .message {{
                    padding: 12px;
                    border-radius: 8px;
                    display: inline-block;
                }}
                .userMessage {{
                    background: #333C46;
                    border: 1px solid #FF4D00;
                    max-width: 62%;
                    text-align: left;
                }}
                .agentMessage {{
                    background: transparent;
                    border: 0;
                    max-width: 78%;
                    text-align: left;
                }}
                .messageText {{
                    color: #F4F4F5;
                    line-height: 1.35;
                }}
                .messageText p {{
                    margin: 0 0 12px 0;
                }}
                .messageText p:last-child {{
                    margin-bottom: 0;
                }}
                .messageText pre {{
                    background: #12171C;
                    border: 1px solid #56616D;
                    border-radius: 8px;
                    overflow-x: auto;
                    padding: 12px;
                    white-space: pre-wrap;
                }}
                .messageText code {{
                    background: #12171C;
                    border-radius: 4px;
                    color: #FFD2C2;
                    font-family: "JetBrains Mono", "Fira Code", monospace;
                    padding: 2px 4px;
                }}
                .messageText pre code {{
                    background: transparent;
                    padding: 0;
                }}
                .messageText h1, .messageText h2, .messageText h3 {{
                    color: #FFFFFF;
                    margin: 12px 0 8px 0;
                }}
                .messageText ul, .messageText ol {{
                    margin: 8px 0 12px 24px;
                }}
                .messageText blockquote {{
                    border-left: 3px solid #FF4D00;
                    color: #DADDE1;
                    margin: 10px 0;
                    padding-left: 12px;
                }}
                .agentMessage .messageText {{
                    font-size: 20px;
                    line-height: 1.5;
                }}
                .userMessage .messageText {{
                    font-size: 14px;
                }}
                .systemNote {{
                    color: #B8C0C8;
                    font-style: italic;
                    margin: 10px 0;
                    text-align: center;
                }}
            </style>
            </head>
            <body>
                <table class="chatWrap" width="78%" cellspacing="0" cellpadding="0" align="center">
                    <tr><td>{items_html}</td></tr>
                </table>
            </body>
            </html>
            """
        )

    def _toggle_left_panel(self) -> None:
        self._left_panel_visible = not self._left_panel_visible
        self.sidebar_panel.setVisible(self._left_panel_visible)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #414B56;
                color: #F4F4F5;
                font-family: Inter, "Segoe UI", Roboto, Arial, sans-serif;
            }
            QWidget {
                color: #F4F4F5;
                font-family: Inter, "Segoe UI", Roboto, Arial, sans-serif;
            }
            QFrame#sidePanel,
            QFrame#chatPanel {
                background: #252C33;
                border: 1px solid #56616D;
                border-radius: 8px;
            }
            QLabel#appTitle {
                font-size: 18px;
                font-weight: 700;
                color: #FFFFFF;
            }
            QLabel#panelHeading {
                font-size: 13px;
                font-weight: 700;
                color: #F4F4F5;
            }
            QLabel#inputModelLabel {
                color: #B8C0C8;
                font-size: 12px;
                padding-left: 4px;
            }
            QLabel#statusPill {
                background: #333C46;
                color: #FFFFFF;
                border: 1px solid #56616D;
                border-radius: 10px;
                padding: 4px 10px;
                font-weight: 600;
            }
            QListWidget,
            QTextBrowser,
            QPlainTextEdit,
            QComboBox {
                background: #1E242A;
                color: #F4F4F5;
                border: 1px solid #56616D;
                border-radius: 6px;
                padding: 6px;
                selection-background-color: #FF4D00;
            }
            QPlainTextEdit#promptEdit {
                padding: 9px 10px;
            }
            QComboBox#toolApprovalCombo {
                color: #F4F4F5;
                background: #252C33;
                border: 1px solid #56616D;
                border-radius: 6px;
                padding: 4px 8px;
                min-width: 132px;
            }
            QComboBox#toolApprovalCombo:hover {
                background: #333C46;
            }
            QComboBox#toolApprovalCombo::drop-down {
                border: 0;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background: #252C33;
                color: #F4F4F5;
                border: 1px solid #56616D;
                selection-background-color: #FF4D00;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 5px;
            }
            QListWidget::item:selected {
                background: #333C46;
                color: #FFFFFF;
                border: 1px solid #56616D;
            }
            QFrame#inputFrame {
                background: #1E242A;
                border: 1px solid #56616D;
                border-radius: 8px;
            }
            QPushButton {
                color: #F4F4F5;
                background: #333C46;
                border: 1px solid #56616D;
                border-radius: 6px;
                padding: 8px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #414B56;
            }
            QPushButton:disabled {
                color: #89939E;
                background: #252C33;
            }
            QPushButton#primaryButton {
                color: #FFFFFF;
                background: #FF4D00;
                border-color: #FF4D00;
            }
            QPushButton#primaryButton:hover {
                background: #E64500;
            }
            QPushButton#secondaryButton {
                color: #F4F4F5;
                background: #252C33;
                border-color: #56616D;
            }
            QPushButton#secondaryButton:hover {
                background: #414B56;
            }
            QPushButton#stopButton {
                color: #FFFFFF;
                background: #B91C1C;
                border-color: #B91C1C;
            }
            QPushButton#stopButton:hover {
                background: #991B1B;
            }
            .messageRow {
                margin: 12px 0;
            }
            .userRow {
                text-align: right;
            }
            .assistantRow {
                text-align: center;
            }
            .message {
                margin: 10px 0;
                padding: 10px;
                border-radius: 8px;
            }
            .userMessage {
                background: #333C46;
                border: 1px solid #FF4D00;
            }
            .agentMessage {
                background: transparent;
                border: 0;
            }
            .messageText {
                color: #F4F4F5;
                line-height: 1.35;
            }
            .agentMessage .messageText {
                font-size: 20px;
                line-height: 1.5;
            }
            .systemNote {
                color: #B8C0C8;
                font-style: italic;
                margin: 8px 0;
            }
            """
        )


exports = MainWindow


class SettingsDialog(QDialog):
    update_check_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(560, 280)

        runtime = get_runtime_settings()
        user_settings = load_user_settings()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("OpenRouter")
        title.setObjectName("panelHeading")

        self.api_key_input = QLineEdit()
        self.api_key_input.setObjectName("settingsInput")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("OpenRouter API key")
        self.api_key_input.setText(user_settings.get("openrouter_api_key", ""))

        active_key_label = QLabel("Configured" if runtime.get("openrouter_api_key") else "Not configured")
        active_key_label.setObjectName("settingsHint")

        path_label = QLabel(f"Saved locally: {get_settings_path()}")
        path_label.setObjectName("settingsHint")
        path_label.setWordWrap(True)

        if "OPENROUTER_API_KEY" in os.environ:
            env_label = QLabel("OPENROUTER_API_KEY is set in the environment and overrides the saved key.")
            env_label.setObjectName("settingsHint")
            env_label.setWordWrap(True)
        else:
            env_label = None

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        check_updates_button = QPushButton("Check updates")
        check_updates_button.setObjectName("secondaryButton")
        check_updates_button.clicked.connect(self.update_check_requested.emit)

        clear_button = QPushButton("Clear key")
        clear_button.setObjectName("secondaryButton")
        clear_button.clicked.connect(self._clear_key)

        action_row.addWidget(check_updates_button)
        action_row.addStretch(1)
        action_row.addWidget(clear_button)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch(1)

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        save_button = QPushButton("Save")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)

        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout.addWidget(title)
        layout.addWidget(active_key_label)
        layout.addWidget(self.api_key_input)
        layout.addWidget(path_label)
        if env_label:
            layout.addWidget(env_label)
        layout.addLayout(action_row)
        layout.addStretch(1)
        layout.addLayout(button_row)

        self.setStyleSheet(
            """
            QDialog {
                background: #252C33;
                color: #F4F4F5;
            }
            QLabel#panelHeading {
                font-size: 15px;
                font-weight: 700;
                color: #FFFFFF;
            }
            QLabel#settingsHint {
                color: #B8C0C8;
                font-size: 12px;
            }
            QLineEdit#settingsInput {
                background: #1E242A;
                color: #F4F4F5;
                border: 1px solid #56616D;
                border-radius: 6px;
                padding: 10px;
                selection-background-color: #FF4D00;
            }
            QPushButton {
                color: #F4F4F5;
                background: #333C46;
                border: 1px solid #56616D;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton#primaryButton {
                color: #FFFFFF;
                background: #FF4D00;
                border-color: #FF4D00;
            }
            QPushButton#secondaryButton {
                color: #F4F4F5;
                background: #252C33;
                border-color: #56616D;
            }
            """
        )

    def _clear_key(self) -> None:
        self.api_key_input.clear()

    def _save(self) -> None:
        save_user_settings({"openrouter_api_key": self.api_key_input.text().strip()})
        self.accept()


class CommandConfirmDialog(QDialog):
    def __init__(self, command: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm command")
        self.setModal(True)
        self.resize(620, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        html = f"""
            <!doctype html>
            <html>
            <head>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <script>
                let bridge = null;
                document.addEventListener("DOMContentLoaded", function() {{
                    if (typeof QWebChannel !== "undefined" && window.qt) {{
                        new QWebChannel(qt.webChannelTransport, function(channel) {{
                            bridge = channel.objects.bridge;
                        }});
                    }}
                }});
                function approveCommand() {{
                    if (bridge) bridge.approve();
                }}
                function denyCommand() {{
                    if (bridge) bridge.deny();
                }}
            </script>
            <style>
                body {{
                    background: #252C33;
                    color: #F4F4F5;
                    font-family: system-ui, sans-serif;
                    margin: 0;
                }}
                .title {{
                    color: #FFFFFF;
                    font-size: 22px;
                    font-weight: 700;
                    margin-bottom: 8px;
                }}
                .subtitle {{
                    color: #B8C0C8;
                    font-size: 13px;
                    margin-bottom: 16px;
                }}
                .command {{
                    background: #1E242A;
                    border: 1px solid #FF4D00;
                    border-radius: 8px;
                    color: #FFFFFF;
                    font-family: monospace;
                    font-size: 14px;
                    padding: 12px;
                    white-space: pre-wrap;
                }}
                .warning {{
                    color: #FFB199;
                    margin-top: 14px;
                    font-size: 13px;
                }}
                .actions {{
                    display: flex;
                    justify-content: flex-end;
                    gap: 10px;
                    margin-top: 22px;
                }}
                button {{
                    border-radius: 6px;
                    border: 1px solid #56616D;
                    cursor: pointer;
                    font-weight: 700;
                    padding: 10px 16px;
                }}
                .deny {{
                    background: #252C33;
                    color: #F4F4F5;
                }}
                .approve {{
                    background: #FF4D00;
                    border-color: #FF4D00;
                    color: #FFFFFF;
                }}
            </style>
            </head>
            <body>
                <div class="title">Command approval</div>
                <div class="subtitle">Scout wants to run this command on your machine.</div>
                <div class="command">{escape(command)}</div>
                <div class="warning">Only approve this if you understand the command and trust the current task.</div>
                <div class="actions">
                    <button class="deny" onclick="denyCommand()">Deny</button>
                    <button class="approve" onclick="approveCommand()">Approve</button>
                </div>
            </body>
            </html>
            """

        QWebChannel, QWebEngineView = _load_webengine_dialog_classes()
        if QWebEngineView and QWebChannel:
            self._bridge = CommandConfirmBridge(self)
            self._channel = QWebChannel(self)
            self._channel.registerObject("bridge", self._bridge)
            body = QWebEngineView()
            body.page().setWebChannel(self._channel)
            body.setHtml(html)
            layout.addWidget(body, 1)
        else:
            body = QTextBrowser()
            body.setObjectName("commandDialogBody")
            body.setOpenExternalLinks(False)
            body.setHtml(html)

            button_row = QHBoxLayout()
            button_row.addStretch(1)

            deny_button = QPushButton("Deny")
            deny_button.setObjectName("secondaryButton")
            deny_button.clicked.connect(self.reject)

            approve_button = QPushButton("Approve")
            approve_button.setObjectName("primaryButton")
            approve_button.clicked.connect(self.accept)

            button_row.addWidget(deny_button)
            button_row.addWidget(approve_button)

            layout.addWidget(body, 1)
            layout.addLayout(button_row)

        self.setStyleSheet(
            """
            QDialog {
                background: #252C33;
            }
            QTextBrowser#commandDialogBody {
                background: #252C33;
                border: 0;
            }
            QPushButton {
                color: #F4F4F5;
                background: #333C46;
                border: 1px solid #56616D;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton#primaryButton {
                color: #FFFFFF;
                background: #FF4D00;
                border-color: #FF4D00;
            }
            QPushButton#secondaryButton {
                color: #F4F4F5;
                background: #252C33;
                border-color: #56616D;
            }
            """
        )


class CommandConfirmBridge(QObject):
    def __init__(self, dialog: CommandConfirmDialog):
        super().__init__(dialog)
        self.dialog = dialog

    @Slot()
    def approve(self) -> None:
        self.dialog.accept()

    @Slot()
    def deny(self) -> None:
        self.dialog.reject()
