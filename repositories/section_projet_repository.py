from typing import List, Optional

from database.db_manager import DatabaseManager
from models.entites import SectionProjet


class SectionProjetRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create(self, section: SectionProjet, conn=None) -> int:
        query = """
            INSERT INTO sections_projet (
                projet_id, parent_id, type_ligne, numero_article, numero_article_original,
                libelle, unite, quantite, prix_unitaire, total, pour_memoire,
                ordre_affichage, profondeur, fichier_source, feuille_source,
                ligne_excel_source, formule_total, donnees_source_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            section.projet_id,
            section.parent_id,
            section.type_ligne,
            section.numero_article,
            section.numero_article_original,
            section.libelle,
            section.unite,
            section.quantite,
            section.prix_unitaire,
            section.total,
            section.pour_memoire,
            section.ordre_affichage,
            section.profondeur,
            section.fichier_source,
            section.feuille_source,
            section.ligne_excel_source,
            section.formule_total,
            section.donnees_source_json,
        )
        if conn is not None:
            cursor = conn.execute(query, params)
            return cursor.lastrowid
        with self.db.get_connection() as local_conn:
            cursor = local_conn.execute(query, params)
            local_conn.commit()
            return cursor.lastrowid

    def get_by_projet(self, projet_id: int) -> List[SectionProjet]:
        query = "SELECT * FROM sections_projet WHERE projet_id = ? ORDER BY ordre_affichage, id"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (projet_id,))
            return [self._row_to_section(row) for row in cursor.fetchall()]

    def get_by_id(self, id: int) -> Optional[SectionProjet]:
        query = "SELECT * FROM sections_projet WHERE id = ?"
        with self.db.get_connection() as conn:
            row = conn.execute(query, (id,)).fetchone()
            return self._row_to_section(row) if row else None

    def count_by_projet(self, projet_id: int) -> int:
        query = "SELECT COUNT(*) FROM sections_projet WHERE projet_id = ?"
        with self.db.get_connection() as conn:
            return conn.execute(query, (projet_id,)).fetchone()[0]

    def delete_by_projet(self, projet_id: int, conn=None):
        query = "DELETE FROM sections_projet WHERE projet_id = ?"
        if conn is not None:
            conn.execute(query, (projet_id,))
            return
        with self.db.get_connection() as local_conn:
            local_conn.execute(query, (projet_id,))
            local_conn.commit()

    def replace_for_projet(self, projet_id: int, sections: List[SectionProjet]):
        with self.db.get_connection() as conn:
            try:
                self.delete_by_projet(projet_id, conn)
                id_by_temp_index = {}
                for index, section in enumerate(sections):
                    if section.parent_id is not None and section.parent_id < 0:
                        section.parent_id = id_by_temp_index[section.parent_id]
                    new_id = self.create(section, conn)
                    id_by_temp_index[-(index + 1)] = new_id
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _row_to_section(self, row) -> SectionProjet:
        data = dict(row)
        data["pour_memoire"] = bool(data["pour_memoire"])
        return SectionProjet(**data)
