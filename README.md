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

## Page Mapping et chiffrage

La page **Mapping et chiffrage** est l'écran principal de travail après l'import DPGF. Elle permet de relier chaque ligne chiffrable du DPGF à un ouvrage de bibliothèque, de saisir ou corriger les prix, puis de sauvegarder des versions du projet.

### Tableau principal

Le tableau affiche une ligne par ouvrage DPGF réel, avec des regroupements par lot et sous-lot. Les colonnes principales sont :

* `Code` : code/article de la ligne DPGF.
* `Désignation` : libellé de la ligne DPGF.
* `Unité` et `Quantité` : informations importées du DPGF.
* `MO`, `Matériaux`, `Matériel`, `Transport`, `Sous-traitance` : composants éditables du déboursé sec.
* `DS total`, `PV unitaire`, `PV total` : valeurs calculées automatiquement.
* `Lien bibliothèque` : état du mapping de la ligne.
* `Propositions` : liste des correspondances trouvées dans la bibliothèque.
* `Actions` : accès aux actions ligne par ligne.

Les colonnes sont redimensionnables, y compris `Désignation`. Les lignes de lot et sous-lot affichent les totaux et peuvent être repliées/dépliées.

### Statuts de mapping

Chaque ligne peut avoir un des statuts suivants :

* `Validée` : une proposition bibliothèque est choisie. La ligne est prise en compte dans le tableau de bord.
* `Proposée` : une ou plusieurs propositions existent, mais aucune n'est validée. La ligne reste en attente et apparaît en orange.
* `Aucune` : aucune proposition n'est retenue. La ligne apparaît en rouge et n'est pas comptée dans les totaux du tableau de bord.

Quand une proposition est choisie, l'application demande confirmation. Après validation, les valeurs de la bibliothèque sont copiées dans la ligne de chiffrage. Si l'utilisateur choisit `Aucune proposition` sur une ligne validée, une confirmation est demandée et les montants liés à cette ligne sont retirés du tableau de bord.

### Saisie du chiffrage

Les colonnes `MO`, `Matériaux`, `Matériel`, `Transport` et `Sous-traitance` sont éditables directement dans le tableau, comme dans un tableur.

La saisie refuse les valeurs négatives et les valeurs non numériques. Après modification, les champs calculés sont mis à jour :

* `DS total` = somme des cinq composants.
* `PV unitaire` et `PV total` sont recalculés selon le coefficient de vente.
* Les totaux de lot, sous-lot et projet sont recalculés immédiatement.

Une modification manuelle après copie bibliothèque marque la ligne comme surchargée manuellement dans les données du projet.

### Tableau de bord

Le tableau de bord en haut de l'écran se met à jour en temps réel pendant le chiffrage. Il affiche :

* Déboursé sec total du projet.
* Prix de vente total du projet.
* Nombre de lignes chiffrées / nombre total de lignes.
* Marge globale en euros et en pourcentage.
* Nombre de correspondances validées.
* Nombre de lignes avec propositions à choisir.
* Nombre de saisies manuelles.
* Nombre de lignes non traitées.

Il affiche aussi la répartition du déboursé sec par nature :

* Main d'oeuvre.
* Matériaux.
* Matériel.
* Transport.
* Sous-traitance.

Les totaux du tableau de bord concernent uniquement les lignes validées ou les lignes saisies manuellement complètes. Les lignes `Proposée` ou `Aucune` ne sont pas additionnées dans les montants tant qu'elles ne sont pas traitées.

### Boutons et actions

* `Original` : revient à l'état courant du projet, c'est-à-dire le travail vivant dans `ouvrages_projet`.
* `Sauvegarder en version` : crée une version figée du travail affiché.
* `Versions sauvegardées` : permet d'afficher une version existante dans le tableau.
* `Voir les versions` : ouvre la page de comparaison des versions.
* `Recherche auto` : recherche automatiquement des correspondances texte avec la bibliothèque.
* `Recherche auto avec IA` : lance le matching IA avec `sentence-transformers`.
* `Copier depuis la bibliothèque` : copie les valeurs bibliothèque sur les lignes sélectionnées qui ont une correspondance validée.
* `Détail ligne` : ouvre le détail d'une ligne, avec son historique et les informations associées.
* `Valider` : valide la proposition sélectionnée sur la ligne.
* `Manuel` : ouvre la recherche manuelle dans le catalogue.
* `Créer` : crée rapidement un nouvel ouvrage bibliothèque depuis la ligne DPGF, puis valide automatiquement la correspondance.

### Versions

Les versions sont liées au projet et enregistrées en base de données. Une version fige :

* les montants de chiffrage de chaque ligne ;
* le statut mapping de chaque ligne ;
* la proposition validée ;
* l'ouvrage bibliothèque lié.

Cela permet de conserver des états séparés. Par exemple, si `Version 1` est sauvegardée avec 4 propositions validées, elle restera à 4 validées même si l'utilisateur continue ensuite le travail et sauvegarde `Version 2` avec 10 propositions validées.

Quand une version sauvegardée est sélectionnée dans la page Mapping et chiffrage, le tableau affiche l'état de cette version. Revenir sur `Original` affiche de nouveau l'état courant du projet.

Les modifications faites pendant l'affichage d'une version modifient cette version affichée. Elles ne changent pas automatiquement l'état original courant.

### Comparaison des versions

La page de comparaison est accessible depuis `Voir les versions`. Elle permet de comparer :

* une version figée avec une autre version figée ;
* une version figée avec la `Version actuelle`.

Elle affiche les écarts par composante, les totaux, les graphiques de répartition et les lignes les plus impactantes.

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
