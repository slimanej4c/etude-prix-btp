from decimal import Decimal
from typing import List, Optional

from database.db_manager import DatabaseManager
from models.entites import CorrespondanceDpgf


class CorrespondanceDpgfRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def upsert_proposition(self, ouvrage_projet_id: int, ouvrage_bibliotheque_id: int, score: Decimal, origine: str = "automatique") -> int:
        with self.db.get_connection() as conn:
            cursor_id = self.upsert_proposition_conn(conn, ouvrage_projet_id, ouvrage_bibliotheque_id, score, origine)
            conn.commit()
            return cursor_id

    def upsert_proposition_conn(self, conn, ouvrage_projet_id: int, ouvrage_bibliotheque_id: int, score: Decimal, origine: str = "automatique") -> int:
        existing = conn.execute(
            """
            SELECT id, statut FROM correspondances_dpgf
            WHERE ouvrage_projet_id = ? AND ouvrage_bibliotheque_id = ?
            """,
            (ouvrage_projet_id, ouvrage_bibliotheque_id),
        ).fetchone()
        if existing:
            if existing["statut"] == "proposee":
                conn.execute(
                    """
                    UPDATE correspondances_dpgf
                    SET score = ?, origine = ?, date_modification = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (float(score), origine, existing["id"]),
                )
            return existing["id"]

        cursor = conn.execute(
            """
            INSERT INTO correspondances_dpgf (
                ouvrage_projet_id, ouvrage_bibliotheque_id, score, origine, statut
            ) VALUES (?, ?, ?, ?, 'proposee')
            """,
            (ouvrage_projet_id, ouvrage_bibliotheque_id, float(score), origine),
        )
        return cursor.lastrowid

    def creer_manuelle_validee(self, ouvrage_projet_id: int, ouvrage_bibliotheque_id: int) -> int:
        with self.db.get_connection() as conn:
            try:
                existing = conn.execute(
                    """
                    SELECT id FROM correspondances_dpgf
                    WHERE ouvrage_projet_id = ? AND ouvrage_bibliotheque_id = ?
                    """,
                    (ouvrage_projet_id, ouvrage_bibliotheque_id),
                ).fetchone()
                if existing:
                    corr_id = existing["id"]
                    conn.execute(
                        """
                        UPDATE correspondances_dpgf
                        SET score = 100, origine = 'manuelle', date_modification = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (corr_id,),
                    )
                else:
                    cursor = conn.execute(
                        """
                        INSERT INTO correspondances_dpgf (
                            ouvrage_projet_id, ouvrage_bibliotheque_id, score, origine, statut
                        ) VALUES (?, ?, 100, 'manuelle', 'proposee')
                        """,
                        (ouvrage_projet_id, ouvrage_bibliotheque_id),
                    )
                    corr_id = cursor.lastrowid
                self.valider(corr_id, conn)
                conn.commit()
                return corr_id
            except Exception:
                conn.rollback()
                raise

    def valider(self, correspondance_id: int, conn=None):
        own_conn = conn is None
        if own_conn:
            conn_ctx = self.db.get_connection()
            conn = conn_ctx.__enter__()
        try:
            row = conn.execute(
                "SELECT ouvrage_projet_id FROM correspondances_dpgf WHERE id = ?",
                (correspondance_id,),
            ).fetchone()
            if not row:
                raise ValueError("Correspondance introuvable.")

            conn.execute(
                """
                UPDATE correspondances_dpgf
                SET statut = 'proposee', date_modification = CURRENT_TIMESTAMP
                WHERE ouvrage_projet_id = ? AND statut = 'validee' AND id <> ?
                """,
                (row["ouvrage_projet_id"], correspondance_id),
            )
            conn.execute(
                """
                UPDATE correspondances_dpgf
                SET statut = 'validee', date_modification = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (correspondance_id,),
            )
            if own_conn:
                conn.commit()
        except Exception:
            if own_conn:
                conn.rollback()
            raise
        finally:
            if own_conn:
                conn_ctx.__exit__(None, None, None)

    def valider_pour_ouvrage(self, ouvrage_projet_id: int, correspondance_id: int, conn=None):
        own_conn = conn is None
        if own_conn:
            conn_ctx = self.db.get_connection()
            conn = conn_ctx.__enter__()
        try:
            row = conn.execute(
                """
                SELECT id
                FROM correspondances_dpgf
                WHERE id = ? AND ouvrage_projet_id = ?
                """,
                (correspondance_id, ouvrage_projet_id),
            ).fetchone()
            if not row:
                raise ValueError("La proposition sélectionnée ne correspond pas à cette ligne DPGF.")
            self.valider(correspondance_id, conn)
            if own_conn:
                conn.commit()
        except Exception:
            if own_conn:
                conn.rollback()
            raise
        finally:
            if own_conn:
                conn_ctx.__exit__(None, None, None)

    def valider_selection(self, selections: dict[int, int]):
        with self.db.get_connection() as conn:
            try:
                seen_ouvrages = set()
                for ouvrage_projet_id, correspondance_id in selections.items():
                    if ouvrage_projet_id in seen_ouvrages:
                        raise ValueError("Plusieurs propositions cochées concernent la même ligne DPGF.")
                    seen_ouvrages.add(ouvrage_projet_id)
                    self.valider_pour_ouvrage(ouvrage_projet_id, correspondance_id, conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def valider_plusieurs(self, correspondance_ids: List[int]):
        with self.db.get_connection() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT id, ouvrage_projet_id
                    FROM correspondances_dpgf
                    WHERE id IN ({})
                    """.format(",".join("?" for _ in correspondance_ids)),
                    correspondance_ids,
                ).fetchall() if correspondance_ids else []
                if len(rows) != len(set(correspondance_ids)):
                    raise ValueError("Une ou plusieurs correspondances sont introuvables.")
                ouvrage_ids = [row["ouvrage_projet_id"] for row in rows]
                if len(ouvrage_ids) != len(set(ouvrage_ids)):
                    raise ValueError("Plusieurs propositions cochées concernent la même ligne DPGF.")
                for corr_id in correspondance_ids:
                    self.valider(corr_id, conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def supprimer(self, correspondance_id: int):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM correspondances_dpgf WHERE id = ?", (correspondance_id,))
            conn.commit()

    def supprimer_pour_ouvrage(self, ouvrage_projet_id: int):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM correspondances_dpgf WHERE ouvrage_projet_id = ?", (ouvrage_projet_id,))
            conn.commit()

    def annuler_validation_pour_ouvrage(self, ouvrage_projet_id: int):
        with self.db.get_connection() as conn:
            conn.execute(
                """
                UPDATE correspondances_dpgf
                SET statut = 'proposee', date_modification = CURRENT_TIMESTAMP
                WHERE ouvrage_projet_id = ? AND statut = 'validee'
                """,
                (ouvrage_projet_id,),
            )
            conn.commit()

    def get_by_ouvrage_projet(self, ouvrage_projet_id: int) -> List[CorrespondanceDpgf]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM correspondances_dpgf
                WHERE ouvrage_projet_id = ?
                ORDER BY statut = 'validee' DESC, score DESC, id
                """,
                (ouvrage_projet_id,),
            ).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def get_validee(self, ouvrage_projet_id: int) -> Optional[CorrespondanceDpgf]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM correspondances_dpgf
                WHERE ouvrage_projet_id = ? AND statut = 'validee'
                """,
                (ouvrage_projet_id,),
            ).fetchone()
            return self._row_to_entity(row) if row else None

    def get_enriched_by_ouvrage_projet(self, ouvrage_projet_id: int) -> List[dict]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.*,
                    o.code,
                    o.designation,
                    o.famille,
                    o.unite,
                    o.debourse_sec_import,
                    o.pv_eg_ht_import,
                    o.pv_st_ht_import,
                    o.fournitures_ht_import,
                    o.mo_ht_import,
                    o.attributs_techniques,
                    b.nom AS bibliotheque_nom,
                    b.corps_metier
                FROM correspondances_dpgf c
                JOIN ouvrages_bibliotheque o ON o.id = c.ouvrage_bibliotheque_id
                JOIN bibliotheques b ON b.id = o.bibliotheque_id
                WHERE c.ouvrage_projet_id = ?
                ORDER BY c.statut = 'validee' DESC, c.score DESC, c.id
                """,
                (ouvrage_projet_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def count_by_ouvrage_bibliotheque(self, ouvrage_bibliotheque_id: int) -> int:
        with self.db.get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM correspondances_dpgf WHERE ouvrage_bibliotheque_id = ?",
                (ouvrage_bibliotheque_id,),
            ).fetchone()[0]

    def _row_to_entity(self, row) -> CorrespondanceDpgf:
        data = dict(row)
        data["score"] = Decimal(str(data["score"]))
        return CorrespondanceDpgf(**data)
