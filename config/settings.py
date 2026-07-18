import os
from pathlib import Path

# Chemins de base de l'application
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "etude_prix.db"
MIGRATIONS_DIR = BASE_DIR / "database" / "migrations"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

# Paramètres généraux
APP_NAME = "Logiciel d'Études de Prix BTP"
APP_VERSION = "0.1.0"

# Configuration du logging
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = DATA_DIR / "app.log"
