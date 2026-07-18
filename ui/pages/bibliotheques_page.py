import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTableWidget, QTableWidgetItem, QPushButton, 
    QHeaderView, QFileDialog, QMessageBox, QInputDialog,
    QDialog, QListWidget, QComboBox, QFormLayout, QGroupBox,
    QRadioButton, QDialogButtonBox, QLineEdit, QScrollArea
)
from PySide6.QtCore import Qt

from database.db_manager import DatabaseManager
from repositories.bibliotheque_repository import BibliothequeRepository
from repositories.ouvrage_bibliotheque_repository import OuvrageBibliothequeRepository
from repositories.parametre_repository import ParametreRepository
from services.bibliotheque_service import BibliothequeService
from services.import_bibliotheque_service import ImportBibliothequeService
from services.parametre_service import ParametreService
from services.ouvrage_service import OuvrageService
from ui.pages.ouvrages_dialog import OuvragesDialog


class MappingImportDialog(QDialog):
    TARGET_FIELDS = [
        ("code", "Code"),
        ("famille", "Famille"),
        ("unite", "Unité"),
        ("fournitures", "Fournitures"),
        ("heures_mo", "Heures MO"),
        ("materiel", "Matériel"),
        ("transport", "Transport"),
        ("sous_traitance", "Sous-traitance"),
    ]

    def __init__(self, import_service: ImportBibliothequeService, analysis, parent=None):
        super().__init__(parent)
        self.import_service = import_service
        self.analysis = analysis
        self.mapping = analysis.mapping or import_service.proposer_mapping(analysis)
        self.setWindowTitle("Validation du mapping d'import Excel")
        self.resize(1100, 680)
        self.setMinimumSize(900, 560)
        self.combos = {}
        self.concat_combos = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Associer les colonnes Excel aux champs utiles")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self.name_input = QLineEdit(self.analysis.mapping_nom or "Modèle standard bibliothèques métiers V1")
        layout.addWidget(QLabel("Nom du mapping"))
        layout.addWidget(self.name_input)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(8)

        body = QHBoxLayout()
        body.addWidget(self._build_columns_group(), 1)
        body.addWidget(self._build_mapping_group(), 1)
        scroll_layout.addLayout(body)

        self.unmapped_label = QLabel()
        self.unmapped_label.setWordWrap(True)
        scroll_layout.addWidget(self.unmapped_label)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)
        self._refresh_unmapped_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Confirmer le mapping")
        buttons.button(QDialogButtonBox.Cancel).setText("Annuler")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_columns_group(self):
        group = QGroupBox("Colonnes Excel détectées")
        layout = QVBoxLayout(group)
        list_widget = QListWidget()
        for column in self.analysis.ouvrage_columns:
            preview = " | ".join(self.analysis.previews.get(column, []))
            label = column if not preview else f"{column}    → {preview}"
            list_widget.addItem(label)
        layout.addWidget(list_widget)
        if self.analysis.result_columns:
            result_label = QLabel(
                "Colonnes de résultat mises de côté pour audit : "
                + ", ".join(self.analysis.result_columns)
            )
            result_label.setWordWrap(True)
            layout.addWidget(result_label)
        return group

    def _build_mapping_group(self):
        group = QGroupBox("Champs cibles SQLite")
        layout = QVBoxLayout(group)

        designation_group = QGroupBox("Désignation")
        designation_layout = QVBoxLayout(designation_group)
        self.direct_radio = QRadioButton("Une colonne contient déjà la désignation")
        self.concat_radio = QRadioButton("Construire depuis 2 à 4 colonnes")
        designation = self.mapping.get("ouvrages", {}).get("designation", {})
        self.direct_radio.setChecked(designation.get("mode") == "direct")
        self.concat_radio.setChecked(designation.get("mode") != "direct")
        designation_layout.addWidget(self.direct_radio)
        self.designation_direct_combo = self._column_combo()
        self.designation_direct_combo.setCurrentText(designation.get("colonne") or "Aucune")
        designation_layout.addWidget(self.designation_direct_combo)
        designation_layout.addWidget(self.concat_radio)
        concat_values = designation.get("colonnes", [])
        for index in range(4):
            combo = self._column_combo()
            combo.setCurrentText(concat_values[index] if index < len(concat_values) else "Aucune")
            self.concat_combos.append(combo)
            designation_layout.addWidget(combo)
        layout.addWidget(designation_group)

        form = QFormLayout()
        ouvrages = self.mapping.get("ouvrages", {})
        components = ouvrages.get("components", {})
        for key, label in self.TARGET_FIELDS:
            combo = self._column_combo()
            if key in components:
                combo.setCurrentText(components.get(key) or "Aucune")
            else:
                combo.setCurrentText(ouvrages.get(key) or "Aucune")
            combo.currentTextChanged.connect(self._refresh_unmapped_preview)
            self.combos[key] = combo
            form.addRow(label, combo)
        layout.addLayout(form)
        return group

    def _column_combo(self):
        combo = QComboBox()
        combo.addItem("Aucune")
        for column in self.analysis.ouvrage_columns:
            if column not in self.analysis.result_columns:
                combo.addItem(column)
        combo.currentTextChanged.connect(self._refresh_unmapped_preview)
        return combo

    def _value(self, combo):
        value = combo.currentText()
        return None if value == "Aucune" else value

    def build_mapping(self):
        designation = {"mode": "direct", "colonne": self._value(self.designation_direct_combo)}
        if self.concat_radio.isChecked():
            designation = {
                "mode": "concat",
                "colonnes": [self._value(combo) for combo in self.concat_combos if self._value(combo)],
            }
        return {
            "parametres": {
                "parametre": self.import_service._find_column(self.analysis.param_columns, "Paramètre"),
                "valeur": self.import_service._find_column(self.analysis.param_columns, "Valeur"),
                "unite": self.import_service._find_column(self.analysis.param_columns, "Unité"),
                "commentaire": self.import_service._find_column(self.analysis.param_columns, "Commentaire"),
            },
            "ouvrages": {
                "code": self._value(self.combos["code"]),
                "famille": self._value(self.combos["famille"]),
                "unite": self._value(self.combos["unite"]),
                "designation": designation,
                "components": {
                    "fournitures": self._value(self.combos["fournitures"]),
                    "heures_mo": self._value(self.combos["heures_mo"]),
                    "taux_horaire": None,
                    "materiel": self._value(self.combos["materiel"]),
                    "transport": self._value(self.combos["transport"]),
                    "sous_traitance": self._value(self.combos["sous_traitance"]),
                },
                "audit": {
                    "debourse_sec": self.import_service._find_column(self.analysis.ouvrage_columns, "Déboursé sec", "Déboursé sec €"),
                    "pv_st": self.import_service._find_column(self.analysis.ouvrage_columns, "PV ST HT", "Prix Sous-traitant €"),
                    "pv_eg": self.import_service._find_column(self.analysis.ouvrage_columns, "PV EG HT", "Prix Entreprise Générale €"),
                    "coef_st": self.import_service._find_column(self.analysis.ouvrage_columns, "Coef ST"),
                    "coef_eg": self.import_service._find_column(self.analysis.ouvrage_columns, "Coef EG"),
                },
            },
        }

    def _refresh_unmapped_preview(self):
        if not hasattr(self, "unmapped_label"):
            return
        mapping = self.build_mapping()
        assigned = self.import_service._assigned_columns(mapping["ouvrages"])
        unmapped = [
            column for column in self.analysis.ouvrage_columns
            if column not in assigned and column not in self.analysis.result_columns
        ]
        self.unmapped_label.setText(
            "Colonnes non mappées → attributs techniques : "
            + (", ".join(unmapped) if unmapped else "aucune")
        )

    def accept(self):
        mapping = self.build_mapping()
        try:
            self.import_service.valider_mapping(mapping)
        except Exception as exc:
            QMessageBox.warning(self, "Mapping invalide", str(exc))
            return
        components = mapping.get("ouvrages", {}).get("components", {})
        if not any(components.get(key) for key in ("fournitures", "heures_mo", "materiel", "transport", "sous_traitance")):
            QMessageBox.warning(
                self,
                "Aucun composant",
                "Aucun composant du déboursé sec n'est associé. L'import continuera avec des prix à 0.",
            )
        self.mapping = mapping
        super().accept()

class BibliothequesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialisation des services métier
        self.db_manager = DatabaseManager()
        self.biblio_repo = BibliothequeRepository(self.db_manager)
        self.biblio_service = BibliothequeService(self.biblio_repo)
        
        self.param_repo = ParametreRepository(self.db_manager)
        self.param_service = ParametreService(self.param_repo)
        
        self.ouvrage_repo = OuvrageBibliothequeRepository(self.db_manager)
        self.import_service = ImportBibliothequeService(self.param_service, self.ouvrage_repo)
        self.ouvrage_service = OuvrageService(self.ouvrage_repo)
        
        self._setup_ui()
        self.load_data()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # En-tête
        header_layout = QHBoxLayout()
        titre = QLabel("Gestion des Bibliothèques")
        titre.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        self.btn_voir = QPushButton("Voir le contenu")
        self.btn_voir.setStyleSheet("background-color: #28a745; color: white; padding: 8px;")
        self.btn_voir.clicked.connect(self.on_voir_contenu)
        self.btn_voir.setEnabled(False) # Désactivé tant qu'aucune ligne n'est sélectionnée
        
        self.btn_import = QPushButton("Importer depuis Excel")
        self.btn_import.setStyleSheet("background-color: #007acc; color: white; padding: 8px;")
        self.btn_import.clicked.connect(self.on_import_excel)

        self.btn_mapping = QPushButton("Modifier le mapping d'import")
        self.btn_mapping.clicked.connect(self.on_modifier_mapping)
        
        self.btn_refresh = QPushButton("Actualiser")
        self.btn_refresh.clicked.connect(self.load_data)
        
        header_layout.addWidget(titre)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_voir)
        header_layout.addWidget(self.btn_import)
        header_layout.addWidget(self.btn_mapping)
        header_layout.addWidget(self.btn_refresh)
        
        # Tableau
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Nom", "Corps de métier", "Statut"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.on_voir_contenu)
        
        layout.addLayout(header_layout)
        layout.addWidget(self.table)

    def load_data(self):
        self.table.setRowCount(0)
        bibliotheques = self.biblio_service.lister_bibliotheques()
        
        for row, biblio in enumerate(bibliotheques):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(biblio.id)))
            self.table.setItem(row, 1, QTableWidgetItem(biblio.nom))
            self.table.setItem(row, 2, QTableWidgetItem(biblio.corps_metier))
            statut = "Actif" if biblio.actif else "Inactif"
            self.table.setItem(row, 3, QTableWidgetItem(statut))
            
        self.on_selection_changed()

    def on_selection_changed(self):
        has_selection = len(self.table.selectedItems()) > 0
        self.btn_voir.setEnabled(has_selection)

    def on_voir_contenu(self):
        selected = self.table.selectedItems()
        if not selected:
            return
            
        row = selected[0].row()
        biblio_id = int(self.table.item(row, 0).text())
        biblio_nom = self.table.item(row, 1).text()
        
        dialog = OuvragesDialog(biblio_id, biblio_nom, self.ouvrage_service, self)
        dialog.exec()

    def on_import_excel(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            "Sélectionner les fichiers Excel des bibliothèques",
            "",
            "Fichiers Excel (*.xlsx *.xls)"
        )
        
        if not filepaths:
            return

        summaries = []
        failures = []
        for filepath in filepaths:
            try:
                result = self._import_single_excel_library(filepath)
                summaries.append(result)
            except Exception as exc:
                failures.append((Path(filepath).name, str(exc)))

        self.load_data()
        QMessageBox.information(
            self,
            "Résumé de l'import collectif",
            self._format_collective_import_summary(summaries, failures),
        )

    def _import_single_excel_library(self, filepath: str):
        filename = Path(filepath)
        nom = filename.stem.strip()
        analysis = self.import_service.analyser_mapping(filepath)
        mapping_override = None
        mapping_nom = None
        mapping_parent_id = None
        creer_nouvelle_version = False
        if analysis.mapping:
            QMessageBox.information(
                self,
                "Mapping reconnu",
                f"{filename.name}\n\nMapping '{analysis.mapping_nom}' reconnu et appliqué.",
            )
        elif analysis.ouvrages_sheet_name:
            if analysis.partial_mapping_id:
                reply = QMessageBox.question(
                    self,
                    "Structure proche détectée",
                    f"{filename.name}\n\n"
                    f"Ce fichier ressemble au mapping '{analysis.partial_mapping_nom}' "
                    f"({analysis.partial_mapping_score:.0f} %) mais présente des différences.\n\n"
                    "Créer une nouvelle version de ce mapping ?\n\n"
                    "Oui : nouvelle version liée au mapping existant.\n"
                    "Non : mapping totalement indépendant.",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                )
                if reply == QMessageBox.Cancel:
                    raise RuntimeError("Import annulé pendant la validation du mapping.")
                if reply == QMessageBox.Yes:
                    mapping_parent_id = analysis.partial_mapping_id
                    creer_nouvelle_version = True
            dialog = MappingImportDialog(self.import_service, analysis, self)
            if dialog.exec() != QDialog.Accepted:
                raise RuntimeError("Import annulé pendant la validation du mapping.")
            mapping_override = dialog.mapping
            mapping_nom = dialog.name_input.text().strip() or "Mapping import bibliothèque"

        biblio = self.biblio_service.obtenir_par_nom(nom)
        if biblio:
            biblio_id = biblio.id
            created = False
        else:
            biblio_id = self.biblio_service.creer_bibliotheque(
                nom=nom,
                description=f"Importé depuis Excel : {filename.name}",
                corps_metier=self._guess_corps_metier(nom, filepath)
            )
            created = True

        summary = self.import_service.import_fichier(
            filepath,
            biblio_id,
            mapping_override=mapping_override,
            mapping_nom=mapping_nom,
            mapping_parent_id=mapping_parent_id,
            creer_nouvelle_version=creer_nouvelle_version,
        )
        return {
            "nom": nom,
            "fichier": filename.name,
            "bibliotheque_creee": created,
            "summary": summary,
        }

    def on_modifier_mapping(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un fichier Excel pour modifier son mapping",
            "",
            "Fichiers Excel (*.xlsx *.xls)"
        )
        if not filepath:
            return
        try:
            analysis = self.import_service.analyser_mapping(filepath)
            if analysis.partial_mapping_id and not analysis.mapping:
                QMessageBox.information(
                    self,
                    "Préremplissage",
                    f"Préremplissage depuis le mapping proche '{analysis.partial_mapping_nom}' "
                    f"({analysis.partial_mapping_score:.0f} %).",
                )
            dialog = MappingImportDialog(self.import_service, analysis, self)
            if dialog.exec() == QDialog.Accepted:
                self.import_service.mapping_repo.save(
                    dialog.name_input.text().strip() or "Mapping import bibliothèque",
                    analysis.signature_colonnes,
                    json.dumps(dialog.mapping, ensure_ascii=False),
                )
                QMessageBox.information(self, "Mapping enregistré", "Le mapping a été enregistré.")
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible de modifier le mapping :\n{exc}")

    def _guess_corps_metier(self, nom: str, filepath: str) -> str:
        text = f"{nom} {filepath}".lower()
        for label in ["plomberie", "couverture", "cvc", "electricite", "électricité", "espaces verts", "etancheite", "étanchéité", "cloisons"]:
            if label in text:
                return "Electricité" if "electric" in label or "électric" in label else label.title()
        return nom

    def _format_import_summary(self, summary) -> str:
        lines = [
            "L'importation de la bibliothèque s'est terminée.",
            "",
            f"Feuille des paramètres traitée : {'oui' if summary.feuille_parametres_traitee else 'non'}",
            f"Feuille des ouvrages traitée : {'oui' if summary.feuille_ouvrages_traitee else 'non'}",
            f"Paramètres généraux importés : {summary.parametres_importes}",
            f"Lignes lues : {summary.lignes_lues}",
            f"Ouvrages importés : {summary.ouvrages_importes}",
            f"Lignes ignorées : {summary.lignes_ignorees}",
            f"Erreurs : {len(summary.erreurs)}",
            f"Avertissements : {len(summary.avertissements)}",
            f"Doublons ignorés : {summary.doublons}",
            f"Unités manquantes : {summary.unites_manquantes}",
            f"Prix manquants : {summary.prix_manquants}",
        ]

        if summary.erreurs:
            lines.append("")
            lines.append("Erreurs :")
            lines.extend(f"- {message}" for message in summary.erreurs[:10])
        if summary.avertissements:
            lines.append("")
            lines.append("Avertissements :")
            lines.extend(f"- {message}" for message in summary.avertissements[:10])
            if len(summary.avertissements) > 10:
                lines.append(f"- ... {len(summary.avertissements) - 10} avertissements supplémentaires")
        return "\n".join(lines)

    def _format_collective_import_summary(self, summaries, failures) -> str:
        total_files = len(summaries) + len(failures)
        total_ouvrages = sum(item["summary"].ouvrages_importes for item in summaries)
        total_doublons = sum(item["summary"].doublons for item in summaries)
        total_erreurs = sum(len(item["summary"].erreurs) for item in summaries) + len(failures)
        lines = [
            f"Fichiers sélectionnés : {total_files}",
            f"Bibliothèques importées : {len(summaries)}",
            f"Ouvrages ajoutés : {total_ouvrages}",
            f"Doublons ignorés : {total_doublons}",
            f"Erreurs : {total_erreurs}",
            "",
            "Détail :",
        ]
        for item in summaries:
            summary = item["summary"]
            statut = "créée" if item["bibliotheque_creee"] else "existante"
            lines.append(
                f"- {item['fichier']} → {item['nom']} ({statut}) : "
                f"{summary.ouvrages_importes} ajoutés, {summary.doublons} doublons ignorés, "
                f"{len(summary.erreurs)} erreurs, {len(summary.avertissements)} avertissements"
            )
        for filename, message in failures:
            lines.append(f"- {filename} : échec ({message})")
        return "\n".join(lines)
