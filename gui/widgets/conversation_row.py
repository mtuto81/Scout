from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget, QMenu


class ConversationRowWidget(QWidget):
    activated = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, conversation_id: int, title: str, parent=None):
        super().__init__(parent)
        self.conversation_id = conversation_id
        self.setObjectName("conversationRow")
        self.setProperty("selected", False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("conversationTitle")
        self.title_label.setWordWrap(False)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.menu_button = QToolButton()
        self.menu_button.setObjectName("conversationMenuButton")
        self.menu_button.setText("...")
        self.menu_button.setToolTip("Conversation menu")
        self.menu_button.setAccessibleName("Conversation menu")
        self.menu_button.setCursor(Qt.PointingHandCursor)
        self.menu_button.setAutoRaise(True)
        self.menu_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.menu_button.setFixedSize(28, 28)
        self.menu_button.clicked.connect(self._show_menu)

        layout.addWidget(self.title_label, 1)
        layout.addWidget(self.menu_button, 0, Qt.AlignRight)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.conversation_id)
        super().mouseReleaseEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self.conversation_id))
        menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))
