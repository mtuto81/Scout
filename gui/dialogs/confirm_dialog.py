import os
from html import escape

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


def _load_webengine_dialog_classes():
    if os.environ.get("SCOUT_ENABLE_WEBENGINE_DIALOG") != "1":
        return None, None

    try:
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except Exception:
        return None, None
    return QWebChannel, QWebEngineView


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
