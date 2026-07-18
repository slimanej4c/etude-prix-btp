# Logiciel d'Études de Prix BTP

Logiciel desktop Windows d'études de prix BTP selon la méthode du déboursé sec.

## Installation

1. Créer un environnement virtuel (recommandé) :
   ```bash
   python -m venv venv
   ```
2. Activer l'environnement virtuel :
   - Sous Windows : `venv\Scripts\activate`
   - Sous macOS/Linux : `source venv/bin/activate`
3. Installer les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

## Lancement de l'application

```bash
python main.py
```

## Lancement des tests

```bash
pytest tests/
```

## Structure du projet

* `config/` : Configuration globale de l'application.
* `data/` : Dossier contenant la base de données SQLite.
* `database/` : Gestion de la base de données et des migrations.
* `models/` : Dataclasses (Entités métiers).
* `repositories/` : Classes d'accès aux données.
* `services/` : Logique métier.
* `ui/` : Interface utilisateur graphique PySide6.
* `tests/` : Tests unitaires.
# etude-prix-btp
