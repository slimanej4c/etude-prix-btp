-- Migration 003 : structure DPGF dynamique pour les projets

CREATE TABLE IF NOT EXISTS sections_projet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id INTEGER NOT NULL,
    parent_id INTEGER,
    type_ligne TEXT NOT NULL CHECK(type_ligne IN ('lot', 'conteneur', 'ouvrage', 'pour_memoire', 'information')),
    numero_article TEXT,
    numero_article_original TEXT,
    libelle TEXT NOT NULL,
    unite TEXT,
    quantite DECIMAL,
    prix_unitaire DECIMAL,
    total DECIMAL,
    pour_memoire BOOLEAN DEFAULT 0,
    ordre_affichage INTEGER NOT NULL DEFAULT 0,
    profondeur INTEGER NOT NULL DEFAULT 1,
    fichier_source TEXT,
    feuille_source TEXT,
    ligne_excel_source INTEGER NOT NULL,
    formule_total TEXT,
    donnees_source_json TEXT,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (projet_id) REFERENCES projets(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES sections_projet(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sections_projet ON sections_projet(projet_id);
CREATE INDEX IF NOT EXISTS idx_sections_parent ON sections_projet(parent_id);
CREATE INDEX IF NOT EXISTS idx_sections_ordre ON sections_projet(projet_id, ordre_affichage);
