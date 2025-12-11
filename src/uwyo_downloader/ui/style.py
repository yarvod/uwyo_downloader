BASE_STYLESHEET = """
QGroupBox { border: 1px solid #1f2937; border-radius: 8px; margin-top: 12px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #9ca3af; }
QLabel { color: #e5e7eb; }
QCheckBox { color: #e5e7eb; }
QLineEdit, QDateTimeEdit, QPlainTextEdit, QSpinBox, QTableWidget, QComboBox {
    background: #0f172a; border: 1px solid #1f2937; color: #e5e7eb; border-radius: 6px; padding: 6px;
}
QPushButton {
    background: #22d3ee; color: #0b1220; border: none; border-radius: 6px; padding: 8px 12px;
    font-weight: 600;
}
QPushButton:disabled { background: #1f2937; color: #9ca3af; }
QProgressBar { background: #0f172a; border: 1px solid #1f2937; border-radius: 6px; text-align: center; }
QProgressBar::chunk { background: #22d3ee; border-radius: 6px; }
QTableWidget { gridline-color: #1f2937; }
"""
