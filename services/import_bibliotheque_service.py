import pandas as pd
import json
import re
import unicodedata
import logging
import math
from datetime import date, datetime
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional, Tuple

from rapidfuzz import fuzz

from config.mapping_bibliotheques import MAPPINGS_BIBLIOTHEQUES, PARAMETRES_STANDARDS
from models.entites import OuvrageBibliotheque
from repositories.bibliotheque_repository import BibliothequeRepository
from services.parametre_service import ParametreService
from repositories.mapping_import_repository import MappingImportRepository
from repositories.ouvrage_bibliotheque_repository import OuvrageBibliothequeRepository

logger = logging.getLogger(__name__)

@dataclass
class ImportBibliothequeSummary:
    lignes_lues: int = 0
    ouvrages_importes: int = 0
    lignes_ignorees: int = 0
    erreurs: List[str] = field(default_factory=list)
    avertissements: List[str] = field(default_factory=list)
    doublons: int = 0
    unites_manquantes: int = 0
    prix_manquants: int = 0
    parametres_importes: int = 0
    feuille_parametres_traitee: bool = False
    feuille_ouvrages_traitee: bool = False
    mapping_reconnu: bool = False
    mapping_nom: str = ""

    def ajouter_erreur(self, message: str):
        self.erreurs.append(message)
        logger.error(message)

    def ajouter_avertissement(self, message: str):
        self.avertissements.append(message)
        logger.warning(message)


@dataclass
class ImportMappingAnalysis:
    filepath: str
    signature_colonnes: str
    param_sheet_name: Optional[str]
    ouvrages_sheet_name: Optional[str]
    param_columns: List[str]
    ouvrage_columns: List[str]
    previews: Dict[str, List[str]]
    result_columns: List[str]
    mapping: Optional[dict] = None
    mapping_id: Optional[int] = None
    mapping_nom: str = ""
    mapping_version: int = 1
    mapping_score: float = 0
    partial_mapping_id: Optional[int] = None
    partial_mapping_nom: str = ""
    partial_mapping_score: float = 0


class MappingImportRequired(Exception):
    def __init__(self, analysis: ImportMappingAnalysis):
        super().__init__("Mapping d'import inconnu. Validation utilisateur requise.")
        self.analysis = analysis

class ImportBibliothequeService:
    def __init__(self, parametre_service: ParametreService, ouvrage_repo: OuvrageBibliothequeRepository):
        self.parametre_service = parametre_service
        self.ouvrage_repo = ouvrage_repo
        self.db = ouvrage_repo.db
        self.mapping_repo = MappingImportRepository(self.db)
        self.bibliotheque_repo = BibliothequeRepository(self.db)
        self._ensure_legacy_cloisons_mapping()

    def slugify(self, text: str) -> str:
        """Convertit un texte en slug (minuscules, sans accents, sans caractères spéciaux, _)."""
        if pd.isna(text) or text is None:
            return ""
        text = str(text).strip().lower()
        # Supprimer les accents
        text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
        # Remplacer les espaces et autres caractères non alphanumériques par '_'
        text = re.sub(r'[^a-z0-9]+', '_', text)
        # Supprimer les underscores multiples et aux extrémités
        text = re.sub(r'_+', '_', text).strip('_')
        return text

    def parse_numeric(self, value: Any) -> Optional[Decimal]:
        if pd.isna(value) or value is None or str(value).strip() in ('', '-', 'N/A'):
            return None
        
        val_str = str(value).strip().replace(' ', '').replace(',', '.')
        
        # Gestion des pourcentages
        is_percentage = False
        if val_str.endswith('%'):
            is_percentage = True
            val_str = val_str[:-1].strip()
            
        try:
            dec_val = Decimal(val_str)
            if is_percentage:
                dec_val = dec_val / Decimal('100')
            return dec_val
        except InvalidOperation:
            return None

    def detect_type(self, value: Any) -> Tuple[Any, str]:
        if pd.isna(value) or value is None:
            return None, 'text'

        date_value = self._normalize_date_value(value)
        if date_value:
            return date_value, "text"
            
        val_str = str(value).strip().lower()
        
        # Boolean
        if val_str in ['oui', 'true', 'vrai']:
            return True, 'boolean'
        if val_str in ['non', 'false', 'faux']:
            return False, 'boolean'
            
        # Try numeric
        num_val = self.parse_numeric(value)
        if num_val is not None:
            # Check if it's strictly integer
            if int(num_val) == num_val and '%' not in str(value):
                return int(num_val), 'integer'
            else:
                return float(num_val), 'decimal' # Convert to float for JSON compatibility if needed, or string. Actually, we return the string or format
                
        return str(value).strip(), 'text'

    def import_fichier(
        self,
        filepath: str,
        bibliotheque_id: int,
        config_type: str = "cloisons",
        mapping_override: Optional[dict] = None,
        mapping_nom: Optional[str] = None,
        mapping_parent_id: Optional[int] = None,
        creer_nouvelle_version: bool = False,
    ) -> ImportBibliothequeSummary:
        summary = ImportBibliothequeSummary()
        analysis = self.analyser_mapping(filepath)
        mapping = mapping_override or analysis.mapping
        if not mapping and analysis.ouvrages_sheet_name:
            raise MappingImportRequired(analysis)
        if mapping_override:
            mapping_name = mapping_nom or "Mapping validé"
            if creer_nouvelle_version and mapping_parent_id:
                parent = self.mapping_repo.get_by_id(mapping_parent_id)
                if not parent:
                    raise ValueError("Mapping parent introuvable.")
                mapping_id = self.mapping_repo.create_version(
                    parent,
                    analysis.signature_colonnes,
                    json.dumps(mapping_override, ensure_ascii=False),
                    nom=mapping_name,
                )
            else:
                mapping_id = self.mapping_repo.save(
                    mapping_name,
                    analysis.signature_colonnes,
                    json.dumps(mapping_override, ensure_ascii=False),
                )
            self.bibliotheque_repo.update_mapping_import_id(bibliotheque_id, mapping_id)
            summary.mapping_reconnu = False
            summary.mapping_nom = mapping_name
        elif analysis.mapping_id:
            self.mapping_repo.mark_used(analysis.mapping_id)
            self.bibliotheque_repo.update_mapping_import_id(bibliotheque_id, analysis.mapping_id)
            summary.mapping_reconnu = True
            summary.mapping_nom = analysis.mapping_nom
            logger.info("Mapping '%s' reconnu et appliqué.", analysis.mapping_nom)

        xls = pd.ExcelFile(filepath)
        
        if analysis.param_sheet_name:
            df_params = pd.read_excel(xls, sheet_name=analysis.param_sheet_name, dtype=object)
            summary.feuille_parametres_traitee = True
            param_mapping = (mapping or self._legacy_cloisons_mapping()).get("parametres", {})
            summary.parametres_importes = self._import_parametres(df_params, param_mapping, summary)
        else:
            summary.ajouter_avertissement("Feuille de paramètres non trouvée.")

        if analysis.ouvrages_sheet_name and mapping:
            df_ouvrages = pd.read_excel(xls, sheet_name=analysis.ouvrages_sheet_name, dtype=object)
            summary.feuille_ouvrages_traitee = True
            self._import_ouvrages(df_ouvrages, mapping, bibliotheque_id, summary)
        elif not analysis.ouvrages_sheet_name:
            summary.ajouter_avertissement("Feuille d'ouvrages non trouvée.")
        else:
            raise MappingImportRequired(analysis)
        return summary

    def analyser_mapping(self, filepath: str) -> ImportMappingAnalysis:
        xls = pd.ExcelFile(filepath)
        sheet_names = xls.sheet_names
        param_sheet_name = self._detect_param_sheet(sheet_names)
        ouvrages_sheet_name = self._detect_ouvrages_sheet(xls)
        param_columns = self._sheet_columns(xls, param_sheet_name) if param_sheet_name else []
        ouvrage_columns = self._sheet_columns(xls, ouvrages_sheet_name) if ouvrages_sheet_name else []
        signature = self.signature_colonnes(param_columns, ouvrage_columns)
        match = self._find_compatible_mapping(param_columns, ouvrage_columns)
        partial = self._find_partial_mapping(param_columns, ouvrage_columns, exclude_id=match[0].id if match else None)
        mapping_entity = match[0] if match else None
        mapping = self._resolve_mapping_columns(json.loads(mapping_entity.mapping_json), param_columns, ouvrage_columns) if mapping_entity else None
        return ImportMappingAnalysis(
            filepath=filepath,
            signature_colonnes=signature,
            param_sheet_name=param_sheet_name,
            ouvrages_sheet_name=ouvrages_sheet_name,
            param_columns=param_columns,
            ouvrage_columns=ouvrage_columns,
            previews=self._column_previews(xls, ouvrages_sheet_name) if ouvrages_sheet_name else {},
            result_columns=self.detect_result_columns(ouvrage_columns),
            mapping=mapping,
            mapping_id=mapping_entity.id if mapping_entity else None,
            mapping_nom=mapping_entity.nom if mapping_entity else "",
            mapping_version=mapping_entity.version if mapping_entity else 1,
            mapping_score=match[1] if match else 0,
            partial_mapping_id=partial[0].id if partial else None,
            partial_mapping_nom=partial[0].nom if partial else "",
            partial_mapping_score=partial[1] if partial else 0,
        )

    def signature_colonnes(self, param_columns: List[str], ouvrage_columns: List[str]) -> str:
        payload = {
            "parametres": sorted(self.slugify(col) for col in param_columns),
            "ouvrages": sorted(self.slugify(col) for col in ouvrage_columns),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def detect_result_columns(self, columns: List[str]) -> List[str]:
        result_keywords = (
            "debourse_sec", "debours_sec", "prix_sous_traitant", "prix_st",
            "prix_entreprise_generale", "prix_eg", "coef_st", "coef_eg",
            "pv_st", "pv_eg",
        )
        return [col for col in columns if any(keyword in self.slugify(col) for keyword in result_keywords)]

    def _find_compatible_mapping(self, param_columns: List[str], ouvrage_columns: List[str]) -> Optional[tuple]:
        matches = []
        for mapping_entity in self.mapping_repo.list_all():
            mapping = json.loads(mapping_entity.mapping_json)
            score = self._mapping_match_score(mapping, param_columns, ouvrage_columns)
            if score >= 90:
                matches.append((mapping_entity, score))
        if not matches:
            return None
        matches.sort(key=lambda item: (item[1], item[0].version), reverse=True)
        return matches[0]

    def _find_partial_mapping(self, param_columns: List[str], ouvrage_columns: List[str], exclude_id: Optional[int] = None) -> Optional[tuple]:
        matches = []
        for mapping_entity in self.mapping_repo.list_all():
            if mapping_entity.id == exclude_id:
                continue
            mapping = json.loads(mapping_entity.mapping_json)
            score = self._mapping_match_score(mapping, param_columns, ouvrage_columns)
            if 70 <= score < 90:
                matches.append((mapping_entity, score))
        if not matches:
            return None
        matches.sort(key=lambda item: (item[1], item[0].version), reverse=True)
        return matches[0]

    def _mapping_match_score(self, mapping: dict, param_columns: List[str], ouvrage_columns: List[str]) -> float:
        essential = self._essential_mapping_columns(mapping)
        if not essential:
            return 0
        actual_columns = [self.slugify(col) for col in ouvrage_columns]
        scores = []
        for _field, expected, optional in essential:
            if optional:
                match = self._best_column_match(expected, ouvrage_columns)
                if match is None:
                    continue
            best = self._best_column_score(expected, actual_columns)
            scores.append(best)
        if not scores:
            return 0
        matched = sum(1 for score in scores if score >= 90)
        return (matched / len(scores)) * 100

    def _essential_mapping_columns(self, mapping: dict) -> List[tuple]:
        ouvrages = mapping.get("ouvrages", {})
        columns = []
        if ouvrages.get("code"):
            columns.append(("code", ouvrages["code"], True))
        for field in ("famille", "unite"):
            if ouvrages.get(field):
                columns.append((field, ouvrages[field], False))
        designation = ouvrages.get("designation", {})
        if designation.get("mode") == "direct" and designation.get("colonne"):
            columns.append(("designation", designation["colonne"], False))
        elif designation.get("mode") == "concat":
            columns.extend((f"designation_{index}", col, False) for index, col in enumerate(designation.get("colonnes", [])) if col)
        for field, column in ouvrages.get("components", {}).items():
            if column:
                columns.append((field, column, False))
        return columns

    def _best_column_score(self, expected: str, actual_slug_columns: List[str]) -> float:
        expected_slug = self.slugify(expected)
        if not expected_slug:
            return 0
        if expected_slug in actual_slug_columns:
            return 100
        return max((fuzz.token_set_ratio(expected_slug, actual) for actual in actual_slug_columns), default=0)

    def _best_column_match(self, expected: str, actual_columns: List[str], threshold: float = 90) -> Optional[str]:
        scored = [
            (self._best_column_score(expected, [self.slugify(column)]), column)
            for column in actual_columns
        ]
        if not scored:
            return None
        score, column = max(scored, key=lambda item: item[0])
        return column if score >= threshold else None

    def _resolve_mapping_columns(self, mapping: dict, param_columns: List[str], ouvrage_columns: List[str]) -> dict:
        resolved = json.loads(json.dumps(mapping))
        param = resolved.get("parametres", {})
        for key, column in list(param.items()):
            param[key] = self._best_column_match(column, param_columns) if column else None

        ouvrages = resolved.get("ouvrages", {})
        if ouvrages.get("code"):
            ouvrages["code"] = self._best_column_match(ouvrages["code"], ouvrage_columns)
        for key in ("famille", "unite"):
            if ouvrages.get(key):
                ouvrages[key] = self._best_column_match(ouvrages[key], ouvrage_columns)
        designation = ouvrages.get("designation", {})
        if designation.get("mode") == "direct" and designation.get("colonne"):
            designation["colonne"] = self._best_column_match(designation["colonne"], ouvrage_columns)
        elif designation.get("mode") == "concat":
            designation["colonnes"] = [
                match for column in designation.get("colonnes", [])
                for match in [self._best_column_match(column, ouvrage_columns)]
                if match
            ]
        for group_name in ("components", "audit"):
            group = ouvrages.get(group_name, {})
            for key, column in list(group.items()):
                group[key] = self._best_column_match(column, ouvrage_columns) if column else None
        return resolved

    def proposer_mapping(self, analysis: ImportMappingAnalysis) -> dict:
        if analysis.partial_mapping_id:
            parent = self.mapping_repo.get_by_id(analysis.partial_mapping_id)
            if parent:
                return self._resolve_mapping_columns(json.loads(parent.mapping_json), analysis.param_columns, analysis.ouvrage_columns)

        cols = analysis.ouvrage_columns
        result_cols = set(analysis.result_columns)

        def pick(*candidates):
            candidate_slugs = [self.slugify(candidate) for candidate in candidates]
            for col in cols:
                if col in result_cols:
                    continue
                slug = self.slugify(col)
                if slug in candidate_slugs or any(candidate in slug for candidate in candidate_slugs):
                    return col
            return None

        direct_designation = pick("Désignation", "Designation", "Libellé", "Libelle")
        mapping = {
            "parametres": {
                "parametre": self._find_column(analysis.param_columns, "Paramètre"),
                "valeur": self._find_column(analysis.param_columns, "Valeur"),
                "unite": self._find_column(analysis.param_columns, "Unité"),
                "commentaire": self._find_column(analysis.param_columns, "Commentaire"),
            },
            "ouvrages": {
                "code": pick("Code"),
                "famille": pick("Famille"),
                "unite": pick("Unité", "U"),
                "designation": {"mode": "direct", "colonne": direct_designation} if direct_designation else {
                    "mode": "concat",
                    "colonnes": [col for col in [pick("Type"), pick("Configuration")] if col],
                },
                "components": {
                    "fournitures": pick("Fournitures HT/u", "Fournitures €", "Fournitures"),
                    "heures_mo": pick("MO h/u", "Heures MO"),
                    "taux_horaire": pick("Taux horaire"),
                    "materiel": pick("Matériel €", "Materiel"),
                    "transport": pick("Transport"),
                    "sous_traitance": pick("Sous-traitance", "Sous traitance"),
                },
                "audit": {
                    "debourse_sec": self._find_column(cols, "Déboursé sec", "Déboursé sec €"),
                    "pv_st": self._find_column(cols, "PV ST HT", "Prix Sous-traitant €"),
                    "pv_eg": self._find_column(cols, "PV EG HT", "Prix Entreprise Générale €"),
                    "coef_st": self._find_column(cols, "Coef ST"),
                    "coef_eg": self._find_column(cols, "Coef EG"),
                },
            },
        }
        return mapping

    def valider_mapping(self, mapping: dict):
        ouvrages = mapping.get("ouvrages", {})
        assigned = []
        for key in ("code", "famille", "unite"):
            value = ouvrages.get(key)
            if value:
                assigned.append(value)
        designation = ouvrages.get("designation", {})
        if designation.get("mode") == "direct" and designation.get("colonne"):
            assigned.append(designation["colonne"])
        elif designation.get("mode") == "concat":
            assigned.extend(col for col in designation.get("colonnes", []) if col)

        for value in ouvrages.get("components", {}).values():
            if value:
                assigned.append(value)

        duplicates = sorted({col for col in assigned if assigned.count(col) > 1})
        if duplicates:
            raise ValueError(f"Une colonne Excel est assignée plusieurs fois : {', '.join(duplicates)}")
        if not ouvrages.get("unite"):
            raise ValueError("Le champ Unité doit être associé à une colonne.")
        if not self._designation_mapping_valid(designation):
            raise ValueError("La désignation doit être associée à une colonne ou construite depuis 2 à 4 colonnes.")

    def _import_parametres(self, df: pd.DataFrame, config: dict, summary: ImportBibliothequeSummary) -> int:
        df_cols_lower = {self.slugify(str(c)): c for c in df.columns}

        sqlite_to_excel = {
            field: df_cols_lower.get(self.slugify(excel_col))
            for field, excel_col in config.items()
            if excel_col
        }
                
        c_p = sqlite_to_excel.get('parametre')
        c_v = sqlite_to_excel.get('valeur')
        c_u = sqlite_to_excel.get('unite')
        c_c = sqlite_to_excel.get('commentaire')
        
        if not c_p or not c_v:
            summary.ajouter_erreur("Colonnes Paramètre ou Valeur manquantes dans la feuille de paramètres.")
            return 0

        cles_generees = set()
        imported = 0

        for _, row in df.iterrows():
            param_nom = str(row[c_p]).strip()
            if pd.isna(row[c_p]) or not param_nom:
                continue

            # Trouver la clé technique
            cle_tech = None
            for p_std, p_cle in PARAMETRES_STANDARDS.items():
                if self.slugify(param_nom) == self.slugify(p_std):
                    cle_tech = p_cle
                    break
            
            if not cle_tech:
                cle_tech = self.slugify(param_nom)
                
            if cle_tech in cles_generees:
                summary.ajouter_erreur(f"Conflit de clé détecté pour '{param_nom}' -> '{cle_tech}'. Ligne ignorée.")
                continue
                
            cles_generees.add(cle_tech)

            val_raw = row[c_v]
            val_formattee, val_type = self.detect_type(val_raw)
            valeur_str = str(val_formattee).lower() if val_type == 'boolean' else str(val_formattee)

            unite = str(row[c_u]).strip() if c_u and not pd.isna(row[c_u]) else ""
            comment = str(row[c_c]).strip() if c_c and not pd.isna(row[c_c]) else ""
            description = f"{param_nom} — {comment}" if comment else param_nom

            self.parametre_service.creer_ou_modifier_parametre(
                cle=cle_tech,
                valeur=valeur_str,
                type_valeur=val_type,
                unite=unite,
                description=description
            )
            imported += 1
            logger.info(f"Paramètre importé : {cle_tech} = {valeur_str}")
        return imported

    def _clean_json_value(self, val: Any) -> Any:
        if pd.isna(val) or val is None or str(val).strip() in ('', '-', 'N/A'):
            return None
        if isinstance(val, float) and math.isnan(val):
            return None
        if isinstance(val, Decimal):
            return float(val)
        return val

    def _import_ouvrages(self, df: pd.DataFrame, config: dict, bibliotheque_id: int, summary: ImportBibliothequeSummary):
        self.valider_mapping(config)
        ouvrages_mapping = config.get("ouvrages", {})
        components_mapping = ouvrages_mapping.get("components", {})
        audit_mapping = ouvrages_mapping.get("audit", {})
        coef_st_global = self.parametre_service.obtenir_parametre("coefficient_vente_st")
        coef_eg_global = self.parametre_service.obtenir_parametre("coefficient_vente_eg")
        taux_global = self.parametre_service.obtenir_parametre("taux_horaire_base")
        val_coef_st_global = self.parse_numeric(coef_st_global.valeur) if coef_st_global else Decimal("1")
        val_coef_eg_global = self.parse_numeric(coef_eg_global.valeur) if coef_eg_global else Decimal("1")
        val_taux_global = self.parse_numeric(taux_global.valeur) if taux_global else Decimal("0")
        summary.lignes_lues = len(df)
        result_columns = set(filter(None, audit_mapping.values()))
        assigned_columns = self._assigned_columns(ouvrages_mapping)

        for _, row in df.iterrows():
            code_val = self._cell_text(row, ouvrages_mapping.get("code")) or None
            famille = self._cell_text(row, ouvrages_mapping.get("famille")) or None
            designation = self._build_designation(row, ouvrages_mapping.get("designation", {}))
            if not designation:
                summary.lignes_ignorees += 1
                summary.ajouter_erreur(f"Ligne ignorée : impossible de construire la désignation. Ligne {row.to_dict()}")
                continue

            composants = {
                "fournitures": self._mapped_decimal(row, components_mapping.get("fournitures")),
                "heures_mo": self._mapped_decimal(row, components_mapping.get("heures_mo")),
                "materiel": self._mapped_decimal(row, components_mapping.get("materiel")),
                "transport": self._mapped_decimal(row, components_mapping.get("transport")),
                "sous_traitance": self._mapped_decimal(row, components_mapping.get("sous_traitance")),
            }
            taux = self._mapped_decimal(row, components_mapping.get("taux_horaire"))
            if taux == Decimal("0"):
                taux = val_taux_global or Decimal("0")
            fournitures = composants["fournitures"]
            mo_h = composants["heures_mo"]
            mo_ht = mo_h * taux
            materiel = composants["materiel"]
            transport = composants["transport"]
            sous_traitance = composants["sous_traitance"]
            ds = self.calculer_debourse_sec(composants, taux)
            pv_st = ds * (val_coef_st_global or Decimal("1"))
            pv_eg = ds * (val_coef_eg_global or Decimal("1"))
            self._warn_audit_differences(row, audit_mapping, designation, ds, pv_st, pv_eg, summary)

            attributs = self._technical_attributes(row, assigned_columns, result_columns)
            source_data = {str(k): self._clean_json_value(v) for k, v in row.items()}

            unite = self._cell_text(row, ouvrages_mapping.get("unite"))
            if not unite:
                summary.unites_manquantes += 1
                summary.ajouter_avertissement(f"Ligne '{designation}' : unité manquante.")

            ouvrage = OuvrageBibliotheque(
                id=None,
                bibliotheque_id=bibliotheque_id,
                code=code_val,
                designation=designation,
                famille=famille,
                unite=unite,
                mode_chiffrage='importe',
                fournitures_ht_import=fournitures,
                mo_heures_import=mo_h,
                taux_horaire_import=taux,
                mo_ht_import=mo_ht,
                materiel_ht_import=materiel,
                transport_ht_import=transport,
                sous_traitance_ht_import=sous_traitance,
                debourse_sec_import=ds,
                pv_st_ht_import=pv_st,
                pv_eg_ht_import=pv_eg,
                debourse_sec_calcule=None,
                pv_st_ht_calcule=None,
                pv_eg_ht_calcule=None,
                source_calcul='importe',
                date_dernier_calcul=None,
                attributs_techniques=json.dumps(attributs, ensure_ascii=False),
                donnees_source_json=json.dumps(source_data, ensure_ascii=False),
                actif=True,
                date_creation="",
                date_modification=""
            )

            # Les doublons déjà présents dans la même bibliothèque sont ignorés :
            # un réimport ne doit pas écraser une bibliothèque déjà validée.
            if code_val:
                existant = self.ouvrage_repo.get_by_bibliotheque_and_code(bibliotheque_id, code_val)
                if existant:
                    summary.doublons += 1
                    continue
            
            self.ouvrage_repo.create(ouvrage)
            summary.ouvrages_importes += 1

    def calculer_debourse_sec(self, composants: Dict[str, Decimal], taux_horaire: Decimal) -> Decimal:
        fournitures = composants.get("fournitures", Decimal(0))
        heures_mo = composants.get("heures_mo", Decimal(0))
        materiel = composants.get("materiel", Decimal(0))
        transport = composants.get("transport", Decimal(0))
        sous_traitance = composants.get("sous_traitance", Decimal(0))
        return fournitures + (heures_mo * taux_horaire) + materiel + transport + sous_traitance

    def _detect_param_sheet(self, sheet_names: List[str]) -> Optional[str]:
        return next((sheet for sheet in sheet_names if "parametre" in self.slugify(sheet)), None)

    def _detect_ouvrages_sheet(self, xls: pd.ExcelFile) -> Optional[str]:
        fallback_base_sheet = None
        for sheet in xls.sheet_names:
            slug = self.slugify(sheet)
            if "base" not in slug:
                continue
            if fallback_base_sheet is None:
                fallback_base_sheet = sheet
            columns = self._sheet_columns(xls, sheet)
            slugs = {self.slugify(column) for column in columns}
            if {"famille", "unite"}.issubset(slugs) and (
                "designation" in slugs
                or {"type", "configuration"}.issubset(slugs)
            ):
                return sheet
        return fallback_base_sheet

    def _sheet_columns(self, xls: pd.ExcelFile, sheet_name: str) -> List[str]:
        return [str(col) for col in pd.read_excel(xls, sheet_name=sheet_name, nrows=0).columns]

    def _column_previews(self, xls: pd.ExcelFile, sheet_name: str) -> Dict[str, List[str]]:
        df = pd.read_excel(xls, sheet_name=sheet_name, dtype=object)
        previews = {}
        for column in df.columns:
            values = []
            for value in df[column]:
                if not pd.isna(value) and str(value).strip():
                    values.append(str(value).strip())
                if len(values) == 3:
                    break
            previews[str(column)] = values
        return previews

    def _find_column(self, columns: List[str], *names: str) -> Optional[str]:
        wanted = {self.slugify(name) for name in names}
        for column in columns:
            slug = self.slugify(column)
            if slug in wanted:
                return column
        return None

    def _designation_mapping_valid(self, designation: dict) -> bool:
        if designation.get("mode") == "direct":
            return bool(designation.get("colonne"))
        if designation.get("mode") == "concat":
            columns = [col for col in designation.get("colonnes", []) if col]
            return 2 <= len(columns) <= 4
        return False

    def _assigned_columns(self, ouvrages_mapping: dict) -> set:
        assigned = set()
        for key in ("code", "famille", "unite"):
            if ouvrages_mapping.get(key):
                assigned.add(ouvrages_mapping[key])
        designation = ouvrages_mapping.get("designation", {})
        if designation.get("mode") == "direct" and designation.get("colonne"):
            assigned.add(designation["colonne"])
        if designation.get("mode") == "concat":
            assigned.update(col for col in designation.get("colonnes", []) if col)
        assigned.update(col for col in ouvrages_mapping.get("components", {}).values() if col)
        return assigned

    def _cell_text(self, row, column: Optional[str]) -> str:
        if not column or column not in row or pd.isna(row[column]):
            return ""
        return str(row[column]).strip()

    def _build_designation(self, row, designation_mapping: dict) -> str:
        if designation_mapping.get("mode") == "direct":
            return self._cell_text(row, designation_mapping.get("colonne"))
        if designation_mapping.get("mode") == "concat":
            parts = [self._cell_text(row, col) for col in designation_mapping.get("colonnes", [])]
            parts = [part for part in parts if part]
            if len(parts) >= 3:
                return f"{parts[0]} - {' '.join(parts[1:])}"
            return " ".join(parts)
        return ""

    def _mapped_decimal(self, row, column: Optional[str]) -> Decimal:
        if not column or column not in row:
            return Decimal("0")
        value = self.parse_numeric(row[column])
        return value if value is not None else Decimal("0")

    def _technical_attributes(self, row, assigned_columns: set, result_columns: set) -> dict:
        attributes = {}
        for column, value in row.items():
            if column in assigned_columns or column in result_columns:
                continue
            clean_value = self._clean_json_value(value)
            if clean_value is not None:
                attributes[self.slugify(str(column))] = clean_value
        return attributes

    def _warn_audit_differences(
        self,
        row,
        audit_mapping: dict,
        designation: str,
        ds: Decimal,
        pv_st: Decimal,
        pv_eg: Decimal,
        summary: ImportBibliothequeSummary,
    ):
        for label, column, calculated in (
            ("déboursé sec", audit_mapping.get("debourse_sec"), ds),
            ("PV ST", audit_mapping.get("pv_st"), pv_st),
            ("PV EG", audit_mapping.get("pv_eg"), pv_eg),
        ):
            if not column or column not in row:
                continue
            source_value = self.parse_numeric(row[column])
            if source_value is None or source_value == 0:
                continue
            reference = max(abs(source_value), Decimal("0.01"))
            if abs(source_value - calculated) / reference > Decimal("0.01"):
                summary.ajouter_avertissement(
                    f"Ligne '{designation}' : {label} fichier ({source_value}) différent du recalcul ({calculated})."
                )

    def _normalize_date_value(self, value: Any) -> Optional[str]:
        if isinstance(value, pd.Timestamp):
            return value.date().isoformat()
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip() if value is not None else ""
        match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", text)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month}-{day}"
        match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
        if match:
            return text
        return None

    def _legacy_cloisons_mapping(self) -> dict:
        return {
            "parametres": {
                "parametre": "Paramètre",
                "valeur": "Valeur",
                "unite": "Unité",
                "commentaire": "Commentaire",
            },
            "ouvrages": {
                "code": "Code",
                "famille": "Famille",
                "unite": "Unité",
                "designation": {"mode": "concat", "colonnes": ["Type", "Configuration"]},
                "components": {
                    "fournitures": "Fournitures HT/u",
                    "heures_mo": "MO h/u",
                    "taux_horaire": "Taux horaire",
                    "materiel": None,
                    "transport": None,
                    "sous_traitance": None,
                },
                "audit": {
                    "debourse_sec": "Déboursé sec",
                    "pv_st": "PV ST HT",
                    "pv_eg": "PV EG HT",
                    "coef_st": "Coef ST",
                    "coef_eg": "Coef EG",
                },
            },
        }

    def _ensure_legacy_cloisons_mapping(self):
        config = MAPPINGS_BIBLIOTHEQUES["cloisons"]
        param_cols = list(config["feuille_parametres"]["colonnes"].keys())
        ouvrage_cols = []
        ouvrage_cols.extend(config["feuille_ouvrages"]["colonnes_directes"].keys())
        ouvrage_cols.extend(config["feuille_ouvrages"]["attributs_techniques"].keys())
        signature = self.signature_colonnes(param_cols, ouvrage_cols)
        if not self.mapping_repo.get_by_signature(signature):
            self.mapping_repo.save(
                "Cloisons (modèle historique)",
                signature,
                json.dumps(self._legacy_cloisons_mapping(), ensure_ascii=False),
            )
