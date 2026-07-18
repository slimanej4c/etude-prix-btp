-- Migration 002 : Modification de la table ouvrages_bibliotheque
-- Rendre le champ 'code' facultatif (suppression de NOT NULL)
-- Ajouter le champ 'donnees_source_json'

PRAGMA foreign_keys=off;

-- Création de la nouvelle table avec le schéma mis à jour
CREATE TABLE IF NOT EXISTS new_ouvrages_bibliotheque (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bibliotheque_id INTEGER NOT NULL,
    code TEXT, -- NOT NULL supprimé
    designation TEXT NOT NULL,
    famille TEXT,
    unite TEXT NOT NULL,
    mode_chiffrage TEXT NOT NULL CHECK(mode_chiffrage IN ('importe', 'composition', 'manuel')),
    
    -- Prix importés
    fournitures_ht_import DECIMAL,
    mo_heures_import DECIMAL,
    taux_horaire_import DECIMAL,
    mo_ht_import DECIMAL,
    materiel_ht_import DECIMAL,
    transport_ht_import DECIMAL,
    sous_traitance_ht_import DECIMAL,
    debourse_sec_import DECIMAL,
    pv_st_ht_import DECIMAL,
    pv_eg_ht_import DECIMAL,
    
    -- Prix calculés
    debourse_sec_calcule DECIMAL,
    pv_st_ht_calcule DECIMAL,
    pv_eg_ht_calcule DECIMAL,
    
    source_calcul TEXT CHECK(source_calcul IN ('importe', 'composition', 'manuel')),
    date_dernier_calcul DATETIME,
    attributs_techniques TEXT,
    donnees_source_json TEXT, -- Nouveau champ
    actif BOOLEAN DEFAULT 1,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bibliotheque_id) REFERENCES bibliotheques(id) ON DELETE CASCADE,
    UNIQUE(bibliotheque_id, code)
);

-- Copie des données
INSERT INTO new_ouvrages_bibliotheque (
    id, bibliotheque_id, code, designation, famille, unite, mode_chiffrage,
    fournitures_ht_import, mo_heures_import, taux_horaire_import, mo_ht_import,
    materiel_ht_import, transport_ht_import, sous_traitance_ht_import, debourse_sec_import,
    pv_st_ht_import, pv_eg_ht_import, debourse_sec_calcule, pv_st_ht_calcule, pv_eg_ht_calcule,
    source_calcul, date_dernier_calcul, attributs_techniques, actif, date_creation, date_modification
)
SELECT 
    id, bibliotheque_id, code, designation, famille, unite, mode_chiffrage,
    fournitures_ht_import, mo_heures_import, taux_horaire_import, mo_ht_import,
    materiel_ht_import, transport_ht_import, sous_traitance_ht_import, debourse_sec_import,
    pv_st_ht_import, pv_eg_ht_import, debourse_sec_calcule, pv_st_ht_calcule, pv_eg_ht_calcule,
    source_calcul, date_dernier_calcul, attributs_techniques, actif, date_creation, date_modification
FROM ouvrages_bibliotheque;

-- Suppression de l'ancienne table
DROP TABLE ouvrages_bibliotheque;

-- Renommage
ALTER TABLE new_ouvrages_bibliotheque RENAME TO ouvrages_bibliotheque;

-- Recréation de l'index
CREATE INDEX IF NOT EXISTS idx_ouvrages_biblio ON ouvrages_bibliotheque(bibliotheque_id);

PRAGMA foreign_keys=on;
