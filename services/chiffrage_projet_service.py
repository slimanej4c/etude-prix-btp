from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional

from database.db_manager import DatabaseManager
from models.entites import SectionProjet
from repositories.correspondance_dpgf_repository import CorrespondanceDpgfRepository
from repositories.section_projet_repository import SectionProjetRepository


ZERO = Decimal("0")
DEFAULT_COEFFICIENT_VENTE = Decimal("1.20")


class ChiffrageProjetService:
    def __init__(
        self,
        db_manager: DatabaseManager,
        section_repo: SectionProjetRepository,
        correspondance_repo: CorrespondanceDpgfRepository,
    ):
        self.db = db_manager
        self.section_repo = section_repo
        self.correspondance_repo = correspondance_repo

    def obtenir_ou_creer_ouvrage(self, section_id: int) -> Dict:
        section = self._section_chiffrable(section_id)
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM ouvrages_projet WHERE section_projet_id = ?",
                (section_id,),
            ).fetchone()
            if row:
                return self._line_dict(row)

            bibliotheque = self._ouvrage_bibliotheque_valide(conn, section_id)
            lot_id = self._ensure_lot(conn, section)
            sous_lot_id = self._ensure_sous_lot(conn, section, lot_id)
            values = self._initial_values(section, bibliotheque)
            cursor = conn.execute(
                """
                INSERT INTO ouvrages_projet (
                    sous_lot_id, section_projet_id, ouvrage_bibliotheque_id,
                    code, designation, unite, quantite,
                    ds_mo, ds_mat, ds_materiel, ds_transport, ds_st,
                    ds_total, pv_unitaire, pv_total, ordre_affichage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sous_lot_id,
                    section.id,
                    bibliotheque["id"] if bibliotheque else None,
                    section.numero_article or f"DPGF-{section.id}",
                    section.libelle,
                    section.unite or "",
                    self._decimal(section.quantite, Decimal("1")),
                    values["ds_mo"],
                    values["ds_mat"],
                    values["ds_materiel"],
                    values["ds_transport"],
                    values["ds_st"],
                    values["ds_total"],
                    values["pv_unitaire"],
                    values["pv_total"],
                    section.ordre_affichage,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM ouvrages_projet WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return self._line_dict(row)

    def preparer_chiffrage_projet(self, projet_id: int) -> List[Dict]:
        sections = [
            section for section in self.section_repo.get_by_projet(projet_id)
            if section.type_ligne in ("ouvrage", "pour_memoire")
        ]
        for section in sections:
            self.obtenir_ou_creer_ouvrage(section.id)
        return self.lister_ouvrages_projet(projet_id)

    def lister_ouvrages_projet(self, projet_id: int) -> List[Dict]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    op.*,
                    sp.id AS section_id,
                    sp.feuille_source,
                    l.id AS lot_id,
                    l.code AS lot_code,
                    l.libelle AS lot_libelle,
                    sl.id AS sous_lot_id,
                    sl.code AS sous_lot_code,
                    sl.libelle AS sous_lot_libelle
                FROM ouvrages_projet op
                JOIN sous_lots sl ON sl.id = op.sous_lot_id
                JOIN lots l ON l.id = sl.lot_id
                LEFT JOIN sections_projet sp ON sp.id = op.section_projet_id
                WHERE l.projet_id = ?
                ORDER BY l.ordre_affichage, l.id, sl.ordre_affichage, sl.id, op.ordre_affichage, op.id
                """,
                (projet_id,),
            ).fetchall()
        return [self._line_dict(row) for row in rows]

    def sauvegarder_composants_ouvrage(
        self,
        ouvrage_id: int,
        ds_mo: Decimal,
        ds_mat: Decimal,
        ds_materiel: Decimal,
        ds_transport: Decimal,
        ds_st: Decimal,
    ) -> Dict:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM ouvrages_projet WHERE id = ?", (ouvrage_id,)).fetchone()
            if not row:
                raise ValueError("Ouvrage projet introuvable.")
            before = self._line_dict(row)
            coefficient = self._coefficient_vente(before)
            quantite = self._decimal(before["quantite"], Decimal("1"))
            ds_total = self._money(ds_mo + ds_mat + ds_materiel + ds_transport + ds_st)
            pv_total = self._money(ds_total * coefficient)
            pv_unitaire = self._money(pv_total / quantite) if quantite else ZERO
            self._insert_history_conn(conn, before, "edition")
            conn.execute(
                """
                UPDATE ouvrages_projet
                SET ds_mo = ?, ds_mat = ?, ds_materiel = ?, ds_transport = ?,
                    ds_st = ?, ds_total = ?, pv_unitaire = ?, pv_total = ?,
                    date_modification = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    self._money(ds_mo),
                    self._money(ds_mat),
                    self._money(ds_materiel),
                    self._money(ds_transport),
                    self._money(ds_st),
                    ds_total,
                    pv_unitaire,
                    pv_total,
                    ouvrage_id,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM ouvrages_projet WHERE id = ?", (ouvrage_id,)).fetchone()
            return self._line_dict(row)

    def copier_depuis_bibliotheque_plusieurs(self, section_ids: Iterable[int]) -> Dict[str, int]:
        copied = 0
        skipped = 0
        for section_id in section_ids:
            try:
                self.copier_depuis_bibliotheque(section_id)
                copied += 1
            except ValueError:
                skipped += 1
        return {"copiees": copied, "ignorees": skipped}

    def sauvegarder_chiffrage(
        self,
        section_id: int,
        ds_mo: Decimal,
        ds_mat: Decimal,
        ds_materiel: Decimal,
        ds_transport: Decimal,
        ds_st: Decimal,
        coefficient_vente: Decimal,
    ) -> Dict:
        ouvrage = self.obtenir_ou_creer_ouvrage(section_id)
        section = self._section_chiffrable(section_id)
        quantite = self._decimal(section.quantite, Decimal("1"))
        ds_total = self._money(ds_mo + ds_mat + ds_materiel + ds_transport + ds_st)
        pv_total = self._money(ds_total * coefficient_vente)
        pv_unitaire = self._money(pv_total / quantite) if quantite else ZERO
        with self.db.get_connection() as conn:
            conn.execute(
                """
                UPDATE ouvrages_projet
                SET ds_mo = ?, ds_mat = ?, ds_materiel = ?, ds_transport = ?,
                    ds_st = ?, ds_total = ?, pv_unitaire = ?, pv_total = ?,
                    date_modification = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    self._money(ds_mo),
                    self._money(ds_mat),
                    self._money(ds_materiel),
                    self._money(ds_transport),
                    self._money(ds_st),
                    ds_total,
                    pv_unitaire,
                    pv_total,
                    ouvrage["id"],
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM ouvrages_projet WHERE id = ?", (ouvrage["id"],)).fetchone()
            return self._line_dict(row)

    def copier_depuis_bibliotheque(self, section_id: int) -> Dict:
        section = self._section_chiffrable(section_id)
        with self.db.get_connection() as conn:
            bibliotheque = self._ouvrage_bibliotheque_valide(conn, section_id)
            if not bibliotheque:
                raise ValueError("Aucune correspondance validée n'est disponible pour cette ligne DPGF.")
            ouvrage = self.obtenir_ou_creer_ouvrage(section_id)
            values = self._initial_values(section, bibliotheque)
            self._insert_history_conn(conn, ouvrage, "copie_bibliotheque")
            conn.execute(
                """
                UPDATE ouvrages_projet
                SET ouvrage_bibliotheque_id = ?, ds_mo = ?, ds_mat = ?,
                    ds_materiel = ?, ds_transport = ?, ds_st = ?, ds_total = ?,
                    pv_unitaire = ?, pv_total = ?, date_modification = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    bibliotheque["id"],
                    values["ds_mo"],
                    values["ds_mat"],
                    values["ds_materiel"],
                    values["ds_transport"],
                    values["ds_st"],
                    values["ds_total"],
                    values["pv_unitaire"],
                    values["pv_total"],
                    ouvrage["id"],
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM ouvrages_projet WHERE id = ?", (ouvrage["id"],)).fetchone()
            return self._line_dict(row)

    def est_surcharge_manuelle(self, section_id: int) -> bool:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT op.*, ob.fournitures_ht_import, ob.mo_ht_import, ob.materiel_ht_import,
                       ob.transport_ht_import, ob.sous_traitance_ht_import, ob.debourse_sec_import,
                       ob.pv_eg_ht_import, sp.quantite
                FROM ouvrages_projet op
                JOIN sections_projet sp ON sp.id = op.section_projet_id
                LEFT JOIN ouvrages_bibliotheque ob ON ob.id = op.ouvrage_bibliotheque_id
                WHERE op.section_projet_id = ?
                """,
                (section_id,),
            ).fetchone()
        if not row or row["ouvrage_bibliotheque_id"] is None:
            return False
        section = self._section_chiffrable(section_id)
        expected = self._initial_values(section, dict(row))
        return any(
            self._decimal(row[key]) != expected[key]
            for key in ("ds_mo", "ds_mat", "ds_materiel", "ds_transport", "ds_st", "ds_total", "pv_total")
        )

    def _section_chiffrable(self, section_id: int) -> SectionProjet:
        section = self.section_repo.get_by_id(section_id)
        if not section or section.type_ligne not in ("ouvrage", "pour_memoire"):
            raise ValueError("Seules les lignes DPGF de type ouvrage ou pour mémoire peuvent être chiffrées.")
        return section

    def _ouvrage_bibliotheque_valide(self, conn, section_id: int) -> Optional[Dict]:
        row = conn.execute(
            """
            SELECT ob.*
            FROM correspondances_dpgf c
            JOIN ouvrages_bibliotheque ob ON ob.id = c.ouvrage_bibliotheque_id
            WHERE c.ouvrage_projet_id = ? AND c.statut = 'validee'
            ORDER BY c.id DESC
            LIMIT 1
            """,
            (section_id,),
        ).fetchone()
        return dict(row) if row else None

    def _ensure_lot(self, conn, section: SectionProjet) -> int:
        top = self._top_section(section)
        code = top.numero_article or top.feuille_source or f"LOT-{top.id}"
        libelle = top.libelle or section.feuille_source or "DPGF"
        existing = conn.execute(
            "SELECT id FROM lots WHERE projet_id = ? AND code = ? AND libelle = ?",
            (section.projet_id, code, libelle),
        ).fetchone()
        if existing:
            return existing["id"]
        return conn.execute(
            "INSERT INTO lots (projet_id, code, libelle, ordre_affichage) VALUES (?, ?, ?, ?)",
            (section.projet_id, code, libelle, top.ordre_affichage),
        ).lastrowid

    def _ensure_sous_lot(self, conn, section: SectionProjet, lot_id: int) -> int:
        parent = self.section_repo.get_by_id(section.parent_id) if section.parent_id else None
        if parent and parent.type_ligne != "lot":
            code = parent.numero_article or f"SL-{parent.id}"
            libelle = parent.libelle
            ordre = parent.ordre_affichage
        else:
            code = "GENERAL"
            libelle = "Général"
            ordre = 0
        existing = conn.execute(
            "SELECT id FROM sous_lots WHERE lot_id = ? AND code = ? AND libelle = ?",
            (lot_id, code, libelle),
        ).fetchone()
        if existing:
            return existing["id"]
        return conn.execute(
            "INSERT INTO sous_lots (lot_id, code, libelle, ordre_affichage) VALUES (?, ?, ?, ?)",
            (lot_id, code, libelle, ordre),
        ).lastrowid

    def _top_section(self, section: SectionProjet) -> SectionProjet:
        current = section
        while current.parent_id:
            parent = self.section_repo.get_by_id(current.parent_id)
            if not parent:
                break
            current = parent
        return current

    def _initial_values(self, section: SectionProjet, bibliotheque: Optional[Dict]) -> Dict[str, Decimal]:
        quantite = self._decimal(section.quantite, Decimal("1"))
        if not bibliotheque:
            ds_mo = ds_mat = ds_materiel = ds_transport = ds_st = ZERO
            ds_total = ZERO
            pv_unitaire = self._decimal(section.prix_unitaire)
            pv_total = self._decimal(section.total, pv_unitaire * quantite)
        else:
            ds_mo = self._decimal(bibliotheque.get("mo_ht_import")) * quantite
            ds_mat = self._decimal(bibliotheque.get("fournitures_ht_import")) * quantite
            ds_materiel = self._decimal(bibliotheque.get("materiel_ht_import")) * quantite
            ds_transport = self._decimal(bibliotheque.get("transport_ht_import")) * quantite
            ds_st = self._decimal(bibliotheque.get("sous_traitance_ht_import")) * quantite
            ds_total = self._decimal(bibliotheque.get("debourse_sec_import"), ds_mo + ds_mat + ds_materiel + ds_transport + ds_st) * quantite
            pv_unitaire = self._decimal(bibliotheque.get("pv_eg_ht_import"), ds_total / quantite if quantite else ZERO)
            pv_total = pv_unitaire * quantite
        return {
            "ds_mo": self._money(ds_mo),
            "ds_mat": self._money(ds_mat),
            "ds_materiel": self._money(ds_materiel),
            "ds_transport": self._money(ds_transport),
            "ds_st": self._money(ds_st),
            "ds_total": self._money(ds_total),
            "pv_unitaire": self._money(pv_unitaire),
            "pv_total": self._money(pv_total),
        }

    def _line_dict(self, row) -> Dict:
        data = dict(row)
        for key in ("quantite", "ds_mo", "ds_mat", "ds_materiel", "ds_transport", "ds_st", "ds_total", "pv_unitaire", "pv_total"):
            data[key] = self._decimal(data[key])
        return data

    def _insert_history_conn(self, conn, ouvrage: Dict, origine: str):
        conn.execute(
            """
            INSERT INTO historique_ouvrages_projet (
                ouvrage_projet_id, ds_mo, ds_mat, ds_materiel, ds_transport,
                ds_st, ds_total, pv_unitaire, pv_total, origine
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ouvrage["id"],
                ouvrage["ds_mo"],
                ouvrage["ds_mat"],
                ouvrage["ds_materiel"],
                ouvrage["ds_transport"],
                ouvrage["ds_st"],
                ouvrage["ds_total"],
                ouvrage["pv_unitaire"],
                ouvrage["pv_total"],
                origine,
            ),
        )

    def _coefficient_vente(self, ouvrage: Dict) -> Decimal:
        ds_total = self._decimal(ouvrage.get("ds_total"))
        pv_total = self._decimal(ouvrage.get("pv_total"))
        if ds_total:
            return pv_total / ds_total
        return DEFAULT_COEFFICIENT_VENTE

    def _decimal(self, value, default: Decimal = ZERO) -> Decimal:
        if value is None or value == "":
            return default
        return Decimal(str(value))

    def _money(self, value: Decimal) -> Decimal:
        return self._decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
