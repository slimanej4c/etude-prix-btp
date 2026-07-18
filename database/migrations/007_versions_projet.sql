-- Migration 007 : Versions explicites de projet

CREATE TABLE IF NOT EXISTS versions_projet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id INTEGER NOT NULL,
    nom TEXT NOT NULL,
    est_version_courante BOOLEAN NOT NULL DEFAULT 0,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (projet_id) REFERENCES projets(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_versions_projet_courante_unique
ON versions_projet(projet_id)
WHERE est_version_courante = 1;

CREATE INDEX IF NOT EXISTS idx_versions_projet_projet
ON versions_projet(projet_id);

CREATE TABLE IF NOT EXISTS versions_projet_lignes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    ouvrage_projet_id INTEGER NOT NULL,
    ds_mo DECIMAL NOT NULL DEFAULT 0,
    ds_mat DECIMAL NOT NULL DEFAULT 0,
    ds_materiel DECIMAL NOT NULL DEFAULT 0,
    ds_transport DECIMAL NOT NULL DEFAULT 0,
    ds_st DECIMAL NOT NULL DEFAULT 0,
    ds_total DECIMAL NOT NULL DEFAULT 0,
    pv_unitaire DECIMAL NOT NULL DEFAULT 0,
    pv_total DECIMAL NOT NULL DEFAULT 0,
    FOREIGN KEY (version_id) REFERENCES versions_projet(id) ON DELETE CASCADE,
    FOREIGN KEY (ouvrage_projet_id) REFERENCES ouvrages_projet(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_versions_projet_lignes_version
ON versions_projet_lignes(version_id);

CREATE INDEX IF NOT EXISTS idx_versions_projet_lignes_ouvrage
ON versions_projet_lignes(ouvrage_projet_id);
