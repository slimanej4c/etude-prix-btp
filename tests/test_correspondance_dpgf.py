from decimal import Decimal
from pathlib import Path
import time

import pytest

from database.db_manager import DatabaseManager
from models.entites import Bibliotheque, OuvrageBibliotheque, Projet, SectionProjet
from repositories.bibliotheque_repository import BibliothequeRepository
from repositories.correspondance_dpgf_repository import CorrespondanceDpgfRepository
from repositories.ouvrage_bibliotheque_repository import OuvrageBibliothequeRepository
from repositories.parametre_repository import ParametreRepository
from repositories.projet_repository import ProjetRepository
from repositories.section_projet_repository import SectionProjetRepository
from services.correspondance_service import CorrespondanceService
from services.parametre_service import ParametreService


@pytest.fixture
def db(tmp_path):
    return DatabaseManager(tmp_path / "matching.db", Path(__file__).parent.parent / "database" / "migrations")


@pytest.fixture
def service(db):
    return CorrespondanceService(
        db,
        CorrespondanceDpgfRepository(db),
        SectionProjetRepository(db),
        ParametreService(ParametreRepository(db)),
    )


@pytest.fixture
def sample_data(db):
    projet_id = ProjetRepository(db).create(Projet(None, "Projet", "", "", "Nouveau", "", ""))
    section_repo = SectionProjetRepository(db)
    lot_id = section_repo.create(SectionProjet(
        None, projet_id, None, "lot", None, None, "Lot Cloisons", None, None, None, None,
        False, 0, 1, "dpgf.xlsx", "Lot Cloisons", 6, None, "{}", "", ""
    ))
    ouvrage_id = section_repo.create(SectionProjet(
        None, projet_id, lot_id, "ouvrage", "1.1", "1.1", "Cloison distributive standard 72/48",
        "m²", None, None, None, False, 1, 2, "dpgf.xlsx", "Lot Cloisons", 7, "=D7*E7", "{}", "", ""
    ))
    autre_ouvrage_id = section_repo.create(SectionProjet(
        None, projet_id, lot_id, "ouvrage", "1.2", "1.2", "Porte bois",
        "u", None, None, None, False, 2, 2, "dpgf.xlsx", "Lot Cloisons", 8, "=D8*E8", "{}", "", ""
    ))
    biblio_repo = BibliothequeRepository(db)
    cloison_biblio = biblio_repo.create(Bibliotheque(None, "Cloisons", "", "Cloisons", True, "", ""))
    menuiserie_biblio = biblio_repo.create(Bibliotheque(None, "Menuiseries", "", "Menuiseries", True, "", ""))
    ouvrage_repo = OuvrageBibliothequeRepository(db)
    cloison_ouvrage = ouvrage_repo.create(make_ouvrage(cloison_biblio, "CL-001", "Cloison distributive standard 72/48", "Cloisons distributives", "m2"))
    porte_ouvrage = ouvrage_repo.create(make_ouvrage(menuiserie_biblio, "P-001", "Porte bois intérieur", "Menuiseries", "u"))
    return {
        "projet_id": projet_id,
        "ouvrage_id": ouvrage_id,
        "autre_ouvrage_id": autre_ouvrage_id,
        "cloison_biblio": cloison_biblio,
        "menuiserie_biblio": menuiserie_biblio,
        "cloison_ouvrage": cloison_ouvrage,
        "porte_ouvrage": porte_ouvrage,
        "ouvrage_repo": ouvrage_repo,
        "section_repo": section_repo,
        "corr_repo": CorrespondanceDpgfRepository(db),
    }


def make_ouvrage(bibliotheque_id, code, designation, famille, unite):
    return OuvrageBibliotheque(
        id=None,
        bibliotheque_id=bibliotheque_id,
        code=code,
        designation=designation,
        famille=famille,
        unite=unite,
        mode_chiffrage="importe",
        fournitures_ht_import=Decimal("10"),
        mo_heures_import=Decimal("1"),
        taux_horaire_import=Decimal("40"),
        mo_ht_import=Decimal("40"),
        materiel_ht_import=Decimal("0"),
        transport_ht_import=Decimal("0"),
        sous_traitance_ht_import=Decimal("0"),
        debourse_sec_import=Decimal("50"),
        pv_st_ht_import=Decimal("60"),
        pv_eg_ht_import=Decimal("75"),
        debourse_sec_calcule=None,
        pv_st_ht_calcule=None,
        pv_eg_ht_calcule=None,
        source_calcul="importe",
        date_dernier_calcul=None,
        attributs_techniques='{"feu": "EI30"}',
        donnees_source_json="{}",
        actif=True,
        date_creation="",
        date_modification="",
    )


def set_score_min(db, value):
    ParametreService(ParametreRepository(db)).creer_ou_modifier_parametre(
        "score_minimum_matching", str(value), "decimal", "score", "Score min"
    )


def test_recherche_avec_resultat(service, sample_data):
    results = service.rechercher(sample_data["ouvrage_id"], enregistrer=True)
    assert results
    assert results[0].ouvrage_bibliotheque_id == sample_data["cloison_ouvrage"]
    assert service.statut_ouvrage(sample_data["ouvrage_id"]) == "Proposée"


def test_recherche_sans_resultat_si_seuil_trop_haut(db, service, sample_data):
    set_score_min(db, 101)
    results = service.rechercher(sample_data["ouvrage_id"], enregistrer=True)
    assert results == []
    assert service.statut_ouvrage(sample_data["ouvrage_id"]) == "Aucune"


def test_score_inferieur_seuil_non_propose(db, service, sample_data):
    set_score_min(db, 95)
    results = service.rechercher(sample_data["autre_ouvrage_id"], enregistrer=True)
    assert results == []
    assert service.statut_ouvrage(sample_data["autre_ouvrage_id"]) == "Aucune"


def test_restriction_corps_metier_et_elargissement(db, service, sample_data):
    set_score_min(db, 30)
    restricted = service.rechercher(sample_data["autre_ouvrage_id"], elargir_toutes_bibliotheques=False, enregistrer=False)
    expanded = service.rechercher(sample_data["autre_ouvrage_id"], elargir_toutes_bibliotheques=True, enregistrer=False)
    assert all(result.corps_metier == "Cloisons" for result in restricted)
    assert any(result.ouvrage_bibliotheque_id == sample_data["porte_ouvrage"] for result in expanded)


def test_normalisation_unites(service):
    assert service.normaliser_unite("m²") == "m2"
    assert service.normaliser_unite("M2") == "m2"
    assert service.normaliser_unite("mètre linéaire") == "ml"
    assert service.normaliser_unite("unités") == "u"
    assert service.normaliser_unite("ensemble") == "ens"


def test_stopwords_supprimes_sans_modifier_termes_techniques(service):
    normalized = service._search_text("Cloison de distribution avec BA13 72/48 EI60 35 dB")
    assert "de" not in normalized.split("_")
    assert "avec" not in normalized.split("_")
    assert "cloison" in normalized
    assert "72_48" in normalized
    assert "ba13" in normalized
    assert "ei60" in normalized
    assert "35" in normalized
    assert "db" in normalized


def test_cloison_72_48_mieux_classee_que_cloison_120_90(db, service, sample_data):
    set_score_min(db, 1)
    sample_data["ouvrage_repo"].create(
        make_ouvrage(sample_data["cloison_biblio"], "CL-120", "Cloison distributive standard 120/90", "Cloisons distributives", "m2")
    )

    results = service.rechercher(sample_data["ouvrage_id"], enregistrer=False)

    assert results[0].ouvrage_bibliotheque_id == sample_data["cloison_ouvrage"]
    scores = {result.code: result.score for result in results}
    assert scores["CL-001"] > scores["CL-120"]


def test_cloison_acoustique_favorise_candidat_acoustique(db, service, sample_data):
    set_score_min(db, 1)
    section_id = sample_data["section_repo"].create(SectionProjet(
        None, sample_data["projet_id"], None, "ouvrage", "2.1", "2.1",
        "Cloison acoustique 72/48 BA13 50 dB", "m²", None, None, None,
        False, 3, 1, "dpgf.xlsx", "Lot Cloisons", 12, "=D12*E12", "{}", "", ""
    ))
    acoustic_id = sample_data["ouvrage_repo"].create(
        make_ouvrage(sample_data["cloison_biblio"], "CL-A50", "Cloison acoustique 72/48 BA13 50 dB", "Cloisons acoustiques", "m2")
    )
    sample_data["ouvrage_repo"].create(
        make_ouvrage(sample_data["cloison_biblio"], "CL-S", "Cloison distributive standard 72/48 BA13", "Cloisons distributives", "m2")
    )

    results = service.rechercher(section_id, enregistrer=False)

    assert results[0].ouvrage_bibliotheque_id == acoustic_id


def test_etancheite_ne_propose_pas_bibliotheque_cloisons(db, service, sample_data):
    set_score_min(db, 1)
    lot_id = sample_data["section_repo"].create(SectionProjet(
        None, sample_data["projet_id"], None, "lot", None, None, "Lot Etanchéité", None,
        None, None, None, False, 4, 1, "dpgf.xlsx", "Lot Etanchéité", 6, None, "{}", "", ""
    ))
    section_id = sample_data["section_repo"].create(SectionProjet(
        None, sample_data["projet_id"], lot_id, "ouvrage", "1.1", "1.1",
        "Complexe etancheite bicouche autoprotegee", "m2", None, None, None,
        False, 5, 2, "dpgf.xlsx", "Lot Etanchéité", 7, "=D7*E7", "{}", "", ""
    ))

    results = service.rechercher(section_id, enregistrer=False)

    assert results == []


def test_peinture_ne_propose_pas_bibliotheque_cloisons(db, service, sample_data):
    set_score_min(db, 1)
    lot_id = sample_data["section_repo"].create(SectionProjet(
        None, sample_data["projet_id"], None, "lot", None, None, "Lot Peinture", None,
        None, None, None, False, 4, 1, "dpgf.xlsx", "Lot Peinture", 6, None, "{}", "", ""
    ))
    section_id = sample_data["section_repo"].create(SectionProjet(
        None, sample_data["projet_id"], lot_id, "ouvrage", "1.1", "1.1",
        "Peinture acrylique deux couches", "m2", None, None, None,
        False, 5, 2, "dpgf.xlsx", "Lot Peinture", 7, "=D7*E7", "{}", "", ""
    ))

    results = service.rechercher(section_id, enregistrer=False)

    assert results == []


def test_association_automatique_et_manuelle(service, sample_data):
    service.rechercher(sample_data["ouvrage_id"], enregistrer=True)
    corr = service.correspondances_pour_ouvrage(sample_data["ouvrage_id"])[0]
    service.associer_resultat(corr["id"])
    assert service.statut_ouvrage(sample_data["ouvrage_id"]) == "Validée"

    service.associer_manuellement(sample_data["autre_ouvrage_id"], sample_data["porte_ouvrage"])
    manual = service.correspondances_pour_ouvrage(sample_data["autre_ouvrage_id"])[0]
    assert manual["origine"] == "manuelle"
    assert manual["statut"] == "validee"


def test_une_seule_validation_par_ouvrage_base(service, sample_data):
    service.rechercher(sample_data["ouvrage_id"], elargir_toutes_bibliotheques=True, enregistrer=True)
    service.associer_manuellement(sample_data["ouvrage_id"], sample_data["cloison_ouvrage"])
    service.associer_manuellement(sample_data["ouvrage_id"], sample_data["porte_ouvrage"])
    validated = [c for c in service.correspondances_pour_ouvrage(sample_data["ouvrage_id"]) if c["statut"] == "validee"]
    assert len(validated) == 1
    assert validated[0]["ouvrage_bibliotheque_id"] == sample_data["porte_ouvrage"]


def test_upsert_relance_recherche_pas_de_doublon(service, sample_data):
    service.rechercher(sample_data["ouvrage_id"], enregistrer=True)
    service.rechercher(sample_data["ouvrage_id"], enregistrer=True)
    correspondances = service.correspondances_pour_ouvrage(sample_data["ouvrage_id"])
    pairs = {(c["ouvrage_projet_id"], c["ouvrage_bibliotheque_id"]) for c in correspondances}
    assert len(correspondances) == len(pairs)


def test_suppression_association(service, sample_data):
    service.rechercher(sample_data["ouvrage_id"], enregistrer=True)
    corr = service.correspondances_pour_ouvrage(sample_data["ouvrage_id"])[0]
    service.supprimer_association(corr["id"])
    assert service.correspondances_pour_ouvrage(sample_data["ouvrage_id"]) == []


def test_recherche_ia_ajoute_propositions_sans_validation(db, service, sample_data):
    class FakeModel:
        def encode(self, texts):
            vectors = []
            for text in texts:
                normalized = text.lower()
                if "cloison" in normalized:
                    vectors.append([1.0, 0.0, 0.0])
                elif "porte" in normalized:
                    vectors.append([0.0, 1.0, 0.0])
                else:
                    vectors.append([0.0, 0.0, 1.0])
            return vectors

    set_score_min(db, 1)

    result = service.lancer_recherche_ia_projet(
        sample_data["projet_id"],
        rechercher_toutes_bibliotheques=True,
        model=FakeModel(),
    )

    assert result.propositions > 0
    correspondances = service.correspondances_pour_ouvrage(sample_data["ouvrage_id"])
    assert correspondances
    assert any(corr["origine"] == "ia" for corr in correspondances)
    assert all(corr["statut"] == "proposee" for corr in correspondances)
    assert service.statut_ouvrage(sample_data["ouvrage_id"]) == "Proposée"


def test_refus_suppression_ouvrage_bibliotheque_reference(service, sample_data):
    service.associer_manuellement(sample_data["ouvrage_id"], sample_data["cloison_ouvrage"])
    with pytest.raises(Exception):
        sample_data["ouvrage_repo"].delete(sample_data["cloison_ouvrage"])


def test_cascade_suppression_section(service, sample_data):
    service.associer_manuellement(sample_data["ouvrage_id"], sample_data["cloison_ouvrage"])
    with sample_data["section_repo"].db.get_connection() as conn:
        conn.execute("DELETE FROM sections_projet WHERE id = ?", (sample_data["ouvrage_id"],))
        conn.commit()
    assert service.correspondances_pour_ouvrage(sample_data["ouvrage_id"]) == []


def test_persistance_apres_redemarrage(db, service, sample_data):
    service.associer_manuellement(sample_data["ouvrage_id"], sample_data["cloison_ouvrage"])
    new_service = CorrespondanceService(
        db,
        CorrespondanceDpgfRepository(db),
        SectionProjetRepository(db),
        ParametreService(ParametreRepository(db)),
    )
    assert new_service.statut_ouvrage(sample_data["ouvrage_id"]) == "Validée"


def test_sections_a_matcher_exclut_conteneurs_vides_et_validees(service, sample_data):
    repo = sample_data["section_repo"]
    container_id = repo.create(SectionProjet(
        None, sample_data["projet_id"], None, "ouvrage", "3", "3", "Conteneur avec enfant",
        "u", None, None, None, False, 10, 1, "dpgf.xlsx", "Lot Cloisons", 20, "=SUM(D21:D22)", "{}", "", ""
    ))
    repo.create(SectionProjet(
        None, sample_data["projet_id"], container_id, "ouvrage", "3.1", "3.1", "Enfant réel",
        "u", None, None, None, False, 11, 2, "dpgf.xlsx", "Lot Cloisons", 21, "=D21*E21", "{}", "", ""
    ))
    repo.create(SectionProjet(
        None, sample_data["projet_id"], None, "ouvrage", "4", "4", "   ",
        "u", None, None, None, False, 12, 1, "dpgf.xlsx", "Lot Cloisons", 22, "=D22*E22", "{}", "", ""
    ))
    service.associer_manuellement(sample_data["ouvrage_id"], sample_data["cloison_ouvrage"])

    ids = {section.id for section in service.sections_a_matcher(sample_data["projet_id"])}

    assert sample_data["ouvrage_id"] not in ids
    assert container_id not in ids
    assert sample_data["autre_ouvrage_id"] in ids


def test_prefiltrage_mots_cles_reduit_candidats_sans_perte(db, service, sample_data):
    biblio_id = sample_data["cloison_biblio"]
    for index in range(80):
        sample_data["ouvrage_repo"].create(
            make_ouvrage(biblio_id, f"X-{index}", f"mot{index} special", "Famille", "m2")
        )
    section_id = sample_data["section_repo"].create(SectionProjet(
        None, sample_data["projet_id"], None, "ouvrage", "5", "5", "mot42",
        "m2", None, None, None, False, 13, 1, "dpgf.xlsx", "Lot Cloisons", 23, "=D23*E23", "{}", "", ""
    ))
    section = sample_data["section_repo"].get_by_id(section_id)
    candidates = service._catalogue_candidates()
    filtered = service._prefilter_candidates_by_keywords(section, candidates)

    assert len(filtered) < len(candidates)
    results = service.rechercher(section_id, elargir_toutes_bibliotheques=True, enregistrer=False)
    assert results[0].code == "X-42"


def test_rapprochement_progression_et_annulation_rollback(db, service, sample_data):
    set_score_min(db, 1)
    progresses = []

    def progress_callback(progress):
        progresses.append((progress.traites, progress.total))

    result = service.lancer_rapprochement_projet(
        sample_data["projet_id"],
        elargir_toutes_bibliotheques=True,
        batch_size=200,
        progress_callback=progress_callback,
        should_cancel=lambda: bool(progresses),
    )

    assert result.annule is True
    assert progresses
    assert service.correspondances_pour_ouvrage(sample_data["ouvrage_id"]) == []


def test_rapprochement_volumineux_prefiltre_rapide(db, service):
    projet_id = ProjetRepository(db).create(Projet(None, "Volume", "", "", "Nouveau", "", ""))
    section_repo = SectionProjetRepository(db)
    lot_id = section_repo.create(SectionProjet(
        None, projet_id, None, "lot", None, None, "Lot Cloisons", None, None, None, None,
        False, 0, 1, "dpgf.xlsx", "Lot Cloisons", 1, None, "{}", "", ""
    ))
    biblio_id = BibliothequeRepository(db).create(Bibliotheque(None, "Cloisons volume", "", "Cloisons", True, "", ""))
    ouvrage_repo = OuvrageBibliothequeRepository(db)
    for index in range(2000):
        key = f"mot{index % 200}"
        ouvrage_repo.create(make_ouvrage(biblio_id, f"V-{index}", key, "Famille", "u"))
    for index in range(1000):
        key = f"mot{index % 200}"
        section_repo.create(SectionProjet(
            None, projet_id, lot_id, "ouvrage", str(index), str(index), key,
            "u", None, None, None, False, index + 1, 2, "dpgf.xlsx", "Lot Cloisons", index + 2, "=D*E", "{}", "", ""
        ))

    progresses = []
    start = time.perf_counter()
    result = service.lancer_rapprochement_projet(
        projet_id,
        batch_size=200,
        progress_callback=lambda progress: progresses.append(progress.traites),
    )
    duration = time.perf_counter() - start

    assert result.traites == 1000
    assert progresses[-1] == 1000
    assert result.candidats_scores < result.candidats_apres_metier
    assert duration < 10
