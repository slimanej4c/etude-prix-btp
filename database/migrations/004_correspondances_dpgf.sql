-- Migration 004 : correspondances entre lignes DPGF et ouvrages de bibliothèque

CREATE TABLE IF NOT EXISTS correspondances_dpgf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ouvrage_projet_id INTEGER NOT NULL,
    ouvrage_bibliotheque_id INTEGER NOT NULL,
    score REAL NOT NULL,
    origine TEXT NOT NULL CHECK(origine IN ('automatique', 'manuelle')),
    statut TEXT NOT NULL CHECK(statut IN ('proposee', 'validee')),
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ouvrage_projet_id) REFERENCES sections_projet(id) ON DELETE CASCADE,
    FOREIGN KEY (ouvrage_bibliotheque_id) REFERENCES ouvrages_bibliotheque(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_correspondance_validee_unique
ON correspondances_dpgf(ouvrage_projet_id)
WHERE statut = 'validee';

CREATE UNIQUE INDEX IF NOT EXISTS idx_correspondance_paire_unique
ON correspondances_dpgf(ouvrage_projet_id, ouvrage_bibliotheque_id);

INSERT INTO parametres_generaux (cle, valeur, type_valeur, unite, description)
SELECT 'score_minimum_matching', '60', 'decimal', 'score', 'Score minimum pour proposer une correspondance DPGF-bibliothèque'
WHERE NOT EXISTS (
    SELECT 1 FROM parametres_generaux WHERE cle = 'score_minimum_matching'
);
