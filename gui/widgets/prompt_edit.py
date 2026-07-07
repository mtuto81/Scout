from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPlainTextEdit


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
