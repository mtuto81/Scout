from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from gui.widgets.conversation_row import ConversationRowWidget


class ConversationListWidget(QWidget):
    """Scrollable conversation list that owns rows and selection state."""

    conversation_selected = Signal(int)
    delete_requested = Signal(int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("conversationList")
        self._selected_id: int | None = None
        self._rows: Dict[int, ConversationRowWidget] = {}

        self._empty_label = QLabel("Your conversations will appear here.")
        self._empty_label.setObjectName("conversationEmptyState")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)

        self._content = QWidget()
        self._content.setObjectName("conversationListContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(2, 2, 2, 2)
        self._content_layout.setSpacing(4)
        self._content_layout.addWidget(self._empty_label)
        self._content_layout.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("conversationScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def clear(self) -> None:
        for row in self._rows.values():
            row.deleteLater()
        self._rows.clear()
        self._selected_id = None
        self._empty_label.setVisible(True)

    def add_conversation(self, conversation_id: int, title: str, updated_at: str | None = None) -> None:
        self._empty_label.setVisible(False)
        row = ConversationRowWidget(conversation_id, title, updated_at, self._content)
        row.activated.connect(self._on_row_activated)
        row.delete_requested.connect(self.delete_requested)
        self._rows[conversation_id] = row
        self._content_layout.insertWidget(self._content_layout.count() - 1, row)

    def _on_row_activated(self, conversation_id: int) -> None:
        self.set_selected(conversation_id)
        self.conversation_selected.emit(conversation_id)

    def set_selected(self, conversation_id: int | None) -> None:
        self._selected_id = conversation_id
        for row_id, row in self._rows.items():
            row.set_selected(row_id == conversation_id)

    def clear_selection(self) -> None:
        self.set_selected(None)

    def row_for(self, conversation_id: int) -> ConversationRowWidget | None:
        return self._rows.get(conversation_id)
