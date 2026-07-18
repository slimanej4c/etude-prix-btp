from decimal import Decimal
from typing import Dict, List, Optional

from database.db_manager import DatabaseManager
from models.entites import VersionProjet


ZERO = Decimal("0")


class VersionProjetRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def creer_snapshot(self, projet_id: int, nom: str, est_version_courante: bool = True) -> int:
        with self.db.get_connection() as conn:
            try:
                conn.execute("BEGIN")
                if est_version_courante:
                    conn.execute(
                        "UPDATE versions_projet SET est_version_courante = 0 WHERE projet_id = ?",
                        (projet_id,),
                    )
                cursor = conn.execute(
                    """
                    INSERT INTO versions_projet (projet_id, nom, est_version_courante)
                    VALUES (?, ?, ?)
                    """,
                    (projet_id, nom, 1 if est_version_courante else 0),
                )
                version_id = cursor.lastrowid
                conn.execute(
                    """
                    INSERT INTO versions_projet_lignes (
                        version_id, ouvrage_projet_id, ds_mo, ds_mat, ds_materiel,
                        ds_transport, ds_st, ds_total, pv_unitaire, pv_total
                    )
                    SELECT
                        ?, op.id, op.ds_mo, op.ds_mat, op.ds_materiel,
                        op.ds_transport, op.ds_st, op.ds_total, op.pv_unitaire, op.pv_total
                    FROM ouvrages_projet op
                    JOIN sous_lots sl ON sl.id = op.sous_lot_id
                    JOIN lots l ON l.id = sl.lot_id
                    WHERE l.projet_id = ?
                    ORDER BY l.ordre_affichage, sl.ordre_affichage, op.ordre_affichage, op.id
                    """,
                    (version_id, projet_id),
                )
                conn.commit()
                return version_id
            except Exception:
                conn.rollback()
                raise

    def dupliquer_version_vers_actuel(self, version_source_id: int, nom: str) -> int:
        with self.db.get_connection() as conn:
            try:
                conn.execute("BEGIN")
                source = conn.execute(
                    "SELECT projet_id FROM versions_projet WHERE id = ?",
                    (version_source_id,),
                ).fetchone()
                if not source:
                    raise ValueError("Version source introuvable.")

                projet_id = source["projet_id"]
                conn.execute(
                    "UPDATE versions_projet SET est_version_courante = 0 WHERE projet_id = ?",
                    (projet_id,),
                )
                cursor = conn.execute(
                    """
                    INSERT INTO versions_projet (projet_id, nom, est_version_courante)
                    VALUES (?, ?, 1)
                    """,
                    (projet_id, nom),
                )
                nouvelle_version_id = cursor.lastrowid
                conn.execute(
                    """
                    INSERT INTO versions_projet_lignes (
                        version_id, ouvrage_projet_id, ds_mo, ds_mat, ds_materiel,
                        ds_transport, ds_st, ds_total, pv_unitaire, pv_total
                    )
                    SELECT
                        ?, ouvrage_projet_id, ds_mo, ds_mat, ds_materiel,
                        ds_transport, ds_st, ds_total, pv_unitaire, pv_total
                    FROM versions_projet_lignes
                    WHERE version_id = ?
                    """,
                    (nouvelle_version_id, version_source_id),
                )
                lignes = conn.execute(
                    """
                    SELECT ouvrage_projet_id, ds_mo, ds_mat, ds_materiel, ds_transport,
                           ds_st, ds_total, pv_unitaire, pv_total
                    FROM versions_projet_lignes
                    WHERE version_id = ?
                    """,
                    (version_source_id,),
                ).fetchall()
                for ligne in lignes:
                    conn.execute(
                        """
                        UPDATE ouvrages_projet
                        SET ds_mo = ?, ds_mat = ?, ds_materiel = ?, ds_transport = ?,
                            ds_st = ?, ds_total = ?, pv_unitaire = ?, pv_total = ?,
                            date_modification = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            ligne["ds_mo"],
                            ligne["ds_mat"],
                            ligne["ds_materiel"],
                            ligne["ds_transport"],
                            ligne["ds_st"],
                            ligne["ds_total"],
                            ligne["pv_unitaire"],
                            ligne["pv_total"],
                            ligne["ouvrage_projet_id"],
                        ),
                    )
                conn.commit()
                return nouvelle_version_id
            except Exception:
                conn.rollback()
                raise

    def etat_actuel_different_derniere_version(self, projet_id: int) -> bool:
        with self.db.get_connection() as conn:
            version = conn.execute(
                """
                SELECT id
                FROM versions_projet
                WHERE projet_id = ? AND est_version_courante = 1
                ORDER BY date_creation DESC, id DESC
                LIMIT 1
                """,
                (projet_id,),
            ).fetchone()
        if not version:
            return bool(self.lignes_actuelles(projet_id))

        actuel = self.lignes_actuelles(projet_id)
        derniere = self.lignes_version(version["id"])
        if set(actuel) != set(derniere):
            return True
        keys = ("ds_mo", "ds_mat", "ds_materiel", "ds_transport", "ds_st", "ds_total", "pv_unitaire", "pv_total")
        for ouvrage_id, ligne_actuelle in actuel.items():
            ligne_version = derniere[ouvrage_id]
            if any(ligne_actuelle[key] != ligne_version[key] for key in keys):
                return True
        return False

    def sauvegarder_composants_ligne_version(
        self,
        version_id: int,
        ouvrage_projet_id: int,
        ds_mo: Decimal,
        ds_mat: Decimal,
        ds_materiel: Decimal,
        ds_transport: Decimal,
        ds_st: Decimal,
    ) -> Dict:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT vl.*, op.quantite
                FROM versions_projet_lignes vl
                JOIN ouvrages_projet op ON op.id = vl.ouvrage_projet_id
                WHERE vl.version_id = ? AND vl.ouvrage_projet_id = ?
                """,
                (version_id, ouvrage_projet_id),
            ).fetchone()
            if not row:
                row = conn.execute(
                    """
                    SELECT op.quantite
                    FROM versions_projet v
                    JOIN ouvrages_projet op ON op.id = ?
                    JOIN sous_lots sl ON sl.id = op.sous_lot_id
                    JOIN lots l ON l.id = sl.lot_id AND l.projet_id = v.projet_id
                    WHERE v.id = ?
                    """,
                    (ouvrage_projet_id, version_id),
                ).fetchone()
                if not row:
                    raise ValueError("Ligne de version introuvable.")

            old_ds_total = self._to_decimal(row["ds_total"]) if "ds_total" in row.keys() else ZERO
            old_pv_total = self._to_decimal(row["pv_total"]) if "pv_total" in row.keys() else ZERO
            coefficient = old_pv_total / old_ds_total if old_ds_total else Decimal("1.20")
            quantite = self._to_decimal(row["quantite"]) or Decimal("1")
            ds_total = self._money(ds_mo + ds_mat + ds_materiel + ds_transport + ds_st)
            pv_total = self._money(ds_total * coefficient)
            pv_unitaire = self._money(pv_total / quantite) if quantite else ZERO
            self._upsert_ligne_version_conn(
                conn,
                version_id,
                ouvrage_projet_id,
                {
                    "ds_mo": self._money(ds_mo),
                    "ds_mat": self._money(ds_mat),
                    "ds_materiel": self._money(ds_materiel),
                    "ds_transport": self._money(ds_transport),
                    "ds_st": self._money(ds_st),
                    "ds_total": ds_total,
                    "pv_unitaire": pv_unitaire,
                    "pv_total": pv_total,
                },
            )
            conn.commit()
            return {
                "ouvrage_projet_id": ouvrage_projet_id,
                "ds_mo": self._money(ds_mo),
                "ds_mat": self._money(ds_mat),
                "ds_materiel": self._money(ds_materiel),
                "ds_transport": self._money(ds_transport),
                "ds_st": self._money(ds_st),
                "ds_total": ds_total,
                "pv_unitaire": pv_unitaire,
                "pv_total": pv_total,
            }

    def sauvegarder_ligne_version(self, version_id: int, ouvrage_projet_id: int, values: Dict[str, Decimal]) -> Dict:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM versions_projet_lignes
                WHERE version_id = ? AND ouvrage_projet_id = ?
                """,
                (version_id, ouvrage_projet_id),
            ).fetchone()
            if not row:
                exists = conn.execute(
                    """
                    SELECT 1
                    FROM versions_projet v
                    JOIN ouvrages_projet op ON op.id = ?
                    JOIN sous_lots sl ON sl.id = op.sous_lot_id
                    JOIN lots l ON l.id = sl.lot_id AND l.projet_id = v.projet_id
                    WHERE v.id = ?
                    """,
                    (ouvrage_projet_id, version_id),
                ).fetchone()
                if not exists:
                    raise ValueError("Ligne de version introuvable.")
            self._upsert_ligne_version_conn(conn, version_id, ouvrage_projet_id, values)
            conn.commit()
            return {
                "ouvrage_projet_id": ouvrage_projet_id,
                "ds_mo": self._money(values["ds_mo"]),
                "ds_mat": self._money(values["ds_mat"]),
                "ds_materiel": self._money(values["ds_materiel"]),
                "ds_transport": self._money(values["ds_transport"]),
                "ds_st": self._money(values["ds_st"]),
                "ds_total": self._money(values["ds_total"]),
                "pv_unitaire": self._money(values["pv_unitaire"]),
                "pv_total": self._money(values["pv_total"]),
            }

    def _upsert_ligne_version_conn(self, conn, version_id: int, ouvrage_projet_id: int, values: Dict[str, Decimal]) -> None:
        updated = conn.execute(
                """
                UPDATE versions_projet_lignes
                SET ds_mo = ?, ds_mat = ?, ds_materiel = ?, ds_transport = ?,
                    ds_st = ?, ds_total = ?, pv_unitaire = ?, pv_total = ?
                WHERE version_id = ? AND ouvrage_projet_id = ?
                """,
            (
                self._money(values["ds_mo"]),
                self._money(values["ds_mat"]),
                self._money(values["ds_materiel"]),
                self._money(values["ds_transport"]),
                self._money(values["ds_st"]),
                self._money(values["ds_total"]),
                self._money(values["pv_unitaire"]),
                self._money(values["pv_total"]),
                version_id,
                ouvrage_projet_id,
            ),
        )
        if updated.rowcount:
            return
        conn.execute(
            """
            INSERT INTO versions_projet_lignes (
                version_id, ouvrage_projet_id, ds_mo, ds_mat, ds_materiel,
                ds_transport, ds_st, ds_total, pv_unitaire, pv_total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                ouvrage_projet_id,
                self._money(values["ds_mo"]),
                self._money(values["ds_mat"]),
                self._money(values["ds_materiel"]),
                self._money(values["ds_transport"]),
                self._money(values["ds_st"]),
                self._money(values["ds_total"]),
                self._money(values["pv_unitaire"]),
                self._money(values["pv_total"]),
            ),
        )

    def lister_par_projet(self, projet_id: int) -> List[VersionProjet]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT v.*, COUNT(vl.id) AS nombre_lignes
                FROM versions_projet v
                LEFT JOIN versions_projet_lignes vl ON vl.version_id = v.id
                WHERE v.projet_id = ?
                GROUP BY v.id
                ORDER BY v.date_creation DESC, v.id DESC
                """,
                (projet_id,),
            ).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def get_by_id(self, version_id: int) -> Optional[VersionProjet]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT v.*, COUNT(vl.id) AS nombre_lignes
                FROM versions_projet v
                LEFT JOIN versions_projet_lignes vl ON vl.version_id = v.id
                WHERE v.id = ?
                GROUP BY v.id
                """,
                (version_id,),
            ).fetchone()
        return self._row_to_entity(row) if row else None

    def supprimer(self, version_id: int) -> None:
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM versions_projet WHERE id = ?", (version_id,))
            conn.commit()

    def lister_lots(self, projet_id: int) -> List[Dict]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, code, libelle
                FROM lots
                WHERE projet_id = ?
                ORDER BY ordre_affichage, id
                """,
                (projet_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def agreger_version(self, version_id: int, lot_id: Optional[int] = None) -> Dict[str, Decimal]:
        query = """
            SELECT
                COALESCE(SUM(vl.ds_mo), 0) AS ds_mo,
                COALESCE(SUM(vl.ds_mat), 0) AS ds_mat,
                COALESCE(SUM(vl.ds_materiel), 0) AS ds_materiel,
                COALESCE(SUM(vl.ds_transport), 0) AS ds_transport,
                COALESCE(SUM(vl.ds_st), 0) AS ds_st,
                COALESCE(SUM(vl.ds_total), 0) AS ds_total,
                COALESCE(SUM(vl.pv_total), 0) AS pv_total
            FROM versions_projet_lignes vl
            JOIN ouvrages_projet op ON op.id = vl.ouvrage_projet_id
            JOIN sous_lots sl ON sl.id = op.sous_lot_id
            WHERE vl.version_id = ?
        """
        params = [version_id]
        if lot_id is not None:
            query += " AND sl.lot_id = ?"
            params.append(lot_id)
        with self.db.get_connection() as conn:
            row = conn.execute(query, params).fetchone()
        return self._decimal_dict(row)

    def agreger_actuel(self, projet_id: int, lot_id: Optional[int] = None) -> Dict[str, Decimal]:
        query = """
            SELECT
                COALESCE(SUM(op.ds_mo), 0) AS ds_mo,
                COALESCE(SUM(op.ds_mat), 0) AS ds_mat,
                COALESCE(SUM(op.ds_materiel), 0) AS ds_materiel,
                COALESCE(SUM(op.ds_transport), 0) AS ds_transport,
                COALESCE(SUM(op.ds_st), 0) AS ds_st,
                COALESCE(SUM(op.ds_total), 0) AS ds_total,
                COALESCE(SUM(op.pv_total), 0) AS pv_total
            FROM ouvrages_projet op
            JOIN sous_lots sl ON sl.id = op.sous_lot_id
            JOIN lots l ON l.id = sl.lot_id
            WHERE l.projet_id = ?
        """
        params = [projet_id]
        if lot_id is not None:
            query += " AND l.id = ?"
            params.append(lot_id)
        with self.db.get_connection() as conn:
            row = conn.execute(query, params).fetchone()
        return self._decimal_dict(row)

    def lignes_version(self, version_id: int, lot_id: Optional[int] = None) -> Dict[int, Dict]:
        query = """
            SELECT
                op.id AS ouvrage_projet_id, op.code, op.designation, l.libelle AS lot_libelle,
                vl.ds_mo, vl.ds_mat, vl.ds_materiel, vl.ds_transport, vl.ds_st,
                vl.ds_total, vl.pv_unitaire, vl.pv_total
            FROM versions_projet_lignes vl
            JOIN ouvrages_projet op ON op.id = vl.ouvrage_projet_id
            JOIN sous_lots sl ON sl.id = op.sous_lot_id
            JOIN lots l ON l.id = sl.lot_id
            WHERE vl.version_id = ?
        """
        params = [version_id]
        if lot_id is not None:
            query += " AND l.id = ?"
            params.append(lot_id)
        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return {row["ouvrage_projet_id"]: self._line_dict(row) for row in rows}

    def lignes_actuelles(self, projet_id: int, lot_id: Optional[int] = None) -> Dict[int, Dict]:
        query = """
            SELECT
                op.id AS ouvrage_projet_id, op.code, op.designation, l.libelle AS lot_libelle,
                op.ds_mo, op.ds_mat, op.ds_materiel, op.ds_transport, op.ds_st,
                op.ds_total, op.pv_unitaire, op.pv_total
            FROM ouvrages_projet op
            JOIN sous_lots sl ON sl.id = op.sous_lot_id
            JOIN lots l ON l.id = sl.lot_id
            WHERE l.projet_id = ?
        """
        params = [projet_id]
        if lot_id is not None:
            query += " AND l.id = ?"
            params.append(lot_id)
        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return {row["ouvrage_projet_id"]: self._line_dict(row) for row in rows}

    def _row_to_entity(self, row) -> VersionProjet:
        return VersionProjet(
            id=row["id"],
            projet_id=row["projet_id"],
            nom=row["nom"],
            est_version_courante=bool(row["est_version_courante"]),
            date_creation=row["date_creation"],
            nombre_lignes=row["nombre_lignes"] or 0,
        )

    def _decimal_dict(self, row) -> Dict[str, Decimal]:
        return {
            key: self._to_decimal(row[key])
            for key in ("ds_mo", "ds_mat", "ds_materiel", "ds_transport", "ds_st", "ds_total", "pv_total")
        }

    def _line_dict(self, row) -> Dict:
        data = dict(row)
        for key in ("ds_mo", "ds_mat", "ds_materiel", "ds_transport", "ds_st", "ds_total", "pv_unitaire", "pv_total"):
            data[key] = self._to_decimal(data[key])
        return data

    def _to_decimal(self, value) -> Decimal:
        if value is None:
            return ZERO
        return Decimal(str(value))

    def _money(self, value: Decimal) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
