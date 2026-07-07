MAIN_WINDOW_STYLE = """
QMainWindow {
    background: #414B56;
    color: #F4F4F5;
    font-family: Inter, "Segoe UI", Roboto, Arial, sans-serif;
}
QWidget {
    color: #F4F4F5;
    font-family: Inter, "Segoe UI", Roboto, Arial, sans-serif;
}
QFrame#sidePanel {
    background: #252C33;
    border: 1px solid #56616D;
    border-radius: 8px;
}
QFrame#chatPanel {
    background: #414B56;
    border: 0;
    border-radius: 0;
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
QListWidget,
QPlainTextEdit,
QComboBox {
    background: #252C33;
    color: #F4F4F5;
    border: 1px solid #56616D;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #FF4D00;
}
QTextBrowser#chatBrowser {
    background: #414B56;
    border: 0;
    border-radius: 0;
    padding: 0;
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
QWidget#conversationRow {
    background: transparent;
    border: 0;
}
QWidget#conversationRow[selected="true"] {
    background: #333C46;
    border: 1px solid #56616D;
    border-radius: 6px;
}
QLabel#conversationTitle {
    color: #F4F4F5;
}
QToolButton#conversationMenuButton {
    color: #F4F4F5;
    background: transparent;
    border: 0;
    font-size: 18px;
    padding: 0;
}
QToolButton#conversationMenuButton:hover {
    background: #414B56;
    border-radius: 6px;
}
QFrame#inputFrame {
    background: #252C33;
    border: 1px solid #56616D;
    border-radius: 8px;
}
QFrame#bottomAlert {
    background: #FFFFFF;
    border: 1px solid #FFFFFF;
    border-radius: 8px;
}
QLabel#bottomAlertLabel {
    background: #FFFFFF;
    color: #111827;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#bottomAlertClose {
    background: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 13px;
    color: #111827;
    font-weight: 700;
    padding: 0;
}
QPushButton#bottomAlertClose:hover {
    background: #F3F4F6;
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
"""
