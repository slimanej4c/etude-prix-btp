from typing import List, Optional

from database.db_manager import DatabaseManager
from models.entites import MappingImport


class MappingImportRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def get_by_signature(self, signature_colonnes: str) -> Optional[MappingImport]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM mappings_import WHERE signature_colonnes = ?",
                (signature_colonnes,),
            ).fetchone()
            return self._row_to_entity(row) if row else None

    def get_by_id(self, mapping_id: int) -> Optional[MappingImport]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM mappings_import WHERE id = ?",
                (mapping_id,),
            ).fetchone()
            return self._row_to_entity(row) if row else None

    def list_all(self) -> List[MappingImport]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM mappings_import ORDER BY nom"
            ).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def save(
        self,
        nom: str,
        signature_colonnes: str,
        mapping_json: str,
        version: int = 1,
        mapping_parent_id: Optional[int] = None,
        update_existing: bool = True,
    ) -> int:
        with self.db.get_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM mappings_import WHERE signature_colonnes = ?",
                (signature_colonnes,),
            ).fetchone() if update_existing else None
            if existing and update_existing:
                conn.execute(
                    """
                    UPDATE mappings_import
                    SET nom = ?, mapping_json = ?, version = ?, mapping_parent_id = ?,
                        date_derniere_utilisation = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (nom, mapping_json, version, mapping_parent_id, existing["id"]),
                )
                conn.commit()
                return existing["id"]

            cursor = conn.execute(
                """
                INSERT INTO mappings_import (
                    nom, signature_colonnes, mapping_json, version, mapping_parent_id, date_derniere_utilisation
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (nom, signature_colonnes, mapping_json, version, mapping_parent_id),
            )
            conn.commit()
            return cursor.lastrowid

    def create_version(self, parent: MappingImport, signature_colonnes: str, mapping_json: str, nom: Optional[str] = None) -> int:
        return self.save(
            nom or parent.nom,
            signature_colonnes,
            mapping_json,
            version=parent.version + 1,
            mapping_parent_id=parent.id,
            update_existing=False,
        )

    def mark_used(self, mapping_id: int):
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE mappings_import SET date_derniere_utilisation = CURRENT_TIMESTAMP WHERE id = ?",
                (mapping_id,),
            )
            conn.commit()

    def _row_to_entity(self, row) -> MappingImport:
        return MappingImport(**dict(row))
