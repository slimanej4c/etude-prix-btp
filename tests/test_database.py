import pytest
import sqlite3
from pathlib import Path
from database.db_manager import DatabaseManager
from repositories.bibliotheque_repository import BibliothequeRepository
from repositories.projet_repository import ProjetRepository
from models.entites import Bibliotheque, Projet
from config import settings
import os

@pytest.fixture
def temp_db_manager(tmp_path):
    # Créer un environnement de base de données temporaire pour les tests
    db_path = tmp_path / "test_etude_prix.db"
    
    # On utilise le répertoire de migrations réel pour l'initialisation
    migrations_dir = Path(__file__).parent.parent / "database" / "migrations"
    
    manager = DatabaseManager(db_path=db_path, migrations_dir=migrations_dir)
    return manager

def test_database_creation(temp_db_manager):
    # Vérifier que le fichier SQLite a bien été créé
    assert temp_db_manager.db_path.exists()

def test_foreign_keys_activated(temp_db_manager):
    with temp_db_manager.get_connection() as conn:
        cursor = conn.execute("PRAGMA foreign_keys;")
        result = cursor.fetchone()[0]
        assert result == 1  # 1 signifie ON

def test_migrations_applied(temp_db_manager):
    with temp_db_manager.get_connection() as conn:
        cursor = conn.execute("SELECT version FROM schema_version")
        versions = [row["version"] for row in cursor.fetchall()]
        assert 1 in versions  # La migration 001 doit être appliquée

def test_crud_bibliotheque(temp_db_manager):
    repo = BibliothequeRepository(temp_db_manager)
    
    # Create
    biblio = Bibliotheque(
        id=None,
        nom="Test Biblio",
        description="Description test",
        corps_metier="Gros Oeuvre",
        actif=True,
        date_creation="",
        date_modification=""
    )
    biblio_id = repo.create(biblio)
    assert biblio_id is not None
    
    # Read
    fetched = repo.get_by_id(biblio_id)
    assert fetched is not None
    assert fetched.nom == "Test Biblio"
    
    # Update
    fetched.nom = "Updated Biblio"
    repo.update(fetched)
    updated = repo.get_by_id(biblio_id)
    assert updated.nom == "Updated Biblio"
    
    # Delete
    repo.delete(biblio_id)
    deleted = repo.get_by_id(biblio_id)
    assert deleted is None

def test_crud_projet(temp_db_manager):
    repo = ProjetRepository(temp_db_manager)
    
    # Create
    projet = Projet(
        id=None,
        nom="Test Projet",
        client="Client A",
        reference="REF-001",
        statut="Nouveau",
        date_creation="",
        date_modification=""
    )
    projet_id = repo.create(projet)
    assert projet_id is not None
    
    # Read
    fetched = repo.get_by_id(projet_id)
    assert fetched is not None
    assert fetched.nom == "Test Projet"
    
    # Update
    fetched.statut = "En cours"
    repo.update(fetched)
    updated = repo.get_by_id(projet_id)
    assert updated.statut == "En cours"
    
    # Delete
    repo.delete(projet_id)
    deleted = repo.get_by_id(projet_id)
    assert deleted is None

def test_cascade_delete(temp_db_manager):
    # Tester que la suppression d'une bibliothèque supprime ses ressources
    with temp_db_manager.get_connection() as conn:
        # Créer bibliothèque
        cursor = conn.execute(
            "INSERT INTO bibliotheques (nom, actif) VALUES ('Biblio', 1)"
        )
        biblio_id = cursor.lastrowid
        
        # Créer ressource liée
        conn.execute(
            "INSERT INTO ressources (bibliotheque_id, code, designation, type_ressource, unite, prix_unitaire_ht) "
            "VALUES (?, 'R1', 'Ressource 1', 'materiau', 'u', 10.0)",
            (biblio_id,)
        )
        conn.commit()
        
        # Vérifier que la ressource existe
        res = conn.execute("SELECT count(*) FROM ressources").fetchone()[0]
        assert res == 1
        
        # Supprimer la bibliothèque
        conn.execute("DELETE FROM bibliotheques WHERE id = ?", (biblio_id,))
        conn.commit()
        
        # Vérifier que la ressource a été supprimée en cascade
        res_after = conn.execute("SELECT count(*) FROM ressources").fetchone()[0]
        assert res_after == 0
