from decimal import Decimal
from pathlib import Path

import pytest

from database.db_manager import DatabaseManager
from repositories.version_projet_repository import VersionProjetRepository
from services.version_projet_service import SOURCE_ACTUEL, VersionProjetService


@pytest.fixture
def db_manager(tmp_path):
    return DatabaseManager(
        db_path=tmp_path / "versions.db",
        migrations_dir=Path(__file__).parent.parent / "database" / "migrations",
    )


@pytest.fixture
def service(db_manager):
    return VersionProjetService(VersionProjetRepository(db_manager))


@pytest.fixture
def project_data(db_manager):
    with db_manager.get_connection() as conn:
        projet_id = conn.execute(
            "INSERT INTO projets (nom, client, reference, statut) VALUES ('Projet', 'Client', 'REF', 'En cours')"
        ).lastrowid
        lot_a = conn.execute(
            "INSERT INTO lots (projet_id, code, libelle, ordre_affichage) VALUES (?, 'L1', 'Lot A', 1)",
            (projet_id,),
        ).lastrowid
        lot_b = conn.execute(
            "INSERT INTO lots (projet_id, code, libelle, ordre_affichage) VALUES (?, 'L2', 'Lot B', 2)",
            (projet_id,),
        ).lastrowid
        sous_lot_a = conn.execute(
            "INSERT INTO sous_lots (lot_id, code, libelle, ordre_affichage) VALUES (?, 'SL1', 'Sous-lot A', 1)",
            (lot_a,),
        ).lastrowid
        sous_lot_b = conn.execute(
            "INSERT INTO sous_lots (lot_id, code, libelle, ordre_affichage) VALUES (?, 'SL2', 'Sous-lot B', 1)",
            (lot_b,),
        ).lastrowid
        ouvrage_1 = _insert_ouvrage(conn, sous_lot_a, "A1", "Ouvrage A1", 100, 200, 30, 10, 50, 390, 780)
        ouvrage_2 = _insert_ouvrage(conn, sous_lot_a, "A2", "Ouvrage A2", 50, 70, 10, 5, 15, 150, 300)
        ouvrage_3 = _insert_ouvrage(conn, sous_lot_b, "B1", "Ouvrage B1", 20, 30, 5, 0, 10, 65, 130)
        conn.commit()
    return {
        "projet_id": projet_id,
        "lot_a": lot_a,
        "lot_b": lot_b,
        "ouvrages": [ouvrage_1, ouvrage_2, ouvrage_3],
    }


def test_creation_version_snapshot_toutes_les_lignes(project_data, service):
    version_id = service.creer_version(project_data["projet_id"], "Avant négociation")

    versions = service.lister_versions(project_data["projet_id"])
    assert versions[0].id == version_id
    assert versions[0].nombre_lignes == 3
    assert versions[0].est_version_courante is True

    comparison = service.comparer(project_data["projet_id"], str(version_id), SOURCE_ACTUEL)
    totals = {row["cle"]: row["reference"] for row in comparison["lignes"]}
    assert totals["ds_mo"] == Decimal("170")
    assert totals["ds_total"] == Decimal("605")
    assert totals["pv_total"] == Decimal("1210")


def test_une_seule_version_courante_possible(project_data, service):
    first_id = service.creer_version(project_data["projet_id"], "V1")
    second_id = service.creer_version(project_data["projet_id"], "V2")

    versions = service.lister_versions(project_data["projet_id"])
    current = [version for version in versions if version.est_version_courante]
    assert [version.id for version in current] == [second_id]
    assert first_id != second_id


def test_contrainte_unique_version_courante_base(project_data, db_manager):
    with db_manager.get_connection() as conn:
        conn.execute(
            "INSERT INTO versions_projet (projet_id, nom, est_version_courante) VALUES (?, 'V1', 1)",
            (project_data["projet_id"],),
        )
        conn.commit()
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO versions_projet (projet_id, nom, est_version_courante) VALUES (?, 'V2', 1)",
                (project_data["projet_id"],),
            )
            conn.commit()


def test_comparaison_deux_versions_figees(project_data, db_manager, service):
    v1 = service.creer_version(project_data["projet_id"], "Avant")
    _update_ouvrage(db_manager, project_data["ouvrages"][0], ds_mat=Decimal("220"), ds_total=Decimal("410"), pv_total=Decimal("820"))
    v2 = service.creer_version(project_data["projet_id"], "Après")

    comparison = service.comparer(project_data["projet_id"], str(v1), str(v2))
    rows = {row["cle"]: row for row in comparison["lignes"]}
    assert rows["ds_mat"]["ecart_montant"] == Decimal("20")
    assert rows["ds_total"]["ecart_montant"] == Decimal("20")
    assert rows["pv_total"]["ecart_formate"] == "+3,31 % / +40,00 €"


def test_comparaison_version_et_etat_actuel_live(project_data, db_manager, service):
    version_id = service.creer_version(project_data["projet_id"], "Avant")
    _update_ouvrage(db_manager, project_data["ouvrages"][1], ds_st=Decimal("45"), ds_total=Decimal("180"), pv_total=Decimal("360"))

    comparison = service.comparer(project_data["projet_id"], str(version_id), SOURCE_ACTUEL)
    rows = {row["cle"]: row for row in comparison["lignes"]}
    assert rows["ds_st"]["ecart_montant"] == Decimal("30")
    assert rows["ds_total"]["ecart_montant"] == Decimal("30")
    assert rows["pv_total"]["ecart_montant"] == Decimal("60")


def test_filtre_lot_recalcule_aggregation(project_data, db_manager, service):
    version_id = service.creer_version(project_data["projet_id"], "Avant")
    _update_ouvrage(db_manager, project_data["ouvrages"][2], ds_total=Decimal("95"), pv_total=Decimal("190"))

    comparison = service.comparer(project_data["projet_id"], str(version_id), SOURCE_ACTUEL, lot_id=project_data["lot_b"])
    rows = {row["cle"]: row for row in comparison["lignes"]}
    assert rows["ds_total"]["reference"] == Decimal("65")
    assert rows["ds_total"]["comparee"] == Decimal("95")
    assert rows["ds_total"]["ecart_montant"] == Decimal("30")


def test_lignes_plus_impactees_triees_par_ecart_absolu(project_data, db_manager, service):
    version_id = service.creer_version(project_data["projet_id"], "Avant")
    _update_ouvrage(db_manager, project_data["ouvrages"][0], ds_total=Decimal("490"), pv_total=Decimal("980"))
    _update_ouvrage(db_manager, project_data["ouvrages"][1], ds_total=Decimal("155"), pv_total=Decimal("310"))

    comparison = service.comparer(project_data["projet_id"], str(version_id), SOURCE_ACTUEL)
    impacted = comparison["top_impacted"]
    assert impacted[0]["code"] == "A1"
    assert impacted[0]["ecart_montant"] == Decimal("100")
    assert impacted[1]["code"] == "A2"


def test_suppression_version_sans_impact_projet(project_data, db_manager, service):
    version_id = service.creer_version(project_data["projet_id"], "À supprimer")
    service.supprimer_version(version_id)

    assert service.lister_versions(project_data["projet_id"]) == []
    with db_manager.get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM ouvrages_projet").fetchone()[0]
        assert count == 3


def test_duplication_version_applique_valeurs_source_sur_actuel(project_data, db_manager, service):
    v1 = service.creer_version(project_data["projet_id"], "Version 1")
    _update_ouvrage(
        db_manager,
        project_data["ouvrages"][0],
        ds_mo=Decimal("500"),
        ds_mat=Decimal("600"),
        ds_total=Decimal("1100"),
        pv_unitaire=Decimal("2200"),
        pv_total=Decimal("2200"),
    )
    service.creer_version(project_data["projet_id"], "Version 2")

    duplicate_id = service.dupliquer_version(v1, "Copie V1")

    versions = service.lister_versions(project_data["projet_id"])
    current = [version for version in versions if version.est_version_courante]
    assert [version.id for version in current] == [duplicate_id]
    comparison = service.comparer(project_data["projet_id"], str(v1), SOURCE_ACTUEL)
    assert all(row["ecart_montant"] == 0 for row in comparison["lignes"])
    duplicate_comparison = service.comparer(project_data["projet_id"], str(v1), str(duplicate_id))
    assert all(row["ecart_montant"] == 0 for row in duplicate_comparison["lignes"])


def test_detection_modifications_non_sauvegardees(project_data, db_manager, service):
    service.creer_version(project_data["projet_id"], "Version enregistrée")

    assert service.a_modifications_non_sauvegardees(project_data["projet_id"]) is False

    _update_ouvrage(db_manager, project_data["ouvrages"][1], ds_st=Decimal("45"), ds_total=Decimal("180"), pv_total=Decimal("360"))

    assert service.a_modifications_non_sauvegardees(project_data["projet_id"]) is True


def test_actuel_reste_modifiable_apres_duplication(project_data, db_manager, service):
    v1 = service.creer_version(project_data["projet_id"], "Base")
    _update_ouvrage(db_manager, project_data["ouvrages"][2], ds_total=Decimal("95"), pv_total=Decimal("190"))
    service.dupliquer_version(v1, "Travail depuis base")

    _update_ouvrage(db_manager, project_data["ouvrages"][2], ds_total=Decimal("120"), pv_total=Decimal("240"))

    comparison = service.comparer(project_data["projet_id"], str(v1), SOURCE_ACTUEL)
    rows = {row["cle"]: row for row in comparison["lignes"]}
    assert rows["ds_total"]["ecart_montant"] == Decimal("55")
    assert rows["pv_total"]["ecart_montant"] == Decimal("110")


def test_format_ecart_client(project_data, db_manager, service):
    version_id = service.creer_version(project_data["projet_id"], "Avant")
    _update_ouvrage(db_manager, project_data["ouvrages"][0], ds_total=Decimal("360"), pv_total=Decimal("720"))

    comparison = service.comparer(project_data["projet_id"], str(version_id), SOURCE_ACTUEL)
    rows = {row["cle"]: row for row in comparison["lignes"]}
    assert rows["ds_total"]["ecart_formate"] == "-4,96 % / -30,00 €"


def _insert_ouvrage(conn, sous_lot_id, code, designation, ds_mo, ds_mat, ds_materiel, ds_transport, ds_st, ds_total, pv_total):
    return conn.execute(
        """
        INSERT INTO ouvrages_projet (
            sous_lot_id, code, designation, unite, quantite, ds_mo, ds_mat,
            ds_materiel, ds_transport, ds_st, ds_total, pv_unitaire, pv_total, ordre_affichage
        )
        VALUES (?, ?, ?, 'u', 1, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            sous_lot_id,
            code,
            designation,
            Decimal(str(ds_mo)),
            Decimal(str(ds_mat)),
            Decimal(str(ds_materiel)),
            Decimal(str(ds_transport)),
            Decimal(str(ds_st)),
            Decimal(str(ds_total)),
            Decimal(str(pv_total)),
            Decimal(str(pv_total)),
        ),
    ).lastrowid


def _update_ouvrage(db_manager, ouvrage_id, **values):
    assignments = ", ".join(f"{key} = ?" for key in values)
    params = [Decimal(str(value)) for value in values.values()]
    params.append(ouvrage_id)
    with db_manager.get_connection() as conn:
        conn.execute(f"UPDATE ouvrages_projet SET {assignments} WHERE id = ?", params)
        conn.commit()
