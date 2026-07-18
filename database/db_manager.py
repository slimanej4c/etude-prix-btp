import sqlite3
import logging
from decimal import Decimal
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, List

# Permettre à SQLite de gérer les Decimal
sqlite3.register_adapter(Decimal, lambda d: float(d))
sqlite3.register_converter("DECIMAL", lambda s: Decimal(s.decode("utf-8")))
from config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: Path = settings.DB_PATH, migrations_dir: Path = settings.MIGRATIONS_DIR):
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self._init_db()

    def _init_db(self):
        """Crée le dossier data et la base de données si nécessaire, puis applique les migrations."""
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Dossier créé : {self.db_path.parent}")
        
        self.apply_migrations()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Fournit une connexion à la base avec foreign keys activées et type Row."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Erreur de base de données : {e}")
            raise
        finally:
            conn.close()

    def _get_applied_migrations(self) -> List[int]:
        """Retourne la liste des versions de migrations déjà appliquées."""
        with self.get_connection() as conn:
            try:
                cursor = conn.execute("SELECT version FROM schema_version ORDER BY version")
                return [row["version"] for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                # La table schema_version n'existe pas encore
                return []

    def apply_migrations(self):
        """Applique les nouvelles migrations trouvées dans le dossier migrations."""
        if not self.migrations_dir.exists():
            logger.warning(f"Dossier de migrations introuvable : {self.migrations_dir}")
            return

        applied = self._get_applied_migrations()
        
        # Liste tous les fichiers .sql, triés par nom (ex: 001_schema_initial.sql)
        migration_files = sorted(self.migrations_dir.glob("*.sql"))
        
        for file in migration_files:
            try:
                # Extrait la version (ex: 001 -> 1)
                version = int(file.stem.split('_')[0])
                if version not in applied:
                    logger.info(f"Application de la migration : {file.name}")
                    self._apply_migration_file(file, version)
            except ValueError:
                logger.error(f"Format de nom de fichier de migration invalide : {file.name}")
            except Exception as e:
                logger.error(f"Erreur lors de l'application de la migration {file.name} : {e}")
                raise

    def _apply_migration_file(self, file_path: Path, version: int):
        """Exécute un fichier SQL de migration dans une transaction."""
        with open(file_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()

        with self.get_connection() as conn:
            try:
                conn.executescript(sql_script)
                
                # Si c'est la migration 1, la table schema_version vient d'être créée par le script lui-même
                conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                    (version, file_path.name)
                )
                conn.commit()
                logger.info(f"Migration {version} appliquée avec succès.")
            except Exception as e:
                conn.rollback()
                logger.error(f"Erreur SQL lors de la migration {file_path.name} : {e}")
                raise
