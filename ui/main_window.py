from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, 
    QListWidget, QStackedWidget, QStatusBar
)
from PySide6.QtGui import QIcon
from ui.pages.projets_page import ProjetsPage
from ui.pages.bibliotheques_page import BibliothequesPage
from ui.pages.parametres_page import ParametresPage
from config import settings
from ui.theme import APP_STYLESHEET

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{settings.APP_NAME} v{settings.APP_VERSION}")
        self.setMinimumSize(1024, 768)
        
        self.setStyleSheet(APP_STYLESHEET)

        self._setup_ui()

    def _setup_ui(self):
        # Widget central et layout principal
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Menu latéral gauche
        self.menu_list = QListWidget()
        self.menu_list.setFixedWidth(250)
        self.menu_list.addItem("Projets")
        self.menu_list.addItem("Bibliothèques")
        self.menu_list.addItem("Paramètres")
        
        # Zone centrale (pages)
        self.stacked_widget = QStackedWidget()
        
        self.page_projets = ProjetsPage()
        self.page_bibliotheques = BibliothequesPage()
        self.page_parametres = ParametresPage()
        
        self.stacked_widget.addWidget(self.page_projets)
        self.stacked_widget.addWidget(self.page_bibliotheques)
        self.stacked_widget.addWidget(self.page_parametres)

        # Connexion menu -> pages
        self.menu_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)
        
        # Assemblage
        main_layout.addWidget(self.menu_list)
        main_layout.addWidget(self.stacked_widget)
        
        # Barre de statut
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Prêt")

        # Sélectionner la première page par défaut
        self.menu_list.setCurrentRow(0)
