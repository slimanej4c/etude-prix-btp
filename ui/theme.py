COLORS = {
    "background": "#2b2b2b",
    "surface": "#3b3b3b",
    "surface_alt": "#1e1e1e",
    "border": "#4a4a4a",
    "text": "#ffffff",
    "muted": "#d6d6d6",
    "accent": "#007acc",
    "danger": "#b3261e",
    "warning": "#c77800",
    "success": "#1b7f3a",
}


APP_STYLESHEET = f"""
QMainWindow, QDialog, QWidget {{
    background-color: {COLORS["background"]};
    color: {COLORS["text"]};
}}
QLabel, QCheckBox, QRadioButton, QGroupBox {{
    color: {COLORS["text"]};
}}
QLineEdit, QComboBox, QPlainTextEdit, QDoubleSpinBox {{
    background-color: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    padding: 6px;
}}
QTableWidget, QTreeWidget, QListWidget, QScrollArea {{
    background-color: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
}}
QTableWidget::item, QTreeWidget::item, QListWidget::item {{
    color: {COLORS["text"]};
}}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{
    background-color: {COLORS["accent"]};
    color: {COLORS["text"]};
}}
QHeaderView::section {{
    background-color: {COLORS["surface_alt"]};
    color: {COLORS["text"]};
    padding: 4px;
    border: 1px solid {COLORS["border"]};
}}
QPushButton {{
    background-color: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    padding: 7px;
}}
QPushButton:disabled {{
    color: #8a8a8a;
}}
QProgressBar {{
    background-color: {COLORS["surface"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
}}
QProgressBar::chunk {{
    background-color: {COLORS["accent"]};
}}
QStatusBar {{
    background-color: {COLORS["surface_alt"]};
    color: {COLORS["text"]};
}}
"""


def status_style(status: str) -> str:
    color = {
        "Aucune": COLORS["danger"],
        "Proposée": COLORS["warning"],
        "Validée": COLORS["success"],
    }.get(status, COLORS["border"])
    return f"font-weight: bold; color: {COLORS['text']}; background: {color}; padding: 4px;"


def band_style() -> str:
    return f"font-size: 15px; font-weight: bold; padding: 8px; background: {COLORS['surface_alt']}; color: {COLORS['text']};"
