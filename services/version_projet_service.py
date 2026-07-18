from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from repositories.version_projet_repository import VersionProjetRepository


COMPONENTS = [
    ("ds_mo", "MO"),
    ("ds_mat", "Matériaux"),
    ("ds_materiel", "Matériel"),
    ("ds_transport", "Transport"),
    ("ds_st", "Sous-traitance"),
    ("ds_total", "Déboursé sec total"),
    ("pv_total", "Prix de vente total"),
]

SOURCE_ACTUEL = "actuel"


class VersionProjetService:
    def __init__(self, repository: VersionProjetRepository):
        self.repository = repository

    def creer_version(self, projet_id: int, nom: str) -> int:
        nom = (nom or "").strip()
        if not nom:
            raise ValueError("Le nom de la version est obligatoire.")
        return self.repository.creer_snapshot(projet_id, nom, est_version_courante=True)

    def dupliquer_version(self, version_source_id: int, nom: str) -> int:
        nom = (nom or "").strip()
        if not nom:
            raise ValueError("Le nom de la nouvelle version est obligatoire.")
        return self.repository.dupliquer_version_vers_actuel(version_source_id, nom)

    def a_modifications_non_sauvegardees(self, projet_id: int) -> bool:
        return self.repository.etat_actuel_different_derniere_version(projet_id)

    def lister_versions(self, projet_id: int):
        return self.repository.lister_par_projet(projet_id)

    def supprimer_version(self, version_id: int) -> None:
        self.repository.supprimer(version_id)

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
        return self.repository.sauvegarder_composants_ligne_version(
            version_id,
            ouvrage_projet_id,
            ds_mo,
            ds_mat,
            ds_materiel,
            ds_transport,
            ds_st,
        )

    def sauvegarder_ligne_version(self, version_id: int, ouvrage_projet_id: int, values: Dict[str, Decimal]) -> Dict:
        return self.repository.sauvegarder_ligne_version(version_id, ouvrage_projet_id, values)

    def lister_lots(self, projet_id: int) -> List[Dict]:
        return self.repository.lister_lots(projet_id)

    def comparer(
        self,
        projet_id: int,
        reference_source: str,
        compare_source: str,
        lot_id: Optional[int] = None,
        top_limit: int = 20,
    ) -> Dict:
        reference = self._aggregate_source(projet_id, reference_source, lot_id)
        comparee = self._aggregate_source(projet_id, compare_source, lot_id)
        lignes_reference = self._lines_source(projet_id, reference_source, lot_id)
        lignes_comparees = self._lines_source(projet_id, compare_source, lot_id)

        rows = []
        for key, label in COMPONENTS:
            ref_value = reference[key]
            cmp_value = comparee[key]
            diff_amount = cmp_value - ref_value
            rows.append({
                "cle": key,
                "composante": label,
                "reference": ref_value,
                "comparee": cmp_value,
                "ecart_montant": diff_amount,
                "ecart_pourcentage": self._percent(diff_amount, ref_value),
                "ecart_formate": self.format_ecart(diff_amount, ref_value),
            })

        impacted = self._top_impacted_lines(lignes_reference, lignes_comparees, top_limit)
        return {
            "reference": reference,
            "comparee": comparee,
            "lignes": rows,
            "top_impacted": impacted,
            "pv_baisse": comparee["pv_total"] < reference["pv_total"],
            "pv_hausse": comparee["pv_total"] > reference["pv_total"],
        }

    def pie_data(self, aggregate: Dict[str, Decimal]) -> List[Dict]:
        total = aggregate["ds_total"]
        result = []
        for key, label in COMPONENTS[:5]:
            value = aggregate[key]
            result.append({
                "cle": key,
                "label": label,
                "valeur": value,
                "pourcentage": self._percent(value, total),
            })
        return result

    def format_euro(self, value: Decimal) -> str:
        value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sign = "-" if value < 0 else ""
        value = abs(value)
        whole, cents = f"{value:.2f}".split(".")
        groups = []
        while whole:
            groups.append(whole[-3:])
            whole = whole[:-3]
        return f"{sign}{' '.join(reversed(groups))},{cents} €"

    def format_percent(self, value: Optional[Decimal]) -> str:
        if value is None:
            return "n/a"
        rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sign = "+" if rounded > 0 else ""
        return f"{sign}{str(rounded).replace('.', ',')} %"

    def format_ecart(self, diff_amount: Decimal, reference: Decimal) -> str:
        percent = self.format_percent(self._percent(diff_amount, reference))
        amount = self.format_euro(diff_amount)
        if diff_amount > 0:
            amount = f"+{amount}"
        return f"{percent} / {amount}"

    def _aggregate_source(self, projet_id: int, source: str, lot_id: Optional[int]) -> Dict[str, Decimal]:
        if source == SOURCE_ACTUEL:
            return self.repository.agreger_actuel(projet_id, lot_id)
        return self.repository.agreger_version(int(source), lot_id)

    def _lines_source(self, projet_id: int, source: str, lot_id: Optional[int]) -> Dict[int, Dict]:
        if source == SOURCE_ACTUEL:
            return self.repository.lignes_actuelles(projet_id, lot_id)
        return self.repository.lignes_version(int(source), lot_id)

    def _top_impacted_lines(self, reference: Dict[int, Dict], comparee: Dict[int, Dict], limit: int) -> List[Dict]:
        ids = set(reference) | set(comparee)
        impacted = []
        for ouvrage_id in ids:
            ref_line = reference.get(ouvrage_id)
            cmp_line = comparee.get(ouvrage_id)
            label_line = cmp_line or ref_line or {}
            ref_total = ref_line["ds_total"] if ref_line else Decimal("0")
            cmp_total = cmp_line["ds_total"] if cmp_line else Decimal("0")
            diff = cmp_total - ref_total
            impacted.append({
                "ouvrage_projet_id": ouvrage_id,
                "code": label_line.get("code") or "",
                "designation": label_line.get("designation") or "",
                "lot": label_line.get("lot_libelle") or "",
                "reference": ref_total,
                "comparee": cmp_total,
                "ecart_montant": diff,
                "ecart_formate": self.format_ecart(diff, ref_total),
            })
        impacted.sort(key=lambda item: abs(item["ecart_montant"]), reverse=True)
        return impacted[:limit]

    def _percent(self, amount: Decimal, reference: Decimal) -> Optional[Decimal]:
        if reference == 0:
            return None if amount != 0 else Decimal("0")
        return (amount / reference) * Decimal("100")
