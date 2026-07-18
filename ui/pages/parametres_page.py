from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class ParametresPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        titre = QLabel("Paramètres Généraux")
        titre.setStyleSheet("font-size: 24px; font-weight: bold;")
        titre.setAlignment(Qt.AlignCenter)
        
        placeholder = QLabel("Contenu de la page Paramètres (à venir...)")
        placeholder.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(titre)
        layout.addWidget(placeholder)
        layout.addStretch()
