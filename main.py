import sys
import logging
from PySide6.QtWidgets import QApplication
from config import settings
from database.db_manager import DatabaseManager
from ui.main_window import MainWindow

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format=settings.LOG_FORMAT,
        handlers=[
            logging.FileHandler(settings.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    # 1. Configuration initiale (chemins, dossiers)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Démarrage de l'application...")

    # 2. Initialisation de la base de données
    try:
        db_manager = DatabaseManager()
        logger.info("Base de données initialisée avec succès.")
    except Exception as e:
        logger.critical(f"Erreur fatale lors de l'initialisation de la BDD : {e}")
        sys.exit(1)

    # 3. Lancement de l'interface graphique
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    logger.info("Interface graphique lancée.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
