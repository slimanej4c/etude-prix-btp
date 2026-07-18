-- Migration 010 : autoriser les propositions issues de la recherche IA

PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS correspondances_dpgf_new;

CREATE TABLE correspondances_dpgf_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ouvrage_projet_id INTEGER NOT NULL,
    ouvrage_bibliotheque_id INTEGER NOT NULL,
    score REAL NOT NULL,
    origine TEXT NOT NULL CHECK(origine IN ('automatique', 'manuelle', 'ia')),
    statut TEXT NOT NULL CHECK(statut IN ('proposee', 'validee')),
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ouvrage_projet_id) REFERENCES sections_projet(id) ON DELETE CASCADE,
    FOREIGN KEY (ouvrage_bibliotheque_id) REFERENCES ouvrages_bibliotheque(id) ON DELETE RESTRICT
);

INSERT INTO correspondances_dpgf_new (
    id, ouvrage_projet_id, ouvrage_bibliotheque_id, score, origine,
    statut, date_creation, date_modification
)
SELECT
    id, ouvrage_projet_id, ouvrage_bibliotheque_id, score, origine,
    statut, date_creation, date_modification
FROM correspondances_dpgf;

DROP TABLE correspondances_dpgf;

ALTER TABLE correspondances_dpgf_new RENAME TO correspondances_dpgf;

CREATE UNIQUE INDEX IF NOT EXISTS idx_correspondance_validee_unique
ON correspondances_dpgf(ouvrage_projet_id)
WHERE statut = 'validee';

CREATE UNIQUE INDEX IF NOT EXISTS idx_correspondance_paire_unique
ON correspondances_dpgf(ouvrage_projet_id, ouvrage_bibliotheque_id);

PRAGMA foreign_keys = ON;

INSERT INTO parametres_generaux (cle, valeur, type_valeur, unite, description)
SELECT 'poids_matching_ia_semantique', '0.65', 'decimal', 'ratio', 'Poids du score sémantique IA dans le matching hybride'
WHERE NOT EXISTS (
    SELECT 1 FROM parametres_generaux WHERE cle = 'poids_matching_ia_semantique'
);

INSERT INTO parametres_generaux (cle, valeur, type_valeur, unite, description)
SELECT 'poids_matching_ia_textuel', '0.35', 'decimal', 'ratio', 'Poids du score textuel RapidFuzz dans le matching hybride IA'
WHERE NOT EXISTS (
    SELECT 1 FROM parametres_generaux WHERE cle = 'poids_matching_ia_textuel'
);
