import json
from decimal import Decimal

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from services.ouvrage_service import OuvrageService
from models.entites import OuvrageBibliotheque
from ui.theme import APP_STYLESHEET


class OuvrageFormDialog(QDialog):
    def __init__(self, bibliotheque_id: int, ouvrage: OuvrageBibliotheque | None = None, parent=None):
        super().__init__(parent)
        self.bibliotheque_id = bibliotheque_id
        self.ouvrage = ouvrage
        self.setWindowTitle("Modifier l'ouvrage" if ouvrage else "Ajouter un ouvrage")
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.code_input = QLineEdit(ouvrage.code if ouvrage and ouvrage.code else "")
        self.designation_input = QLineEdit(ouvrage.designation if ouvrage else "")
        self.famille_input = QLineEdit(ouvrage.famille if ouvrage and ouvrage.famille else "")
        self.unite_input = QLineEdit(ouvrage.unite if ouvrage else "")

        self.fournitures_input = self._money_spin(ouvrage.fournitures_ht_import if ouvrage else None)
        self.mo_heures_input = self._quantity_spin(ouvrage.mo_heures_import if ouvrage else None)
        self.taux_horaire_input = self._money_spin(ouvrage.taux_horaire_import if ouvrage else None)
        self.mo_ht_input = self._money_spin(ouvrage.mo_ht_import if ouvrage else None)
        self.debourse_input = self._money_spin(ouvrage.debourse_sec_import if ouvrage else None)
        self.pv_st_input = self._money_spin(ouvrage.pv_st_ht_import if ouvrage else None)
        self.pv_eg_input = self._money_spin(ouvrage.pv_eg_ht_import if ouvrage else None)

        form.addRow("Code", self.code_input)
        form.addRow("Désignation", self.designation_input)
        form.addRow("Famille", self.famille_input)
        form.addRow("Unité", self.unite_input)
        form.addRow("Fournitures HT/u", self.fournitures_input)
        form.addRow("MO h/u", self.mo_heures_input)
        form.addRow("Taux horaire", self.taux_horaire_input)
        form.addRow("MO HT/u", self.mo_ht_input)
        form.addRow("Déboursé sec", self.debourse_input)
        form.addRow("PV ST HT", self.pv_st_input)
        form.addRow("PV EG HT", self.pv_eg_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def _money_spin(self, value):
        spin = QDoubleSpinBox()
        spin.setRange(0, 1_000_000)
        spin.setDecimals(4)
        spin.setSuffix(" €")
        if value is not None:
            spin.setValue(float(value))
        return spin

    def _quantity_spin(self, value):
        spin = QDoubleSpinBox()
        spin.setRange(0, 1_000_000)
        spin.setDecimals(4)
        if value is not None:
            spin.setValue(float(value))
        return spin

    def accept(self):
        if not self.designation_input.text().strip():
            QMessageBox.warning(self, "Champ obligatoire", "La désignation est obligatoire.")
            return
        if not self.unite_input.text().strip():
            QMessageBox.warning(self, "Champ obligatoire", "L'unité est obligatoire.")
            return
        super().accept()

    def get_ouvrage(self) -> OuvrageBibliotheque:
        existing = self.ouvrage
        return OuvrageBibliotheque(
            id=existing.id if existing else None,
            bibliotheque_id=self.bibliotheque_id,
            code=self.code_input.text().strip() or None,
            designation=self.designation_input.text().strip(),
            famille=self.famille_input.text().strip() or None,
            unite=self.unite_input.text().strip(),
            mode_chiffrage=existing.mode_chiffrage if existing else "manuel",
            fournitures_ht_import=self._decimal(self.fournitures_input.value()),
            mo_heures_import=self._decimal(self.mo_heures_input.value()),
            taux_horaire_import=self._decimal(self.taux_horaire_input.value()),
            mo_ht_import=self._decimal(self.mo_ht_input.value()),
            materiel_ht_import=existing.materiel_ht_import if existing else Decimal("0"),
            transport_ht_import=existing.transport_ht_import if existing else Decimal("0"),
            sous_traitance_ht_import=existing.sous_traitance_ht_import if existing else Decimal("0"),
            debourse_sec_import=self._decimal(self.debourse_input.value()),
            pv_st_ht_import=self._decimal(self.pv_st_input.value()),
            pv_eg_ht_import=self._decimal(self.pv_eg_input.value()),
            debourse_sec_calcule=existing.debourse_sec_calcule if existing else None,
            pv_st_ht_calcule=existing.pv_st_ht_calcule if existing else None,
            pv_eg_ht_calcule=existing.pv_eg_ht_calcule if existing else None,
            source_calcul=existing.source_calcul if existing else "manuel",
            date_dernier_calcul=existing.date_dernier_calcul if existing else None,
            attributs_techniques=existing.attributs_techniques if existing else "{}",
            donnees_source_json=existing.donnees_source_json if existing else "{}",
            actif=existing.actif if existing else True,
            date_creation=existing.date_creation if existing else "",
            date_modification=existing.date_modification if existing else "",
        )

    def _decimal(self, value: float) -> Decimal:
        return Decimal(str(value))


class OuvrageDetailsDialog(QDialog):
    FIELD_LABELS = [
        ("systeme", "Système"),
        ("type", "Type"),
        ("configuration", "Configuration"),
        ("epaisseur_mm", "Épaisseur"),
        ("ossature", "Ossature"),
        ("parement_face_a", "Parement face A"),
        ("parement_face_b", "Parement face B"),
        ("isolant", "Isolant"),
        ("feu", "Feu"),
        ("acoustique_db", "Acoustique"),
        ("hauteur_max_m", "Hauteur maximale"),
        ("observations", "Observations"),
    ]

    def __init__(self, ouvrage: OuvrageBibliotheque, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Détails : {ouvrage.designation}")
        self.resize(820, 640)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        attributs = self._loads(ouvrage.attributs_techniques)

        for key, label in self.FIELD_LABELS:
            value = attributs.get(key)
            form.addRow(label, QLabel("-" if value in (None, "") else str(value)))

        source_title = QLabel("Données source JSON")
        source_json = QPlainTextEdit()
        source_json.setReadOnly(True)
        source_json.setPlainText(self._pretty_json(ouvrage.donnees_source_json))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(source_title)
        layout.addWidget(source_json)
        layout.addWidget(buttons)

    def _loads(self, raw: str | None) -> dict:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _pretty_json(self, raw: str | None) -> str:
        if not raw:
            return "{}"
        try:
            return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return raw


class OuvragesDialog(QDialog):
    COLUMNS = [
        "Code",
        "Désignation",
        "Famille",
        "Unité",
        "Fournitures HT",
        "MO h/u",
        "Taux horaire",
        "MO HT",
        "Déboursé Sec",
        "PV ST HT",
        "PV EG HT",
    ]

    def __init__(self, bibliotheque_id: int, bibliotheque_nom: str, ouvrage_service: OuvrageService, parent=None):
        super().__init__(parent)
        self.bibliotheque_id = bibliotheque_id
        self.ouvrage_service = ouvrage_service
        self.ouvrages: list[OuvrageBibliotheque] = []
        self.setWindowTitle(f"Ouvrages de la bibliothèque : {bibliotheque_nom}")
        self.resize(1300, 720)
        
        self.setStyleSheet(APP_STYLESHEET)

        self._setup_ui()
        self.load_data()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        filters_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher code, désignation, famille...")
        self.search_input.textChanged.connect(self.apply_filters)

        self.famille_filter = QComboBox()
        self.famille_filter.currentTextChanged.connect(self.apply_filters)

        self.unite_filter = QComboBox()
        self.unite_filter.currentTextChanged.connect(self.apply_filters)

        self.btn_add = QPushButton("Ajouter")
        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit = QPushButton("Modifier")
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_delete = QPushButton("Supprimer")
        self.btn_delete.clicked.connect(self.on_delete)
        self.btn_details = QPushButton("Voir les détails")
        self.btn_details.clicked.connect(self.on_details)
        self.btn_refresh = QPushButton("Actualiser")
        self.btn_refresh.clicked.connect(self.load_data)

        filters_layout.addWidget(self.search_input, 2)
        filters_layout.addWidget(QLabel("Famille"))
        filters_layout.addWidget(self.famille_filter)
        filters_layout.addWidget(QLabel("Unité"))
        filters_layout.addWidget(self.unite_filter)
        filters_layout.addWidget(self.btn_add)
        filters_layout.addWidget(self.btn_edit)
        filters_layout.addWidget(self.btn_delete)
        filters_layout.addWidget(self.btn_details)
        filters_layout.addWidget(self.btn_refresh)
        
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        self.table.itemDoubleClicked.connect(self.on_details)
        
        layout.addLayout(filters_layout)
        layout.addWidget(self.table)
        
    def load_data(self):
        self.ouvrages = self.ouvrage_service.lister_ouvrages_bibliotheque(self.bibliotheque_id)
        self.refresh_filter_values()
        self.apply_filters()

    def refresh_filter_values(self):
        current_famille = self.famille_filter.currentText()
        current_unite = self.unite_filter.currentText()

        familles = sorted({o.famille for o in self.ouvrages if o.famille})
        unites = sorted({o.unite for o in self.ouvrages if o.unite})

        self.famille_filter.blockSignals(True)
        self.unite_filter.blockSignals(True)
        self.famille_filter.clear()
        self.unite_filter.clear()
        self.famille_filter.addItem("Toutes")
        self.unite_filter.addItem("Toutes")
        self.famille_filter.addItems(familles)
        self.unite_filter.addItems(unites)

        if current_famille in familles:
            self.famille_filter.setCurrentText(current_famille)
        if current_unite in unites:
            self.unite_filter.setCurrentText(current_unite)
        self.famille_filter.blockSignals(False)
        self.unite_filter.blockSignals(False)

    def apply_filters(self):
        search = self.search_input.text().strip().lower()
        famille = self.famille_filter.currentText()
        unite = self.unite_filter.currentText()

        filtered = []
        for ouvrage in self.ouvrages:
            haystack = " ".join([
                ouvrage.code or "",
                ouvrage.designation or "",
                ouvrage.famille or "",
                ouvrage.unite or "",
            ]).lower()
            if search and search not in haystack:
                continue
            if famille and famille != "Toutes" and ouvrage.famille != famille:
                continue
            if unite and unite != "Toutes" and ouvrage.unite != unite:
                continue
            filtered.append(ouvrage)

        self.populate_table(filtered)

    def populate_table(self, ouvrages: list[OuvrageBibliotheque]):
        self.table.setRowCount(0)
        
        for row, ouvrage in enumerate(ouvrages):
            self.table.insertRow(row)
            values = [
                ouvrage.code or "",
                ouvrage.designation,
                ouvrage.famille or "",
                ouvrage.unite,
                self._money(ouvrage.fournitures_ht_import),
                self._number(ouvrage.mo_heures_import),
                self._money(ouvrage.taux_horaire_import),
                self._money(ouvrage.mo_ht_import),
                self._money(ouvrage.debourse_sec_import),
                self._money(ouvrage.pv_st_ht_import),
                self._money(ouvrage.pv_eg_ht_import),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, ouvrage.id)
                self.table.setItem(row, col, item)
        self.update_buttons()

    def selected_ouvrage(self) -> OuvrageBibliotheque | None:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        ouvrage_id = self.table.item(row, 0).data(Qt.UserRole)
        return next((ouvrage for ouvrage in self.ouvrages if ouvrage.id == ouvrage_id), None)

    def update_buttons(self):
        has_selection = self.selected_ouvrage() is not None
        self.btn_edit.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)
        self.btn_details.setEnabled(has_selection)

    def on_add(self):
        dialog = OuvrageFormDialog(self.bibliotheque_id, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.ouvrage_service.creer_ouvrage(dialog.get_ouvrage())
            self.load_data()

    def on_edit(self):
        ouvrage = self.selected_ouvrage()
        if not ouvrage:
            return
        dialog = OuvrageFormDialog(self.bibliotheque_id, ouvrage, self)
        if dialog.exec() == QDialog.Accepted:
            self.ouvrage_service.modifier_ouvrage(dialog.get_ouvrage())
            self.load_data()

    def on_delete(self):
        ouvrage = self.selected_ouvrage()
        if not ouvrage:
            return
        reply = QMessageBox.question(
            self,
            "Supprimer l'ouvrage",
            f"Supprimer l'ouvrage '{ouvrage.designation}' ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.ouvrage_service.supprimer_ouvrage(ouvrage.id)
            self.load_data()

    def on_details(self):
        ouvrage = self.selected_ouvrage()
        if ouvrage:
            OuvrageDetailsDialog(ouvrage, self).exec()

    def _money(self, value) -> str:
        return f"{value:.2f} €" if value is not None else "-"

    def _number(self, value) -> str:
        return f"{value:.4f}".rstrip("0").rstrip(".") if value is not None else "-"
