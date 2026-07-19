-- Migration 011 : figer l'etat mapping dans chaque version de projet

ALTER TABLE versions_projet_lignes
ADD COLUMN correspondance_dpgf_id INTEGER;

ALTER TABLE versions_projet_lignes
ADD COLUMN ouvrage_bibliotheque_id INTEGER;

ALTER TABLE versions_projet_lignes
ADD COLUMN statut_mapping TEXT NOT NULL DEFAULT 'Aucune'
CHECK(statut_mapping IN ('Aucune', 'Proposée', 'Validée'));

UPDATE versions_projet_lignes
SET
    correspondance_dpgf_id = (
        SELECT c.id
        FROM correspondances_dpgf c
        WHERE c.ouvrage_projet_id = versions_projet_lignes.ouvrage_projet_id
          AND c.statut = 'validee'
        ORDER BY c.id
        LIMIT 1
    ),
    ouvrage_bibliotheque_id = (
        SELECT c.ouvrage_bibliotheque_id
        FROM correspondances_dpgf c
        WHERE c.ouvrage_projet_id = versions_projet_lignes.ouvrage_projet_id
          AND c.statut = 'validee'
        ORDER BY c.id
        LIMIT 1
    ),
    statut_mapping = CASE
        WHEN EXISTS (
            SELECT 1 FROM correspondances_dpgf c
            WHERE c.ouvrage_projet_id = versions_projet_lignes.ouvrage_projet_id
              AND c.statut = 'validee'
        ) THEN 'Validée'
        WHEN EXISTS (
            SELECT 1 FROM correspondances_dpgf c
            WHERE c.ouvrage_projet_id = versions_projet_lignes.ouvrage_projet_id
              AND c.statut = 'proposee'
        ) THEN 'Proposée'
        ELSE 'Aucune'
    END;
