PARAMETRES_STANDARDS = {
    "Taux horaire MO": "taux_horaire_base",
    "Coefficient vente Sous-traitant": "coefficient_vente_st",
    "Coefficient vente Entreprise Générale": "coefficient_vente_eg",
    "Marge sécurité matériaux": "taux_marge_securite_materiaux",
    "TVA standard": "taux_tva",
    "Majoration petite surface": "majoration_petite_surface",
    "Majoration chantier occupé": "majoration_chantier_occupe",
    "Majoration accès difficile": "majoration_acces_difficile",
    "Majoration grande hauteur": "majoration_grande_hauteur"
}

MAPPINGS_BIBLIOTHEQUES = {
    "cloisons": {
        "feuille_parametres": {
            "noms_possibles": ["01_PARAMETRES", "PARAMETRES", "parametres"],
            "colonnes": {
                "Paramètre": "parametre",
                "Valeur": "valeur",
                "Unité": "unite",
                "Commentaire": "commentaire"
            }
        },
        "feuille_ouvrages": {
            "noms_possibles": ["03_BASE_CLOISONS", "BASE_CLOISONS", "ouvrages"],
            "colonnes_directes": {
                "Code": "code",
                "Famille": "famille",
                "Unité": "unite",
                "Fournitures HT/u": "fournitures_ht_import",
                "MO h/u": "mo_heures_import",
                "Taux horaire": "taux_horaire_import",
                "MO HT/u": "mo_ht_import",
                "Déboursé sec": "debourse_sec_import",
                "PV ST HT": "pv_st_ht_import",
                "PV EG HT": "pv_eg_ht_import"
            },
            "attributs_techniques": {
                "Système": "systeme",
                "Type": "type",
                "Configuration": "configuration",
                "Épaisseur mm": "epaisseur_mm",
                "Ossature": "ossature",
                "Parement face A": "parement_face_a",
                "Parement face B": "parement_face_b",
                "Isolant": "isolant",
                "Feu": "feu",
                "Acoustique dB": "acoustique_db",
                "Hauteur max m": "hauteur_max_m",
                "Observations": "observations",
                "Coef ST": "coef_st_source",
                "Coef EG": "coef_eg_source"
            },
            "designation_strategy": "famille_type_configuration"
        }
    }
}
