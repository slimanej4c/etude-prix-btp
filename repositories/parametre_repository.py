from typing import List, Optional
from database.db_manager import DatabaseManager
from models.entites import ParametreGeneral

class ParametreRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create(self, parametre: ParametreGeneral) -> int:
        query = """
            INSERT INTO parametres_generaux (cle, valeur, type_valeur, unite, description)
            VALUES (?, ?, ?, ?, ?)
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                query,
                (parametre.cle, parametre.valeur, parametre.type_valeur, parametre.unite, parametre.description)
            )
            conn.commit()
            return cursor.lastrowid

    def get_by_cle(self, cle: str) -> Optional[ParametreGeneral]:
        query = "SELECT * FROM parametres_generaux WHERE cle = ?"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (cle,))
            row = cursor.fetchone()
            if row:
                return ParametreGeneral(**dict(row))
            return None

    def get_all(self) -> List[ParametreGeneral]:
        query = "SELECT * FROM parametres_generaux"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query)
            return [ParametreGeneral(**dict(row)) for row in cursor.fetchall()]

    def update(self, parametre: ParametreGeneral):
        query = """
            UPDATE parametres_generaux
            SET valeur = ?, type_valeur = ?, unite = ?, description = ?, date_modification = CURRENT_TIMESTAMP
            WHERE cle = ?
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (parametre.valeur, parametre.type_valeur, parametre.unite, parametre.description, parametre.cle)
            )
            conn.commit()

    def delete(self, cle: str):
        query = "DELETE FROM parametres_generaux WHERE cle = ?"
        with self.db.get_connection() as conn:
            conn.execute(query, (cle,))
            conn.commit()
