from typing import List, Optional
from database.db_manager import DatabaseManager
from models.entites import Projet

class ProjetRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create(self, projet: Projet) -> int:
        query = """
            INSERT INTO projets (nom, client, reference, statut)
            VALUES (?, ?, ?, ?)
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                query,
                (projet.nom, projet.client, projet.reference, projet.statut)
            )
            conn.commit()
            return cursor.lastrowid

    def get_by_id(self, id: int) -> Optional[Projet]:
        query = "SELECT * FROM projets WHERE id = ?"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (id,))
            row = cursor.fetchone()
            if row:
                return Projet(**dict(row))
            return None

    def get_all(self) -> List[Projet]:
        query = "SELECT * FROM projets"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query)
            return [Projet(**dict(row)) for row in cursor.fetchall()]

    def update(self, projet: Projet):
        query = """
            UPDATE projets
            SET nom = ?, client = ?, reference = ?, statut = ?, date_modification = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (projet.nom, projet.client, projet.reference, projet.statut, projet.id)
            )
            conn.commit()

    def delete(self, id: int):
        query = "DELETE FROM projets WHERE id = ?"
        with self.db.get_connection() as conn:
            conn.execute(query, (id,))
            conn.commit()
