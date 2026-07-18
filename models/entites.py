from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

@dataclass
class Projet:
    id: Optional[int]
    nom: str
    client: str
    reference: str
    statut: str
    date_creation: str
    date_modification: str

@dataclass
class Bibliotheque:
    id: Optional[int]
    nom: str
    description: str
    corps_metier: str
    actif: bool
    date_creation: str
    date_modification: str
    mapping_import_id: Optional[int] = None

@dataclass
class ParametreGeneral:
    id: Optional[int]
    cle: str
    valeur: str
    type_valeur: str
    unite: Optional[str]
    description: str
    date_modification: str

@dataclass
class Ressource:
    id: Optional[int]
    bibliotheque_id: int
    code: str
    designation: str
    type_ressource: str
    unite: str
    prix_unitaire_ht: Decimal
    attributs_techniques: Optional[str]
    actif: bool
    date_creation: str
    date_modification: str

@dataclass
class OuvrageBibliotheque:
    id: Optional[int]
    bibliotheque_id: int
    code: Optional[str]
    designation: str
    famille: Optional[str]
    unite: str
    mode_chiffrage: str
    
    # Prix importés
    fournitures_ht_import: Optional[Decimal]
    mo_heures_import: Optional[Decimal]
    taux_horaire_import: Optional[Decimal]
    mo_ht_import: Optional[Decimal]
    materiel_ht_import: Optional[Decimal]
    transport_ht_import: Optional[Decimal]
    sous_traitance_ht_import: Optional[Decimal]
    debourse_sec_import: Optional[Decimal]
    pv_st_ht_import: Optional[Decimal]
    pv_eg_ht_import: Optional[Decimal]
    
    # Prix calculés
    debourse_sec_calcule: Optional[Decimal]
    pv_st_ht_calcule: Optional[Decimal]
    pv_eg_ht_calcule: Optional[Decimal]
    
    source_calcul: str
    date_dernier_calcul: Optional[str]
    attributs_techniques: Optional[str]
    donnees_source_json: Optional[str]
    actif: bool
    date_creation: str
    date_modification: str

@dataclass
class CompositionOuvrage:
    id: Optional[int]
    ouvrage_id: int
    ressource_id: int
    quantite: Decimal
    coefficient_perte: Decimal
    ordre_affichage: int

@dataclass
class ParametreProjet:
    id: Optional[int]
    projet_id: int
    cle: str
    valeur: str
    type_valeur: str

@dataclass
class Lot:
    id: Optional[int]
    projet_id: int
    code: str
    libelle: str
    ordre_affichage: int

@dataclass
class SousLot:
    id: Optional[int]
    lot_id: int
    code: str
    libelle: str
    ordre_affichage: int

@dataclass
class OuvrageProjet:
    id: Optional[int]
    sous_lot_id: int
    ouvrage_bibliotheque_id: int
    code: str
    designation: str
    unite: str
    quantite: Decimal
    
    # Déboursés
    ds_mo: Decimal
    ds_mat: Decimal
    ds_materiel: Decimal
    ds_transport: Decimal
    ds_st: Decimal
    ds_total: Decimal
    
    # Prix
    pv_unitaire: Decimal
    pv_total: Decimal
    
    ordre_affichage: int
    date_creation: str
    date_modification: str

@dataclass
class SectionProjet:
    id: Optional[int]
    projet_id: int
    parent_id: Optional[int]
    type_ligne: str
    numero_article: Optional[str]
    numero_article_original: Optional[str]
    libelle: str
    unite: Optional[str]
    quantite: Optional[Decimal]
    prix_unitaire: Optional[Decimal]
    total: Optional[Decimal]
    pour_memoire: bool
    ordre_affichage: int
    profondeur: int
    fichier_source: Optional[str]
    feuille_source: str
    ligne_excel_source: int
    formule_total: Optional[str]
    donnees_source_json: Optional[str]
    date_creation: str
    date_modification: str

@dataclass
class CorrespondanceDpgf:
    id: Optional[int]
    ouvrage_projet_id: int
    ouvrage_bibliotheque_id: int
    score: Decimal
    origine: str
    statut: str
    date_creation: str
    date_modification: str

@dataclass
class MappingImport:
    id: Optional[int]
    nom: str
    signature_colonnes: str
    mapping_json: str
    date_creation: str
    date_derniere_utilisation: Optional[str]
    version: int = 1
    mapping_parent_id: Optional[int] = None

@dataclass
class VersionProjet:
    id: Optional[int]
    projet_id: int
    nom: str
    est_version_courante: bool
    date_creation: str
    nombre_lignes: int = 0

@dataclass
class VersionProjetLigne:
    id: Optional[int]
    version_id: int
    ouvrage_projet_id: int
    ds_mo: Decimal
    ds_mat: Decimal
    ds_materiel: Decimal
    ds_transport: Decimal
    ds_st: Decimal
    ds_total: Decimal
    pv_unitaire: Decimal
    pv_total: Decimal
