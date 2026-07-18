from typing import List, Optional
from database.db_manager import DatabaseManager
from models.entites import Bibliotheque

class BibliothequeRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create(self, bibliotheque: Bibliotheque) -> int:
        query = """
            INSERT INTO bibliotheques (nom, description, corps_metier, actif, mapping_import_id)
            VALUES (?, ?, ?, ?, ?)
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                query,
                (
                    bibliotheque.nom,
                    bibliotheque.description,
                    bibliotheque.corps_metier,
                    bibliotheque.actif,
                    bibliotheque.mapping_import_id,
                )
            )
            conn.commit()
            return cursor.lastrowid

    def get_by_id(self, id: int) -> Optional[Bibliotheque]:
        query = "SELECT * FROM bibliotheques WHERE id = ?"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (id,))
            row = cursor.fetchone()
            if row:
                return Bibliotheque(**dict(row))
            return None

    def get_by_nom(self, nom: str) -> Optional[Bibliotheque]:
        query = "SELECT * FROM bibliotheques WHERE lower(nom) = lower(?) LIMIT 1"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (nom,))
            row = cursor.fetchone()
            if row:
                return Bibliotheque(**dict(row))
            return None

    def get_all(self) -> List[Bibliotheque]:
        query = "SELECT * FROM bibliotheques"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query)
            return [Bibliotheque(**dict(row)) for row in cursor.fetchall()]

    def update(self, bibliotheque: Bibliotheque):
        query = """
            UPDATE bibliotheques
            SET nom = ?, description = ?, corps_metier = ?, actif = ?, mapping_import_id = ?, date_modification = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    bibliotheque.nom,
                    bibliotheque.description,
                    bibliotheque.corps_metier,
                    bibliotheque.actif,
                    bibliotheque.mapping_import_id,
                    bibliotheque.id,
                )
            )
            conn.commit()

    def update_mapping_import_id(self, bibliotheque_id: int, mapping_import_id: int):
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE bibliotheques SET mapping_import_id = ?, date_modification = CURRENT_TIMESTAMP WHERE id = ?",
                (mapping_import_id, bibliotheque_id),
            )
            conn.commit()

    def delete(self, id: int):
        query = "DELETE FROM bibliotheques WHERE id = ?"
        with self.db.get_connection() as conn:
            conn.execute(query, (id,))
            conn.commit()
