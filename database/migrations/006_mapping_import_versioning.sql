-- Migration 006 : versionning des mappings d'import et traçabilité bibliothèque

ALTER TABLE mappings_import ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE mappings_import ADD COLUMN mapping_parent_id INTEGER NULL REFERENCES mappings_import(id) ON DELETE SET NULL;

ALTER TABLE bibliotheques ADD COLUMN mapping_import_id INTEGER NULL REFERENCES mappings_import(id) ON DELETE SET NULL;
