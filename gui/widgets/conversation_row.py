from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from datetime import datetime

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget, QVBoxLayout


class TrashButton(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("conversationDeleteButton")
        self.setToolTip("Delete conversation")
        self.setAccessibleName("Delete conversation")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(26, 26)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.underMouse():
            painter.setBrush(QColor("#B91C1C"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(self.rect(), 6, 6)

        color = QColor("#FFFFFF" if self.underMouse() else "#D6DEE6")
        painter.setPen(QPen(color, 1.6))
        painter.setBrush(Qt.NoBrush)
        x = (self.width() - 20) // 2
        y = (self.height() - 20) // 2
        painter.drawRoundedRect(x + 6, y + 6, 8, 11, 1.5, 1.5)
        painter.drawLine(x + 5, y + 5, x + 15, y + 5)
        painter.drawLine(x + 8, y + 3, x + 12, y + 3)
        painter.drawLine(x + 8, y + 8, x + 8, y + 14)
        painter.drawLine(x + 12, y + 8, x + 12, y + 14)
        painter.end()


class ConversationRowWidget(QWidget):
    activated = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, conversation_id: int, title: str, updated_at: str | None = None, parent=None):
        super().__init__(parent)
        self.conversation_id = conversation_id
        self.setObjectName("conversationRow")
        self.setProperty("selected", False)
        self.setProperty("hovered", False)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 8, 7)
        layout.setSpacing(8)

        accent = QLabel()
        accent.setObjectName("conversationAccent")
        accent.setFixedSize(3, 28)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("conversationTitle")
        self.title_label.setWordWrap(False)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.meta_label = QLabel(self._format_date(updated_at))
        self.meta_label.setObjectName("conversationMeta")
        self.meta_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.meta_label)

        self.delete_button = TrashButton()
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.conversation_id))
        self.installEventFilter(self)
        for child in (self.title_label, self.meta_label, self.delete_button):
            child.installEventFilter(self)

        layout.addWidget(accent)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self.delete_button, 0, Qt.AlignRight)

    @staticmethod
    def _format_date(value: str | None) -> str:
        if not value:
            return "New conversation"
        try:
            return datetime.fromisoformat(value).strftime("%b %d, %Y")
        except ValueError:
            return "Conversation"

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.conversation_id)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self.setProperty("hovered", True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hovered", False)
        self.update()
        super().leaveEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Enter:
            self.setProperty("hovered", True)
            self.update()
        elif event.type() == QEvent.Leave:
            inside = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
            self.setProperty("hovered", inside)
            self.update()
        return super().eventFilter(watched, event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        selected = bool(self.property("selected"))
        hovered = bool(self.property("hovered"))
        fill = QColor("#333C46" if selected else "#2D3741" if hovered else "#252C33")
        border = QColor("#FF6A2A" if selected else "#7B8794" if hovered else "#3A444E")
        painter.setBrush(fill)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 9, 9)
        painter.end()

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
