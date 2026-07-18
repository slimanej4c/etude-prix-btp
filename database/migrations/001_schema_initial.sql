-- Migration 001 : Schéma initial

CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version INTEGER NOT NULL,
    description TEXT NOT NULL,
    date_application DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parametres_generaux (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cle TEXT NOT NULL UNIQUE,
    valeur TEXT NOT NULL,
    type_valeur TEXT NOT NULL CHECK(type_valeur IN ('decimal', 'integer', 'boolean', 'text')),
    unite TEXT,
    description TEXT,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bibliotheques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    description TEXT,
    corps_metier TEXT,
    actif BOOLEAN DEFAULT 1,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ressources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bibliotheque_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    designation TEXT NOT NULL,
    type_ressource TEXT NOT NULL CHECK(type_ressource IN ('main_oeuvre', 'materiau', 'materiel', 'transport', 'sous_traitance', 'autre')),
    unite TEXT NOT NULL,
    prix_unitaire_ht DECIMAL NOT NULL,
    attributs_techniques TEXT,
    actif BOOLEAN DEFAULT 1,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bibliotheque_id) REFERENCES bibliotheques(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ouvrages_bibliotheque (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bibliotheque_id INTEGER NOT NULL,
    code TEXT NOT NULL,
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
    actif BOOLEAN DEFAULT 1,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bibliotheque_id) REFERENCES bibliotheques(id) ON DELETE CASCADE,
    UNIQUE(bibliotheque_id, code)
);

CREATE TABLE IF NOT EXISTS compositions_ouvrages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ouvrage_id INTEGER NOT NULL,
    ressource_id INTEGER NOT NULL,
    quantite DECIMAL NOT NULL,
    coefficient_perte DECIMAL NOT NULL DEFAULT 1.0,
    ordre_affichage INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (ouvrage_id) REFERENCES ouvrages_bibliotheque(id) ON DELETE CASCADE,
    FOREIGN KEY (ressource_id) REFERENCES ressources(id) ON DELETE CASCADE,
    UNIQUE(ouvrage_id, ressource_id)
);

CREATE TABLE IF NOT EXISTS projets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    client TEXT,
    reference TEXT,
    statut TEXT,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parametres_projet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id INTEGER NOT NULL,
    cle TEXT NOT NULL,
    valeur TEXT NOT NULL,
    type_valeur TEXT NOT NULL,
    FOREIGN KEY (projet_id) REFERENCES projets(id) ON DELETE CASCADE,
    UNIQUE(projet_id, cle)
);

CREATE TABLE IF NOT EXISTS lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    libelle TEXT NOT NULL,
    ordre_affichage INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (projet_id) REFERENCES projets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sous_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    libelle TEXT NOT NULL,
    ordre_affichage INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (lot_id) REFERENCES lots(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ouvrages_projet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sous_lot_id INTEGER NOT NULL,
    ouvrage_bibliotheque_id INTEGER,
    code TEXT NOT NULL,
    designation TEXT NOT NULL,
    unite TEXT NOT NULL,
    quantite DECIMAL NOT NULL,
    
    -- Déboursés
    ds_mo DECIMAL NOT NULL DEFAULT 0,
    ds_mat DECIMAL NOT NULL DEFAULT 0,
    ds_materiel DECIMAL NOT NULL DEFAULT 0,
    ds_transport DECIMAL NOT NULL DEFAULT 0,
    ds_st DECIMAL NOT NULL DEFAULT 0,
    ds_total DECIMAL NOT NULL DEFAULT 0,
    
    -- Prix
    pv_unitaire DECIMAL NOT NULL DEFAULT 0,
    pv_total DECIMAL NOT NULL DEFAULT 0,
    
    ordre_affichage INTEGER NOT NULL DEFAULT 0,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sous_lot_id) REFERENCES sous_lots(id) ON DELETE CASCADE,
    FOREIGN KEY (ouvrage_bibliotheque_id) REFERENCES ouvrages_bibliotheque(id) ON DELETE SET NULL
);

-- Index pour optimiser les performances
CREATE INDEX IF NOT EXISTS idx_ressources_biblio ON ressources(bibliotheque_id);
CREATE INDEX IF NOT EXISTS idx_ouvrages_biblio ON ouvrages_bibliotheque(bibliotheque_id);
CREATE INDEX IF NOT EXISTS idx_compositions_ouvrage ON compositions_ouvrages(ouvrage_id);
CREATE INDEX IF NOT EXISTS idx_lots_projet ON lots(projet_id);
CREATE INDEX IF NOT EXISTS idx_sous_lots_lot ON sous_lots(lot_id);
CREATE INDEX IF NOT EXISTS idx_ouvrages_projet_sous_lot ON ouvrages_projet(sous_lot_id);
