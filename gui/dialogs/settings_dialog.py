from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app_metadata import get_version
from config import get_settings_path, get_runtime_settings, load_user_settings, save_user_settings


class SettingsDialog(QDialog):
    update_check_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(680, 520)

        runtime = get_runtime_settings()
        user_settings = load_user_settings()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Backend")
        title.setObjectName("panelHeading")

        version_label = QLabel(f"Scout version {get_version()}")
        version_label.setObjectName("settingsHint")

        backend_row = QHBoxLayout()
        backend_row.setContentsMargins(0, 0, 0, 0)
        backend_row.setSpacing(8)

        backend_label = QLabel("Backend")
        backend_label.setObjectName("settingsHint")

        self.backend_combo = QComboBox()
        self.backend_combo.setObjectName("settingsInput")
        self.backend_combo.addItem("OpenRouter", "openrouter")
        self.backend_combo.addItem("Ollama", "ollama")
        self.backend_combo.addItem("Local llama.cpp", "local")
        backend_index = self.backend_combo.findData(runtime.get("backend", "openrouter"))
        self.backend_combo.setCurrentIndex(max(0, backend_index))

        backend_row.addWidget(backend_label)
        backend_row.addWidget(self.backend_combo, 1)

        self.openrouter_api_input = QLineEdit()
        self.openrouter_api_input.setObjectName("settingsInput")
        self.openrouter_api_input.setEchoMode(QLineEdit.Password)
        self.openrouter_api_input.setPlaceholderText("OpenRouter API key")
        self.openrouter_api_input.setText(user_settings.get("openrouter_api_key", runtime.get("openrouter_api_key", "")))

        self.openrouter_base_input = QLineEdit()
        self.openrouter_base_input.setObjectName("settingsInput")
        self.openrouter_base_input.setPlaceholderText("OpenRouter base URL")
        self.openrouter_base_input.setText(runtime.get("openrouter_base_url", ""))

        self.openrouter_model_input = QLineEdit()
        self.openrouter_model_input.setObjectName("settingsInput")
        self.openrouter_model_input.setPlaceholderText("OpenRouter model")
        self.openrouter_model_input.setText(runtime.get("openrouter_model", ""))

        self.ollama_base_input = QLineEdit()
        self.ollama_base_input.setObjectName("settingsInput")
        self.ollama_base_input.setPlaceholderText("Ollama base URL")
        self.ollama_base_input.setText(runtime.get("ollama_base_url", ""))

        self.ollama_model_input = QLineEdit()
        self.ollama_model_input.setObjectName("settingsInput")
        self.ollama_model_input.setPlaceholderText("Ollama model")
        self.ollama_model_input.setText(runtime.get("ollama_model", ""))

        self.ollama_api_input = QLineEdit()
        self.ollama_api_input.setObjectName("settingsInput")
        self.ollama_api_input.setEchoMode(QLineEdit.Password)
        self.ollama_api_input.setPlaceholderText("Ollama API key")
        self.ollama_api_input.setText(user_settings.get("ollama_api_key", runtime.get("ollama_api_key", "ollama")))

        self.local_model_input = QLineEdit()
        self.local_model_input.setObjectName("settingsInput")
        self.local_model_input.setPlaceholderText("Path to GGUF model")
        self.local_model_input.setText(user_settings.get("local_model_path", runtime.get("local_model_path", "")))

        self.local_ctx_input = QSpinBox()
        self.local_ctx_input.setObjectName("settingsInput")
        self.local_ctx_input.setRange(512, 32768)
        self.local_ctx_input.setSingleStep(256)
        self.local_ctx_input.setValue(int(runtime.get("local_ctx_size", 4096)))

        self.local_max_tokens_input = QSpinBox()
        self.local_max_tokens_input.setObjectName("settingsInput")
        self.local_max_tokens_input.setRange(16, 8192)
        self.local_max_tokens_input.setSingleStep(64)
        self.local_max_tokens_input.setValue(int(runtime.get("local_max_tokens", 768)))

        self.local_threads_input = QSpinBox()
        self.local_threads_input.setObjectName("settingsInput")
        self.local_threads_input.setRange(1, 256)
        self.local_threads_input.setValue(int(runtime.get("local_threads", 1)))

        self.local_gpu_layers_input = QComboBox()
        self.local_gpu_layers_input.setObjectName("settingsInput")
        self.local_gpu_layers_input.addItems(["auto", "0", "8", "16", "32"])
        gpu_layers_index = self.local_gpu_layers_input.findText(str(runtime.get("local_gpu_layers", "auto")))
        self.local_gpu_layers_input.setCurrentIndex(max(0, gpu_layers_index))

        self.openrouter_section = QWidget()
        openrouter_form = QFormLayout(self.openrouter_section)
        openrouter_form.setContentsMargins(0, 0, 0, 0)
        openrouter_form.setSpacing(8)
        openrouter_form.addRow("API key", self.openrouter_api_input)
        openrouter_form.addRow("Base URL", self.openrouter_base_input)
        openrouter_form.addRow("Model", self.openrouter_model_input)

        self.ollama_section = QWidget()
        ollama_form = QFormLayout(self.ollama_section)
        ollama_form.setContentsMargins(0, 0, 0, 0)
        ollama_form.setSpacing(8)
        ollama_form.addRow("Base URL", self.ollama_base_input)
        ollama_form.addRow("Model", self.ollama_model_input)
        ollama_form.addRow("API key", self.ollama_api_input)

        self.local_section = QWidget()
        local_form = QFormLayout(self.local_section)
        local_form.setContentsMargins(0, 0, 0, 0)
        local_form.setSpacing(8)
        local_form.addRow("GGUF model", self.local_model_input)
        local_form.addRow("Context", self.local_ctx_input)
        local_form.addRow("Max tokens", self.local_max_tokens_input)
        local_form.addRow("Threads", self.local_threads_input)
        local_form.addRow("GPU layers", self.local_gpu_layers_input)

        self.backend_hint = QLabel()
        self.backend_hint.setObjectName("settingsHint")
        self.backend_hint.setWordWrap(True)
        self.backend_hint.setText(
            f"Saved locally: {get_settings_path()}\nEnvironment variables still override saved settings."
        )

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        check_updates_button = QPushButton("Check updates")
        check_updates_button.setObjectName("secondaryButton")
        check_updates_button.clicked.connect(self.update_check_requested.emit)

        clear_button = QPushButton("Clear API keys")
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
        layout.addWidget(version_label)
        layout.addLayout(backend_row)
        layout.addWidget(self.openrouter_section)
        layout.addWidget(self.ollama_section)
        layout.addWidget(self.local_section)
        layout.addWidget(self.backend_hint)
        layout.addLayout(action_row)
        layout.addStretch(1)
        layout.addLayout(button_row)

        self.backend_combo.currentIndexChanged.connect(self._update_backend_visibility)
        self._update_backend_visibility()

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

    def _selected_backend(self) -> str:
        return str(self.backend_combo.currentData() or "openrouter")

    def _update_backend_visibility(self, *args) -> None:
        backend = self._selected_backend()
        self.openrouter_section.setVisible(backend == "openrouter")
        self.ollama_section.setVisible(backend == "ollama")
        self.local_section.setVisible(backend == "local")

    def _clear_key(self) -> None:
        self.openrouter_api_input.clear()
        self.ollama_api_input.clear()

    def _save(self) -> None:
        updates = {
            "backend": self._selected_backend(),
            "openrouter_api_key": self.openrouter_api_input.text().strip(),
            "openrouter_base_url": self.openrouter_base_input.text().strip(),
            "openrouter_model": self.openrouter_model_input.text().strip(),
            "ollama_base_url": self.ollama_base_input.text().strip(),
            "ollama_model": self.ollama_model_input.text().strip(),
            "ollama_api_key": self.ollama_api_input.text().strip(),
            "local_model_path": self.local_model_input.text().strip(),
            "local_ctx_size": self.local_ctx_input.value(),
            "local_max_tokens": self.local_max_tokens_input.value(),
            "local_threads": self.local_threads_input.value(),
            "local_gpu_layers": self.local_gpu_layers_input.currentText().strip(),
        }
        save_user_settings(updates)
        self.accept()
