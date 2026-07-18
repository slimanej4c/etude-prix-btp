-- Migration 005 : mappings dynamiques d'import Excel

CREATE TABLE IF NOT EXISTS mappings_import (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    signature_colonnes TEXT NOT NULL UNIQUE,
    mapping_json TEXT NOT NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_derniere_utilisation DATETIME
);
