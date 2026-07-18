-- Migration 008 : liaison entre lignes DPGF et chiffrage courant

ALTER TABLE ouvrages_projet ADD COLUMN section_projet_id INTEGER REFERENCES sections_projet(id) ON DELETE CASCADE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvrages_projet_section
ON ouvrages_projet(section_projet_id)
WHERE section_projet_id IS NOT NULL;
