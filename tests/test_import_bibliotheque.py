import pytest
import pandas as pd
import json
from pathlib import Path
from database.db_manager import DatabaseManager
from repositories.ouvrage_bibliotheque_repository import OuvrageBibliothequeRepository
from repositories.bibliotheque_repository import BibliothequeRepository
from repositories.parametre_repository import ParametreRepository
from services.bibliotheque_service import BibliothequeService
from services.parametre_service import ParametreService
from services.import_bibliotheque_service import ImportBibliothequeService, MappingImportRequired
from models.entites import Bibliotheque

@pytest.fixture
def temp_db_manager(tmp_path):
    db_path = tmp_path / "test_import.db"
    migrations_dir = Path(__file__).parent.parent / "database" / "migrations"
    return DatabaseManager(db_path=db_path, migrations_dir=migrations_dir)

@pytest.fixture
def import_service(temp_db_manager):
    param_repo = ParametreRepository(temp_db_manager)
    param_service = ParametreService(param_repo)
    ouvrage_repo = OuvrageBibliothequeRepository(temp_db_manager)
    return ImportBibliothequeService(param_service, ouvrage_repo)

@pytest.fixture
def biblio_id(temp_db_manager):
    repo = BibliothequeRepository(temp_db_manager)
    return repo.create(Bibliotheque(id=None, nom="Test", description="", corps_metier="", actif=True, date_creation="", date_modification=""))

def test_import_parametres(import_service, temp_db_manager, tmp_path, biblio_id):
    # Prepare data
    df_params = pd.DataFrame({
        "Paramètre": [
            "Taux horaire MO", 
            "Marge sécurité matériaux", 
            "Paramètre Inconnu", 
            "Élément avec Accénts",
            "Paramètre Inconnu ", # Collision test
            "Coef %"
        ],
        "Valeur": ["45,50", "15 %", "Oui", "Texte simple", "Autre", "25%"],
        "Unité": ["€", "%", "", "", "", "%"],
        "Commentaire": ["", "Sécurité", "", "", "Devrait être ignoré pour cause de collision", ""]
    })
    
    file_path = tmp_path / "test_cloisons.xlsx"
    with pd.ExcelWriter(file_path) as writer:
        df_params.to_excel(writer, sheet_name="01_PARAMETRES", index=False)
        
    import_service.import_fichier(str(file_path), biblio_id)
    
    # Vérifications
    param_repo = ParametreRepository(temp_db_manager)
    
    # 1. Clés standards
    p1 = param_repo.get_by_cle("taux_horaire_base")
    assert p1 is not None
    assert p1.valeur == "45.5"
    assert p1.type_valeur == "decimal"
    
    p2 = param_repo.get_by_cle("taux_marge_securite_materiaux")
    assert p2 is not None
    assert p2.valeur == "0.15"  # 15 % -> 0.15
    assert p2.type_valeur == "decimal"
    
    # 2. Slugification et suppression des accents
    p3 = param_repo.get_by_cle("parametre_inconnu")
    assert p3 is not None
    assert p3.valeur == "true" # "Oui" -> boolean true
    assert p3.type_valeur == "boolean"
    
    p4 = param_repo.get_by_cle("element_avec_accents")
    assert p4 is not None
    assert p4.valeur == "Texte simple" # Text simple is parsed as text, wait, my logic does str(val).lower() only for boolean? Wait, text is kept as is? Ah, I did str(value).strip(). Let's check: "Texte simple".
    
    # Check if collision was avoided (value should be "true" from the first insertion, not "autre")
    assert p3.valeur == "true"

def test_import_ouvrages(import_service, temp_db_manager, tmp_path, biblio_id):
    df_ouvrages = pd.DataFrame({
        "Code": ["0012", " ", None, "0015"], # Zéros initiaux et NULLs
        "Famille": ["Cloisons", "", None, "Cloisons"],
        "Type": ["Standard", "Standard", None, "Spécial"],
        "Configuration": ["72/48", "72/48", None, "98/48"],
        "Unité": ["m2", "m2", "m2", "m2"],
        "Fournitures HT/u": [10.5, 12, None, 15],
        "Déboursé sec": ["25,50", 25, 10, 30],
        "Épaisseur mm": [72, 72, None, 98],
        "Coef ST": [1.1, None, None, 1.2]
    })
    
    file_path = tmp_path / "test_cloisons2.xlsx"
    with pd.ExcelWriter(file_path) as writer:
        df_ouvrages.to_excel(writer, sheet_name="03_BASE_CLOISONS", index=False)
        
    import_service.import_fichier(str(file_path), biblio_id, mapping_override=cloisons_test_mapping())
    
    with temp_db_manager.get_connection() as conn:
        ouvrages = conn.execute("SELECT * FROM ouvrages_bibliotheque ORDER BY id").fetchall()
        
    assert len(ouvrages) == 3 # La ligne 3 (None, None, None) doit être rejetée
    
    # Ligne 1: 0012, complète
    o1 = ouvrages[0]
    assert o1["code"] == "0012" # Zéros initiaux conservés
    assert o1["designation"] == "Standard 72/48"
    assert o1["materiel_ht_import"] == 0 # Valeurs par défaut
    assert o1["mode_chiffrage"] == "importe"
    assert o1["actif"] == 1
    
    # Attributs techniques
    attr1 = json.loads(o1["attributs_techniques"])
    assert attr1["epaisseur_mm"] == 72
    assert "coef_st" not in attr1
    
    # Source JSON
    src1 = json.loads(o1["donnees_source_json"])
    assert src1["Code"] == "0012"
    
    # Ligne 2: code vide -> NULL, famille vide -> désignation réduite
    o2 = ouvrages[1]
    assert o2["code"] is None
    assert o2["designation"] == "Standard 72/48"
    
    # Doublon : le réimport ne doit ni réinsérer ni écraser l'ouvrage existant.
    date_creation_initiale = o1["date_creation"]
    
    df_ouvrages_update = pd.DataFrame({
        "Code": ["0012"],
        "Famille": ["Cloisons Modifiée"],
        "Type": ["Standard"],
        "Configuration": ["72/48"]
    })
    with pd.ExcelWriter(file_path) as writer:
        df_ouvrages_update.to_excel(writer, sheet_name="03_BASE_CLOISONS", index=False)
    
    summary_update = import_service.import_fichier(str(file_path), biblio_id, mapping_override=cloisons_test_mapping())
    
    with temp_db_manager.get_connection() as conn:
        o1_updated = conn.execute("SELECT * FROM ouvrages_bibliotheque WHERE code='0012'").fetchone()
        total_after = conn.execute("SELECT COUNT(*) FROM ouvrages_bibliotheque").fetchone()[0]
        
    assert summary_update.doublons == 1
    assert summary_update.ouvrages_importes == 0
    assert total_after == 3
    assert o1_updated["famille"] == "Cloisons"
    assert o1_updated["date_creation"] == date_creation_initiale
    assert o1_updated["date_modification"] == o1["date_modification"]


def cloisons_test_mapping():
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
                "heures_mo": None,
                "taux_horaire": None,
                "materiel": None,
                "transport": None,
                "sous_traitance": None,
            },
            "audit": {
                "debourse_sec": "Déboursé sec",
                "pv_st": None,
                "pv_eg": None,
                "coef_st": "Coef ST",
                "coef_eg": None,
            },
        },
    }


def standard_metier_mapping():
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
            "designation": {"mode": "direct", "colonne": "Désignation"},
            "components": {
                "fournitures": "Fournitures €",
                "heures_mo": "Heures MO",
                "taux_horaire": None,
                "materiel": "Matériel €",
                "transport": None,
                "sous_traitance": None,
            },
            "audit": {
                "debourse_sec": "Déboursé sec €",
                "pv_st": "Prix Sous-traitant €",
                "pv_eg": "Prix Entreprise Générale €",
                "coef_st": None,
                "coef_eg": None,
            },
        },
    }


def make_standard_file(path, base_sheet="03_BASE_PLOMBERIE", include_code=True, rendement_col="Rendement", pv_eg=307.5, designation="Mitigeur lavabo"):
    df_params = pd.DataFrame({
        "Paramètre": ["Taux horaire MO", "Coefficient vente Sous-traitant", "Coefficient vente Entreprise Générale", "Date version"],
        "Valeur": ["50", "1.2", "1.5", "28/06/2026"],
        "Unité": ["€", "", "", ""],
        "Commentaire": ["", "", "", ""],
    })
    data = {
        "Code": ["P-001"],
        "Famille": ["Plomberie"],
        "Sous-famille": ["Robinetterie"],
        "Désignation": [designation],
        "Support": ["Mur"],
        "Finition/Sujétion": ["Chromé"],
        "Unité": ["u"],
        "Fournitures €": [100],
        "Heures MO": [2],
        "Matériel €": [5],
        "Déboursé sec €": [205],
        "Prix Sous-traitant €": [246],
        "Prix Entreprise Générale €": [pv_eg],
        rendement_col: ["R1"],
        "Observations": ["Obs"],
    }
    if not include_code:
        data.pop("Code")
    df_ouvrages = pd.DataFrame(data)
    with pd.ExcelWriter(path) as writer:
        df_params.to_excel(writer, sheet_name="02_PARAMETRES", index=False)
        df_ouvrages.to_excel(writer, sheet_name=base_sheet, index=False)


def test_signature_inconnue_demande_validation(import_service, tmp_path, biblio_id):
    file_path = tmp_path / "plomberie.xlsx"
    make_standard_file(file_path)

    with pytest.raises(MappingImportRequired):
        import_service.import_fichier(str(file_path), biblio_id)


def test_signature_connue_mapping_applique_automatiquement(import_service, tmp_path, biblio_id):
    file_path = tmp_path / "plomberie.xlsx"
    make_standard_file(file_path)
    analysis = import_service.analyser_mapping(str(file_path))
    import_service.mapping_repo.save("Standard métiers", analysis.signature_colonnes, json.dumps(standard_metier_mapping(), ensure_ascii=False))

    summary = import_service.import_fichier(str(file_path), biblio_id)

    assert summary.mapping_reconnu is True
    assert summary.mapping_nom == "Standard métiers"
    assert summary.ouvrages_importes == 1


def test_meme_signature_reutilisee_sur_plusieurs_feuilles_metiers(import_service, tmp_path, biblio_id):
    plomberie = tmp_path / "plomberie.xlsx"
    couverture = tmp_path / "couverture.xlsx"
    make_standard_file(plomberie, "03_BASE_PLOMBERIE")
    make_standard_file(couverture, "03_BASE_COUVERTURE")
    analysis = import_service.analyser_mapping(str(plomberie))
    import_service.mapping_repo.save("Standard métiers", analysis.signature_colonnes, json.dumps(standard_metier_mapping(), ensure_ascii=False))

    assert import_service.analyser_mapping(str(couverture)).mapping is not None
    summary = import_service.import_fichier(str(couverture), biblio_id)

    assert summary.mapping_reconnu is True
    assert summary.ouvrages_importes == 1


def test_reconnaissance_tolerante_code_manquant(import_service, tmp_path, biblio_id):
    reference = tmp_path / "plomberie.xlsx"
    sans_code = tmp_path / "peinture_sans_code.xlsx"
    make_standard_file(reference)
    make_standard_file(sans_code, base_sheet="03_BASE_PEINTURE", include_code=False)
    analysis = import_service.analyser_mapping(str(reference))
    import_service.mapping_repo.save(
        "Modèle standard bibliothèques métiers",
        analysis.signature_colonnes,
        json.dumps(standard_metier_mapping(), ensure_ascii=False),
    )

    recognized = import_service.analyser_mapping(str(sans_code))
    summary = import_service.import_fichier(str(sans_code), biblio_id)

    assert recognized.mapping_nom == "Modèle standard bibliothèques métiers"
    assert recognized.mapping_score >= 90
    assert summary.mapping_reconnu is True
    with temp_db_for_repo(import_service).get_connection() as conn:
        ouvrage = conn.execute("SELECT code FROM ouvrages_bibliotheque ORDER BY id DESC LIMIT 1").fetchone()
    assert ouvrage["code"] is None


def test_colonne_non_essentielle_renommee_ne_bloque_pas(import_service, tmp_path, biblio_id):
    reference = tmp_path / "plomberie.xlsx"
    renamed = tmp_path / "couverture.xlsx"
    make_standard_file(reference)
    make_standard_file(renamed, base_sheet="03_BASE_COUVERTURE", rendement_col="Rendement unité/h")
    analysis = import_service.analyser_mapping(str(reference))
    import_service.mapping_repo.save(
        "Modèle standard bibliothèques métiers",
        analysis.signature_colonnes,
        json.dumps(standard_metier_mapping(), ensure_ascii=False),
    )

    recognized = import_service.analyser_mapping(str(renamed))

    assert recognized.mapping_nom == "Modèle standard bibliothèques métiers"
    assert recognized.mapping_score >= 90


def test_fichier_different_declenche_validation(import_service, tmp_path, biblio_id):
    reference = tmp_path / "plomberie.xlsx"
    different = tmp_path / "different.xlsx"
    make_standard_file(reference)
    with pd.ExcelWriter(different) as writer:
        pd.DataFrame({"A": [1], "B": [2], "C": [3]}).to_excel(writer, sheet_name="03_BASE_AUTRE", index=False)
    analysis = import_service.analyser_mapping(str(reference))
    import_service.mapping_repo.save(
        "Modèle standard bibliothèques métiers",
        analysis.signature_colonnes,
        json.dumps(standard_metier_mapping(), ensure_ascii=False),
    )

    with pytest.raises(MappingImportRequired):
        import_service.import_fichier(str(different), biblio_id)


def test_mapping_cloisons_isole_du_modele_standard(import_service, tmp_path):
    standard = tmp_path / "standard.xlsx"
    make_standard_file(standard)

    analysis = import_service.analyser_mapping(str(standard))

    assert analysis.mapping_nom != "Cloisons (modèle historique)"


def test_creation_nouvelle_version_mapping(import_service, tmp_path):
    reference = tmp_path / "standard.xlsx"
    changed = tmp_path / "changed.xlsx"
    make_standard_file(reference)
    make_standard_file(changed)
    analysis = import_service.analyser_mapping(str(reference))
    parent_id = import_service.mapping_repo.save(
        "Modèle standard bibliothèques métiers",
        analysis.signature_colonnes,
        json.dumps(standard_metier_mapping(), ensure_ascii=False),
    )
    parent = import_service.mapping_repo.get_by_id(parent_id)
    changed_analysis = import_service.analyser_mapping(str(changed))
    new_mapping = standard_metier_mapping()
    new_id = import_service.mapping_repo.create_version(
        parent,
        changed_analysis.signature_colonnes + "::v2",
        json.dumps(new_mapping, ensure_ascii=False),
    )

    child = import_service.mapping_repo.get_by_id(new_id)

    assert child.version == parent.version + 1
    assert child.mapping_parent_id == parent.id
    assert json.loads(child.mapping_json)["ouvrages"]["designation"]["colonne"] == "Désignation"


def test_bibliotheque_garde_mapping_utilise(import_service, temp_db_manager, tmp_path, biblio_id):
    file_path = tmp_path / "standard.xlsx"
    make_standard_file(file_path)
    analysis = import_service.analyser_mapping(str(file_path))
    mapping_id = import_service.mapping_repo.save(
        "Modèle standard bibliothèques métiers",
        analysis.signature_colonnes,
        json.dumps(standard_metier_mapping(), ensure_ascii=False),
    )

    import_service.import_fichier(str(file_path), biblio_id)

    with temp_db_manager.get_connection() as conn:
        biblio = conn.execute("SELECT mapping_import_id FROM bibliotheques WHERE id = ?", (biblio_id,)).fetchone()
    assert biblio["mapping_import_id"] == mapping_id


def test_calcul_generique_debourse_sec(import_service, tmp_path, temp_db_manager, biblio_id):
    file_path = tmp_path / "standard.xlsx"
    make_standard_file(file_path)

    import_service.import_fichier(str(file_path), biblio_id, mapping_override=standard_metier_mapping())

    with temp_db_manager.get_connection() as conn:
        ouvrage = conn.execute("SELECT * FROM ouvrages_bibliotheque WHERE code = 'P-001'").fetchone()
    assert ouvrage["debourse_sec_import"] == 205
    assert ouvrage["mo_ht_import"] == 100
    assert ouvrage["pv_st_ht_import"] == 246
    assert ouvrage["pv_eg_ht_import"] == 307.5


def test_reimport_doublon_meme_bibliotheque_ignore_sans_ecraser(import_service, tmp_path, temp_db_manager, biblio_id):
    file_path = tmp_path / "standard.xlsx"
    make_standard_file(file_path)
    first_summary = import_service.import_fichier(str(file_path), biblio_id, mapping_override=standard_metier_mapping())

    changed_file = tmp_path / "standard_modifie.xlsx"
    make_standard_file(changed_file, designation="Désignation changée")
    second_summary = import_service.import_fichier(str(changed_file), biblio_id, mapping_override=standard_metier_mapping())

    assert first_summary.ouvrages_importes == 1
    assert second_summary.ouvrages_importes == 0
    assert second_summary.doublons == 1
    with temp_db_manager.get_connection() as conn:
        rows = conn.execute("SELECT code, designation FROM ouvrages_bibliotheque").fetchall()
    assert len(rows) == 1
    assert rows[0]["designation"] == "Mitigeur lavabo"


def test_reutilisation_bibliotheque_par_nom_de_fichier(temp_db_manager):
    repo = BibliothequeRepository(temp_db_manager)
    service = BibliothequeService(repo)
    repo.create(Bibliotheque(id=None, nom="Plomberie", description="", corps_metier="", actif=True, date_creation="", date_modification=""))

    existing = service.obtenir_par_nom("plomberie")

    assert existing is not None
    assert existing.nom == "Plomberie"


def temp_db_for_repo(import_service):
    return import_service.db


def test_date_version_importee_en_texte_iso(import_service, temp_db_manager, tmp_path, biblio_id):
    file_path = tmp_path / "params_date.xlsx"
    df_params = pd.DataFrame({
        "Paramètre": ["Date version"],
        "Valeur": ["28/06/2026"],
        "Unité": [""],
        "Commentaire": [""],
    })
    with pd.ExcelWriter(file_path) as writer:
        df_params.to_excel(writer, sheet_name="02_PARAMETRES", index=False)

    import_service.import_fichier(str(file_path), biblio_id)

    param = ParametreRepository(temp_db_manager).get_by_cle("date_version")
    assert param.valeur == "2026-06-28"
    assert param.type_valeur == "text"


def test_avertissement_ecart_audit_non_bloquant(import_service, tmp_path, biblio_id):
    file_path = tmp_path / "audit.xlsx"
    make_standard_file(file_path, pv_eg=1000)
    summary = import_service.import_fichier(str(file_path), biblio_id, mapping_override=standard_metier_mapping())

    assert summary.ouvrages_importes == 1
    assert any("PV EG fichier" in warning for warning in summary.avertissements)


def test_colonnes_non_mappees_en_attributs(import_service, temp_db_manager, tmp_path, biblio_id):
    file_path = tmp_path / "attrs.xlsx"
    make_standard_file(file_path)
    import_service.import_fichier(str(file_path), biblio_id, mapping_override=standard_metier_mapping())

    with temp_db_manager.get_connection() as conn:
        ouvrage = conn.execute("SELECT attributs_techniques FROM ouvrages_bibliotheque WHERE code = 'P-001'").fetchone()
    attrs = json.loads(ouvrage["attributs_techniques"])
    assert attrs["sous_famille"] == "Robinetterie"
    assert attrs["support"] == "Mur"
    assert "debourse_sec" not in attrs


def test_migration_mapping_cloisons_existante(import_service):
    assert any(mapping.nom == "Cloisons (modèle historique)" for mapping in import_service.mapping_repo.list_all())


def test_rejet_colonne_assignee_deux_fois(import_service):
    mapping = standard_metier_mapping()
    mapping["ouvrages"]["famille"] = "Désignation"
    with pytest.raises(ValueError):
        import_service.valider_mapping(mapping)
