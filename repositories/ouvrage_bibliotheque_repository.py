from typing import List, Optional
from database.db_manager import DatabaseManager
from models.entites import OuvrageBibliotheque

class OuvrageBibliothequeRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create(self, ouvrage: OuvrageBibliotheque) -> int:
        query = """
            INSERT INTO ouvrages_bibliotheque (
                bibliotheque_id, code, designation, famille, unite, mode_chiffrage,
                fournitures_ht_import, mo_heures_import, taux_horaire_import, mo_ht_import,
                materiel_ht_import, transport_ht_import, sous_traitance_ht_import, debourse_sec_import,
                pv_st_ht_import, pv_eg_ht_import, source_calcul, attributs_techniques, donnees_source_json,
                actif, date_creation, date_modification
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                query,
                (
                    ouvrage.bibliotheque_id, ouvrage.code, ouvrage.designation, ouvrage.famille, ouvrage.unite, ouvrage.mode_chiffrage,
                    ouvrage.fournitures_ht_import, ouvrage.mo_heures_import, ouvrage.taux_horaire_import, ouvrage.mo_ht_import,
                    ouvrage.materiel_ht_import, ouvrage.transport_ht_import, ouvrage.sous_traitance_ht_import, ouvrage.debourse_sec_import,
                    ouvrage.pv_st_ht_import, ouvrage.pv_eg_ht_import, ouvrage.source_calcul, ouvrage.attributs_techniques, ouvrage.donnees_source_json,
                    ouvrage.actif
                )
            )
            conn.commit()
            return cursor.lastrowid

    def update(self, ouvrage: OuvrageBibliotheque):
        query = """
            UPDATE ouvrages_bibliotheque SET
                code = ?, designation = ?, famille = ?, unite = ?, mode_chiffrage = ?,
                fournitures_ht_import = ?, mo_heures_import = ?, taux_horaire_import = ?, mo_ht_import = ?,
                materiel_ht_import = ?, transport_ht_import = ?, sous_traitance_ht_import = ?, debourse_sec_import = ?,
                pv_st_ht_import = ?, pv_eg_ht_import = ?, source_calcul = ?, attributs_techniques = ?, donnees_source_json = ?,
                actif = ?, date_creation = ?, date_modification = STRFTIME('%Y-%m-%d %H:%M:%f', 'now')
            WHERE id = ?
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    ouvrage.code, ouvrage.designation, ouvrage.famille, ouvrage.unite, ouvrage.mode_chiffrage,
                    ouvrage.fournitures_ht_import, ouvrage.mo_heures_import, ouvrage.taux_horaire_import, ouvrage.mo_ht_import,
                    ouvrage.materiel_ht_import, ouvrage.transport_ht_import, ouvrage.sous_traitance_ht_import, ouvrage.debourse_sec_import,
                    ouvrage.pv_st_ht_import, ouvrage.pv_eg_ht_import, ouvrage.source_calcul, ouvrage.attributs_techniques, ouvrage.donnees_source_json,
                    ouvrage.actif, ouvrage.date_creation, ouvrage.id
                )
            )
            conn.commit()

    def get_by_bibliotheque_and_code(self, bibliotheque_id: int, code: str) -> Optional[OuvrageBibliotheque]:
        query = "SELECT * FROM ouvrages_bibliotheque WHERE bibliotheque_id = ? AND code = ?"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (bibliotheque_id, code))
            row = cursor.fetchone()
            if row:
                return OuvrageBibliotheque(**dict(row))
            return None

    def get_by_id(self, id: int) -> Optional[OuvrageBibliotheque]:
        query = "SELECT * FROM ouvrages_bibliotheque WHERE id = ?"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (id,))
            row = cursor.fetchone()
            if row:
                return OuvrageBibliotheque(**dict(row))
            return None

    def get_all_by_bibliotheque(self, bibliotheque_id: int) -> List[OuvrageBibliotheque]:
        query = "SELECT * FROM ouvrages_bibliotheque WHERE bibliotheque_id = ? ORDER BY id"
        with self.db.get_connection() as conn:
            cursor = conn.execute(query, (bibliotheque_id,))
            return [OuvrageBibliotheque(**dict(row)) for row in cursor.fetchall()]

    def delete(self, id: int):
        query = "DELETE FROM ouvrages_bibliotheque WHERE id = ?"
        with self.db.get_connection() as conn:
            conn.execute(query, (id,))
            conn.commit()
