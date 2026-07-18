-- Migration 009 : historique des modifications de chiffrage courant

CREATE TABLE IF NOT EXISTS historique_ouvrages_projet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ouvrage_projet_id INTEGER NOT NULL,
    ds_mo DECIMAL NOT NULL DEFAULT 0,
    ds_mat DECIMAL NOT NULL DEFAULT 0,
    ds_materiel DECIMAL NOT NULL DEFAULT 0,
    ds_transport DECIMAL NOT NULL DEFAULT 0,
    ds_st DECIMAL NOT NULL DEFAULT 0,
    ds_total DECIMAL NOT NULL DEFAULT 0,
    pv_unitaire DECIMAL NOT NULL DEFAULT 0,
    pv_total DECIMAL NOT NULL DEFAULT 0,
    origine TEXT NOT NULL DEFAULT 'edition',
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ouvrage_projet_id) REFERENCES ouvrages_projet(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_historique_ouvrages_projet_ouvrage
ON historique_ouvrages_projet(ouvrage_projet_id, date_creation);
