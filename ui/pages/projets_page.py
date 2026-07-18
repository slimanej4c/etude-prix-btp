from decimal import Decimal
import logging
import json

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QFrame,
    QGroupBox,
)
from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter

from database.db_manager import DatabaseManager
from repositories.projet_repository import ProjetRepository
from repositories.section_projet_repository import SectionProjetRepository
from repositories.correspondance_dpgf_repository import CorrespondanceDpgfRepository
from repositories.parametre_repository import ParametreRepository
from repositories.version_projet_repository import VersionProjetRepository
from repositories.bibliotheque_repository import BibliothequeRepository
from repositories.ouvrage_bibliotheque_repository import OuvrageBibliothequeRepository
from models.entites import OuvrageBibliotheque
from services.import_dpgf_service import ImportDpgfService
from services.correspondance_service import CorrespondanceService
from services.chiffrage_projet_service import ChiffrageProjetService, DEFAULT_COEFFICIENT_VENTE
from services.parametre_service import ParametreService
from services.projet_service import ProjetService
from services.section_projet_service import SectionProjetService
from services.version_projet_service import SOURCE_ACTUEL, VersionProjetService
from ui.theme import APP_STYLESHEET, COLORS, band_style, status_style

try:
    from PySide6.QtCharts import QChart, QChartView, QPieSeries
except Exception:
    QChart = None
    QChartView = None
    QPieSeries = None

logger = logging.getLogger(__name__)


class DpgfImportWorker(QObject):
    progression = Signal(int, str)
    succes = Signal(object)
    erreur = Signal(str)
    termine = Signal()

    def __init__(self, db_path, migrations_dir, filepath: str, projet_id: int, header_overrides=None, timeout_seconds: int = 120):
        super().__init__()
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self.filepath = filepath
        self.projet_id = projet_id
        self.header_overrides = header_overrides or {}
        self.timeout_seconds = timeout_seconds

    @Slot()
    def run(self):
        logger.info(
            "Worker DPGF : démarrage projet_id=%s fichier=%s thread=%s",
            self.projet_id,
            self.filepath,
            QThread.currentThread(),
        )
        try:
            self.progression.emit(0, "Import DPGF démarré")
            logger.info("Worker DPGF : création DatabaseManager thread=%s", QThread.currentThread())
            db_manager = DatabaseManager(db_path=self.db_path, migrations_dir=self.migrations_dir)
            section_repo = SectionProjetRepository(db_manager)
            import_service = ImportDpgfService(section_repo)
            logger.info("Worker DPGF : service d'import créé thread=%s", QThread.currentThread())
            summary = import_service.importer_fichier(
                self.filepath,
                self.projet_id,
                self.header_overrides,
                timeout_seconds=self.timeout_seconds,
            )
            logger.info("Worker DPGF : succès projet_id=%s", self.projet_id)
            self.progression.emit(100, "Import DPGF terminé")
            self.succes.emit(summary)
        except Exception as exc:
            logger.exception("Worker DPGF : erreur")
            self.erreur.emit(str(exc))
        finally:
            logger.info("Worker DPGF : termine émis thread=%s", QThread.currentThread())
            self.termine.emit()


class MatchingWorker(QObject):
    progression = Signal(int, int, str)
    succes = Signal(object)
    erreur = Signal(str)
    termine = Signal()

    def __init__(self, db_path, migrations_dir, projet_id: int, elargir_toutes_bibliotheques: bool = False, mode: str = "textuel"):
        super().__init__()
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self.projet_id = projet_id
        self.elargir_toutes_bibliotheques = elargir_toutes_bibliotheques
        self.mode = mode
        self._cancel_requested = False

    @Slot()
    def cancel(self):
        self._cancel_requested = True

    @Slot()
    def run(self):
        logger.info("Worker matching : démarrage projet_id=%s thread=%s", self.projet_id, QThread.currentThread())
        try:
            db_manager = DatabaseManager(db_path=self.db_path, migrations_dir=self.migrations_dir)
            section_repo = SectionProjetRepository(db_manager)
            corr_repo = CorrespondanceDpgfRepository(db_manager)
            param_service = ParametreService(ParametreRepository(db_manager))
            service = CorrespondanceService(db_manager, corr_repo, section_repo, param_service)

            def on_progress(progress):
                self.progression.emit(
                    progress.traites,
                    progress.total,
                    f"{progress.traites}/{progress.total} lignes traitées",
                )

            if self.mode == "ia":
                result = service.lancer_recherche_ia_projet(
                    self.projet_id,
                    rechercher_toutes_bibliotheques=self.elargir_toutes_bibliotheques,
                    progress_callback=on_progress,
                    should_cancel=lambda: self._cancel_requested,
                )
            else:
                result = service.lancer_rapprochement_projet(
                    self.projet_id,
                    elargir_toutes_bibliotheques=self.elargir_toutes_bibliotheques,
                    progress_callback=on_progress,
                    should_cancel=lambda: self._cancel_requested,
                )
            self.succes.emit(result)
        except Exception as exc:
            logger.exception("Worker matching : erreur")
            self.erreur.emit(str(exc))
        finally:
            logger.info("Worker matching : termine émis thread=%s", QThread.currentThread())
            self.termine.emit()


class ProjetFormDialog(QDialog):
    def __init__(self, projet=None, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.setWindowTitle("Modifier le projet" if projet else "Nouveau projet")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.nom_input = QLineEdit(projet.nom if projet else "")
        self.client_input = QLineEdit(projet.client if projet else "")
        self.reference_input = QLineEdit(projet.reference if projet else "")
        self.statut_input = QLineEdit(projet.statut if projet else "Nouveau")
        form.addRow("Nom", self.nom_input)
        form.addRow("Client", self.client_input)
        form.addRow("Référence", self.reference_input)
        form.addRow("Statut", self.statut_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self):
        if not self.nom_input.text().strip():
            QMessageBox.warning(self, "Champ obligatoire", "Le nom du projet est obligatoire.")
            return
        super().accept()


class OuvrageBibliothequeDetailDialog(QDialog):
    def __init__(self, details: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Détail ouvrage bibliothèque")
        self.resize(760, 560)
        self.setStyleSheet(APP_STYLESHEET)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        fields = [
            ("Code", details.get("code")),
            ("Désignation", details.get("designation")),
            ("Famille", details.get("famille")),
            ("Unité", details.get("unite")),
            ("Fournitures", details.get("fournitures_ht_import")),
            ("MO", details.get("mo_ht_import")),
            ("Déboursé sec", details.get("debourse_sec_import")),
            ("PV ST", details.get("pv_st_ht_import")),
            ("PV EG", details.get("pv_eg_ht_import")),
        ]
        for label, value in fields:
            form.addRow(label, QLabel("" if value is None else str(value)))
        attrs = QTableWidget()
        attrs.setColumnCount(2)
        attrs.setHorizontalHeaderLabels(["Attribut", "Valeur"])
        try:
            data = json.loads(details.get("attributs_techniques") or "{}")
        except json.JSONDecodeError:
            data = {}
        attrs.setRowCount(len(data))
        for row, (key, value) in enumerate(data.items()):
            attrs.setItem(row, 0, QTableWidgetItem(str(key)))
            attrs.setItem(row, 1, QTableWidgetItem("" if value is None else str(value)))
        attrs.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addLayout(form)
        layout.addWidget(QLabel("Attributs techniques"))
        layout.addWidget(attrs)
        layout.addWidget(buttons)


class CatalogueSearchDialog(QDialog):
    def __init__(self, correspondance_service: CorrespondanceService, parent=None):
        super().__init__(parent)
        self.service = correspondance_service
        self.selected_ouvrage_id = None
        self.setWindowTitle("Recherche manuelle dans le catalogue")
        self.resize(1000, 640)
        self.setStyleSheet(APP_STYLESHEET)
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Code, désignation, famille...")
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Code")
        self.famille_input = QLineEdit()
        self.famille_input.setPlaceholderText("Famille")
        btn_search = QPushButton("Rechercher")
        btn_search.clicked.connect(self.load_results)
        filters.addWidget(self.search_input)
        filters.addWidget(self.code_input)
        filters.addWidget(self.famille_input)
        filters.addWidget(btn_search)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Code", "Désignation", "Famille", "Unité", "Bibliothèque"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addLayout(filters)
        layout.addWidget(self.table)
        layout.addWidget(buttons)
        self.load_results()

    def load_results(self):
        results = self.service.recherche_catalogue_libre(
            self.search_input.text(),
            self.famille_input.text(),
            self.code_input.text(),
        )
        self.table.setRowCount(0)
        for row, result in enumerate(results[:300]):
            self.table.insertRow(row)
            values = [
                str(result["ouvrage_bibliotheque_id"]),
                result["code"] or "",
                result["designation"] or "",
                result["famille"] or "",
                result["unite"] or "",
                result["bibliotheque_nom"] or "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, result["ouvrage_bibliotheque_id"])
                self.table.setItem(row, col, item)

    def accept(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez un ouvrage du catalogue.")
            return
        row = selected[0].row()
        self.selected_ouvrage_id = self.table.item(row, 0).data(Qt.UserRole)
        super().accept()


class QuickOuvrageCreateDialog(QDialog):
    def __init__(self, db_manager: DatabaseManager, section, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.section = section
        self.created_ouvrage_id = None
        self.bibliotheques = [b for b in BibliothequeRepository(db_manager).get_all() if b.actif]
        self.setWindowTitle("Créer un ouvrage de bibliothèque")
        self.resize(620, 520)
        self.setStyleSheet(APP_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.bibliotheque_combo = QComboBox()
        for bibliotheque in self.bibliotheques:
            self.bibliotheque_combo.addItem(f"{bibliotheque.nom} ({bibliotheque.corps_metier})", bibliotheque.id)
        self.code_input = QLineEdit(section.numero_article or "")
        self.designation_input = QLineEdit(section.libelle or "")
        self.famille_input = QLineEdit(section.feuille_source or "")
        self.unite_input = QLineEdit(section.unite or "")
        self.ds_mat_input = self._money_spin()
        self.ds_mo_input = self._money_spin()
        self.ds_materiel_input = self._money_spin()
        self.ds_transport_input = self._money_spin()
        self.ds_st_input = self._money_spin()
        self.pv_coeff_input = QDoubleSpinBox()
        self.pv_coeff_input.setRange(0, 100)
        self.pv_coeff_input.setDecimals(4)
        self.pv_coeff_input.setValue(float(DEFAULT_COEFFICIENT_VENTE))

        form.addRow("Bibliothèque cible", self.bibliotheque_combo)
        form.addRow("Code", self.code_input)
        form.addRow("Désignation", self.designation_input)
        form.addRow("Famille", self.famille_input)
        form.addRow("Unité", self.unite_input)
        form.addRow("Matériaux", self.ds_mat_input)
        form.addRow("MO", self.ds_mo_input)
        form.addRow("Matériel", self.ds_materiel_input)
        form.addRow("Transport", self.ds_transport_input)
        form.addRow("Sous-traitance", self.ds_st_input)
        form.addRow("Coefficient vente", self.pv_coeff_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _money_spin(self):
        spin = QDoubleSpinBox()
        spin.setRange(0, 1_000_000_000)
        spin.setDecimals(2)
        spin.setSuffix(" €")
        return spin

    def accept(self):
        if not self.bibliotheques:
            QMessageBox.warning(self, "Bibliothèque requise", "Créez ou activez une bibliothèque avant d'ajouter un ouvrage.")
            return
        if not self.designation_input.text().strip():
            QMessageBox.warning(self, "Champ obligatoire", "La désignation est obligatoire.")
            return
        if not self.unite_input.text().strip():
            QMessageBox.warning(self, "Champ obligatoire", "L'unité est obligatoire.")
            return
        ds_mat = Decimal(str(self.ds_mat_input.value()))
        ds_mo = Decimal(str(self.ds_mo_input.value()))
        ds_materiel = Decimal(str(self.ds_materiel_input.value()))
        ds_transport = Decimal(str(self.ds_transport_input.value()))
        ds_st = Decimal(str(self.ds_st_input.value()))
        ds_total = ds_mat + ds_mo + ds_materiel + ds_transport + ds_st
        pv_eg = ds_total * Decimal(str(self.pv_coeff_input.value()))
        ouvrage = OuvrageBibliotheque(
            id=None,
            bibliotheque_id=self.bibliotheque_combo.currentData(),
            code=self.code_input.text().strip() or None,
            designation=self.designation_input.text().strip(),
            famille=self.famille_input.text().strip() or None,
            unite=self.unite_input.text().strip(),
            mode_chiffrage="manuel",
            fournitures_ht_import=ds_mat,
            mo_heures_import=None,
            taux_horaire_import=None,
            mo_ht_import=ds_mo,
            materiel_ht_import=ds_materiel,
            transport_ht_import=ds_transport,
            sous_traitance_ht_import=ds_st,
            debourse_sec_import=ds_total,
            pv_st_ht_import=pv_eg,
            pv_eg_ht_import=pv_eg,
            debourse_sec_calcule=None,
            pv_st_ht_calcule=None,
            pv_eg_ht_calcule=None,
            source_calcul="manuel",
            date_dernier_calcul=None,
            attributs_techniques="{}",
            donnees_source_json=json.dumps({"origine": "creation_depuis_dpgf"}, ensure_ascii=False),
            actif=True,
            date_creation="",
            date_modification="",
        )
        self.created_ouvrage_id = OuvrageBibliothequeRepository(self.db_manager).create(ouvrage)
        super().accept()


class ChiffrageLigneDialog(QDialog):
    COMPONENTS = [
        ("ds_mo", "MO"),
        ("ds_mat", "Matériaux"),
        ("ds_materiel", "Matériel"),
        ("ds_transport", "Transport"),
        ("ds_st", "Sous-traitance"),
    ]

    def __init__(self, section, chiffrage_service: ChiffrageProjetService, parent=None):
        super().__init__(parent)
        self.section = section
        self.service = chiffrage_service
        self.ouvrage = self.service.obtenir_ou_creer_ouvrage(section.id)
        self.setWindowTitle(f"Chiffrer - {section.numero_article or ''} {section.libelle}")
        self.resize(620, 430)
        self.setStyleSheet(APP_STYLESHEET)

        layout = QVBoxLayout(self)
        title = QLabel(f"{section.numero_article or ''} - {section.libelle}")
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        meta = QLabel(f"Unité : {section.unite or '-'} | Quantité : {self._decimal_text(section.quantite)}")
        self.surcharge_label = QLabel("")
        self.surcharge_label.setStyleSheet(f"color: {COLORS['warning']}; font-weight: bold;")

        form = QFormLayout()
        self.inputs = {}
        for key, label in self.COMPONENTS:
            spin = self._money_spin(self.ouvrage[key])
            spin.valueChanged.connect(self.recalculate)
            self.inputs[key] = spin
            form.addRow(label, spin)

        self.coefficient_input = QDoubleSpinBox()
        self.coefficient_input.setRange(0, 100)
        self.coefficient_input.setDecimals(4)
        self.coefficient_input.setValue(float(self._initial_coefficient()))
        self.coefficient_input.valueChanged.connect(self.recalculate)
        form.addRow("Coefficient PV", self.coefficient_input)

        self.ds_total_label = QLabel("")
        self.pv_unitaire_label = QLabel("")
        self.pv_total_label = QLabel("")
        form.addRow("DS total", self.ds_total_label)
        form.addRow("PV unitaire", self.pv_unitaire_label)
        form.addRow("PV total", self.pv_total_label)

        actions = QHBoxLayout()
        self.btn_copy = QPushButton("Copier depuis la bibliothèque")
        self.btn_copy.clicked.connect(self.copy_from_library)
        actions.addWidget(self.btn_copy)
        actions.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)

        layout.addWidget(title)
        layout.addWidget(meta)
        layout.addWidget(self.surcharge_label)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(buttons)
        self.recalculate()
        self.refresh_surcharge()

    def _money_spin(self, value):
        spin = QDoubleSpinBox()
        spin.setRange(0, 1_000_000_000)
        spin.setDecimals(2)
        spin.setSuffix(" €")
        spin.setValue(float(value or 0))
        return spin

    def _initial_coefficient(self) -> Decimal:
        ds_total = Decimal(str(self.ouvrage["ds_total"] or 0))
        pv_total = Decimal(str(self.ouvrage["pv_total"] or 0))
        if ds_total:
            return pv_total / ds_total
        return DEFAULT_COEFFICIENT_VENTE

    def recalculate(self):
        ds_total = sum(Decimal(str(spin.value())) for spin in self.inputs.values())
        coefficient = Decimal(str(self.coefficient_input.value()))
        pv_total = ds_total * coefficient
        quantite = Decimal(str(self.section.quantite or 1))
        pv_unitaire = pv_total / quantite if quantite else Decimal("0")
        self.ds_total_label.setText(self._money_text(ds_total))
        self.pv_unitaire_label.setText(self._money_text(pv_unitaire))
        self.pv_total_label.setText(self._money_text(pv_total))

    def copy_from_library(self):
        try:
            self.ouvrage = self.service.copier_depuis_bibliotheque(self.section.id)
        except Exception as exc:
            QMessageBox.warning(self, "Copie impossible", str(exc))
            return
        for key, spin in self.inputs.items():
            spin.setValue(float(self.ouvrage[key] or 0))
        self.coefficient_input.setValue(float(self._initial_coefficient()))
        self.recalculate()
        self.refresh_surcharge()

    def save(self):
        try:
            self.ouvrage = self.service.sauvegarder_chiffrage(
                self.section.id,
                *(Decimal(str(self.inputs[key].value())) for key, _label in self.COMPONENTS),
                Decimal(str(self.coefficient_input.value())),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Chiffrage impossible :\n{exc}")
            return
        self.refresh_surcharge()
        self.accept()

    def refresh_surcharge(self):
        if self.service.est_surcharge_manuelle(self.section.id):
            self.surcharge_label.setText("Surcharge manuelle par rapport à la bibliothèque")
        else:
            self.surcharge_label.setText("Chiffrage courant")

    def _money_text(self, value: Decimal) -> str:
        return f"{value.quantize(Decimal('0.01'))} €"

    def _decimal_text(self, value) -> str:
        return "" if value is None else str(value)


class DecimalCellDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QDoubleSpinBox(parent)
        editor.setRange(0, 1_000_000_000)
        editor.setDecimals(2)
        return editor

    def setEditorData(self, editor, index):
        try:
            editor.setValue(float(Decimal(str(index.data() or "0").replace(",", "."))))
        except Exception:
            editor.setValue(0)

    def setModelData(self, editor, model, index):
        model.setData(index, f"{Decimal(str(editor.value())).quantize(Decimal('0.01'))}", Qt.EditRole)


class ChiffrageTableDialog(QDialog):
    COLUMNS = [
        "Code", "Désignation", "Unité", "Quantité", "MO", "Matériaux", "Matériel",
        "Transport", "Sous-traitance", "DS total", "Coefficient vente", "PV unitaire", "PV total",
    ]
    EDITABLE_KEYS = {
        4: "ds_mo",
        5: "ds_mat",
        6: "ds_materiel",
        7: "ds_transport",
        8: "ds_st",
    }
    MONEY_KEYS = {
        4: "ds_mo",
        5: "ds_mat",
        6: "ds_materiel",
        7: "ds_transport",
        8: "ds_st",
        9: "ds_total",
        11: "pv_unitaire",
        12: "pv_total",
    }

    def __init__(
        self,
        projet,
        chiffrage_service: ChiffrageProjetService,
        focus_section_id=None,
        parent=None,
        correspondance_service: CorrespondanceService | None = None,
        db_manager: DatabaseManager | None = None,
        version_service: VersionProjetService | None = None,
    ):
        super().__init__(parent)
        self.projet = projet
        self.service = chiffrage_service
        self.correspondance_service = correspondance_service
        self.db_manager = db_manager or chiffrage_service.db
        self.version_service = version_service or VersionProjetService(VersionProjetRepository(self.db_manager))
        self.mapping_enabled = correspondance_service is not None
        self.original_version_prompt_shown = self._has_original_version()
        self.focus_section_id = focus_section_id
        self.rows = []
        self.row_by_ouvrage_id = {}
        self.group_rows = {}
        self.ai_matching_thread = None
        self.ai_matching_worker = None
        self._updating = False
        self.viewing_version_id = None
        self.columns = list(self.COLUMNS)
        self.mapping_col_status = None
        self.mapping_col_proposals = None
        self.mapping_col_actions = None
        if self.mapping_enabled:
            self.mapping_col_status = len(self.columns)
            self.mapping_col_proposals = len(self.columns) + 1
            self.mapping_col_actions = len(self.columns) + 2
            self.columns.extend(["Lien bibliothèque", "Propositions", "Actions"])
        self.setWindowTitle(f"DPGF - Mapping et chiffrage - {projet.nom}" if self.mapping_enabled else f"Chiffrage - {projet.nom}")
        self.resize(1500, 820)
        self.setStyleSheet(APP_STYLESHEET)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("DPGF - Mapping et chiffrage" if self.mapping_enabled else "Chiffrage courant")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("font-weight: bold;")
        self.btn_copy = QPushButton("Copier depuis la bibliothèque")
        self.btn_copy.clicked.connect(self.copy_selected_from_library)
        self.btn_auto_search = QPushButton("Rechercher auto manquants")
        self.btn_auto_search.clicked.connect(self.search_auto_for_all_missing)
        self.btn_auto_search_ai = QPushButton("Recherche auto avec IA")
        self.btn_auto_search_ai.clicked.connect(self.search_ai_for_all_missing)
        self.btn_detail = QPushButton("Détail ligne")
        self.btn_detail.clicked.connect(self.open_selected_detail)
        self.btn_original_work = QPushButton("Original")
        self.btn_original_work.setToolTip("Afficher le travail courant modifiable")
        self.btn_original_work.clicked.connect(self.show_original_work)
        self.btn_save_work_version = QPushButton("Sauvegarder en version")
        self.btn_save_work_version.setToolTip("Créer une version figée du chiffrage courant")
        self.btn_save_work_version.clicked.connect(self.save_current_work_as_version)
        self.version_combo = QComboBox()
        self.version_combo.setMinimumWidth(190)
        self.version_combo.currentIndexChanged.connect(self.on_version_combo_changed)
        self.btn_view_versions = QPushButton("Voir les versions")
        self.btn_view_versions.clicked.connect(self.open_versions_dialog)
        header.addWidget(title)
        header.addWidget(self.progress_label)
        header.addStretch()
        header.addWidget(self.btn_original_work)
        header.addWidget(self.btn_save_work_version)
        header.addWidget(self.version_combo)
        header.addWidget(self.btn_view_versions)
        header.addWidget(self.btn_auto_search)
        header.addWidget(self.btn_auto_search_ai)
        header.addWidget(self.btn_copy)
        header.addWidget(self.btn_detail)
        self.refresh_version_controls()

        self.dashboard_box = self._create_dashboard()

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setColumnWidth(1, 420)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setItemDelegate(DecimalCellDelegate(self.table))
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.btn_copy.setVisible(not self.mapping_enabled)
        self.btn_auto_search.setVisible(self.mapping_enabled)
        self.btn_auto_search_ai.setVisible(self.mapping_enabled)

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.reject)
        layout.addLayout(header)
        layout.addWidget(self.dashboard_box)
        layout.addWidget(self.table)
        layout.addWidget(close_buttons)
        self.reload()

    def _create_dashboard(self):
        box = QGroupBox("Tableau de bord - Pendant le chiffrage")
        box.setMaximumHeight(245)
        layout = QHBoxLayout(box)

        totals_panel = QWidget()
        totals_grid = QGridLayout(totals_panel)
        totals_grid.setContentsMargins(0, 0, 0, 0)
        self.dashboard_labels = {}
        metrics = [
            ("ds_total", "DS total projet"),
            ("pv_total", "PV total projet"),
            ("progress", "Lignes chiffrées"),
            ("margin", "Marge globale"),
            ("validated", "Correspondances validées"),
            ("proposed", "Propositions à choisir"),
            ("manual", "Saisies manuelles"),
            ("untreated", "Non traitées"),
        ]
        for index, (key, label) in enumerate(metrics):
            label_widget = QLabel(label)
            value_widget = QLabel("0.00")
            value_widget.setStyleSheet("font-weight: bold;")
            totals_grid.addWidget(label_widget, index, 0)
            totals_grid.addWidget(value_widget, index, 1)
            self.dashboard_labels[key] = value_widget
        self.dashboard_labels["proposed"].setStyleSheet(f"font-weight: bold; color: {COLORS['warning']};")

        self.nature_table = QTableWidget()
        self.nature_table.setColumnCount(3)
        self.nature_table.setHorizontalHeaderLabels(["Nature", "Montant", "% DS"])
        self.nature_table.setRowCount(5)
        self.nature_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.nature_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.nature_table.setMaximumWidth(430)

        self.group_totals_tree = QTreeWidget()
        self.group_totals_tree.setHeaderLabels(["Regroupement", "DS total", "PV total"])
        self.group_totals_tree.setMaximumWidth(520)
        self.group_totals_tree.setMaximumHeight(185)

        layout.addWidget(totals_panel, 2)
        layout.addWidget(self.nature_table, 3)
        layout.addWidget(self.group_totals_tree, 3)
        return box

    def reload(self):
        self.viewing_version_id = None
        self._set_work_actions_enabled(True)
        self.rows = self.service.preparer_chiffrage_projet(self.projet.id)
        self.populate_table()

    def refresh_version_controls(self):
        if not hasattr(self, "version_combo"):
            return
        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        self.version_combo.addItem("Versions sauvegardées", None)
        for version in self.version_service.lister_versions(self.projet.id):
            label = version.nom + (" (courante)" if version.est_version_courante else "")
            self.version_combo.addItem(label, version.id)
        self.version_combo.blockSignals(False)

    def show_original_work(self):
        self.reload()
        self.refresh_version_controls()
        self.version_combo.setCurrentIndex(0)

    def on_version_combo_changed(self):
        if not hasattr(self, "version_combo") or self._updating:
            return
        version_id = self.version_combo.currentData()
        if version_id is None:
            if self.viewing_version_id is not None:
                self.show_original_work()
            return
        self.show_saved_version(version_id)

    def show_saved_version(self, version_id):
        base_rows = self.service.preparer_chiffrage_projet(self.projet.id)
        version_lines = self.version_service.repository.lignes_version(version_id)
        self.viewing_version_id = version_id
        self._set_work_actions_enabled(False)
        self.rows = []
        for row in base_rows:
            version_line = version_lines.get(row["id"])
            if version_line:
                row = {
                    **row,
                    "ds_mo": version_line["ds_mo"],
                    "ds_mat": version_line["ds_mat"],
                    "ds_materiel": version_line["ds_materiel"],
                    "ds_transport": version_line["ds_transport"],
                    "ds_st": version_line["ds_st"],
                    "ds_total": version_line["ds_total"],
                    "pv_unitaire": version_line["pv_unitaire"],
                    "pv_total": version_line["pv_total"],
                }
            self.rows.append(row)
        self.populate_table()

    def _set_work_actions_enabled(self, enabled):
        self.btn_auto_search.setEnabled(True)
        self.btn_auto_search_ai.setEnabled(True)
        for button in (self.btn_copy, self.btn_detail):
            button.setEnabled(enabled)

    def save_current_work_as_version(self):
        default_name = f"Version {len(self.version_service.lister_versions(self.projet.id)) + 1}"
        nom, ok = QInputDialog.getText(
            self,
            "Sauvegarder en version",
            "Nom de la version :",
            text=default_name,
        )
        if not ok:
            return
        try:
            version_id = self.version_service.creer_version(self.projet.id, nom)
            self.refresh_version_controls()
            self.version_combo.setCurrentIndex(0)
            QMessageBox.information(self, "Version sauvegardée", f"La version #{version_id} a été sauvegardée.")
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Sauvegarde de version impossible :\n{exc}")

    def open_versions_dialog(self):
        dialog = ComparaisonVersionsDialog(self.projet, self.version_service, self)
        selected_version_id = self.version_combo.currentData()
        if selected_version_id is not None:
            index = dialog.reference_combo.findData(str(selected_version_id))
            if index >= 0:
                dialog.reference_combo.setCurrentIndex(index)
        dialog.exec()
        self.refresh_version_controls()

    def populate_table(self):
        self._updating = True
        self.table.setRowCount(0)
        self.row_by_ouvrage_id.clear()
        self.group_rows.clear()
        current_lot = None
        current_sous_lot = None
        for ouvrage in self.rows:
            lot_key = ouvrage["lot_id"]
            sous_lot_key = ouvrage["sous_lot_id"]
            if lot_key != current_lot:
                current_lot = lot_key
                current_sous_lot = None
                self._add_group_row("lot", lot_key, f"Lot - {ouvrage['lot_code']} {ouvrage['lot_libelle']}")
            if sous_lot_key != current_sous_lot:
                current_sous_lot = sous_lot_key
                self._add_group_row("sous_lot", sous_lot_key, f"Sous-lot - {ouvrage['sous_lot_code']} {ouvrage['sous_lot_libelle']}")
            self._add_ouvrage_row(ouvrage)
        self._add_group_row("projet", self.projet.id, "Total projet")
        self.recalculate_totals()
        self.update_mapping_progress()
        self._updating = False
        self._focus_requested_section()

    def _add_group_row(self, group_type, group_id, label):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.group_rows[(group_type, group_id)] = row
        item = QTableWidgetItem(f"- {label}")
        item.setData(Qt.UserRole, {"row_type": group_type, "id": group_id, "collapsed": False})
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setBackground(QColor(COLORS["surface_alt"]))
        self.table.setItem(row, 0, item)
        for col in range(1, len(self.columns)):
            empty = QTableWidgetItem("")
            empty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            empty.setBackground(QColor(COLORS["surface_alt"]))
            self.table.setItem(row, col, empty)

    def _add_ouvrage_row(self, ouvrage):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.row_by_ouvrage_id[ouvrage["id"]] = row
        values = [
            ouvrage["code"],
            ouvrage["designation"],
            ouvrage["unite"],
            self._decimal_text(ouvrage["quantite"]),
            self._money_text(ouvrage["ds_mo"]),
            self._money_text(ouvrage["ds_mat"]),
            self._money_text(ouvrage["ds_materiel"]),
            self._money_text(ouvrage["ds_transport"]),
            self._money_text(ouvrage["ds_st"]),
            self._money_text(ouvrage["ds_total"]),
            self._coefficient_text(ouvrage),
            self._money_text(ouvrage["pv_unitaire"]),
            self._money_text(ouvrage["pv_total"]),
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.UserRole, {"row_type": "ouvrage", "ouvrage_id": ouvrage["id"], "section_id": ouvrage.get("section_id")})
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if col in self.EDITABLE_KEYS:
                flags |= Qt.ItemIsEditable
            item.setFlags(flags)
            self.table.setItem(row, col, item)
        if self.mapping_enabled:
            self._add_mapping_cells(row, ouvrage)

    def _add_mapping_cells(self, row, ouvrage):
        status = self.correspondance_service.statut_ouvrage(ouvrage["section_id"]) if ouvrage.get("section_id") else "Aucune"
        status_item = QTableWidgetItem(status)
        status_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        status_item.setBackground(QColor({
            "Aucune": COLORS["danger"],
            "Proposée": COLORS["warning"],
            "Validée": COLORS["success"],
        }.get(status, COLORS["border"])))
        self.table.setItem(row, self.mapping_col_status, status_item)

        proposal_combo = QComboBox()
        proposal_combo.setObjectName(f"proposal_combo_{ouvrage['id']}")
        proposals = self.correspondance_service.correspondances_pour_ouvrage(ouvrage["section_id"]) if ouvrage.get("section_id") else []
        proposal_combo.addItem("Aucune proposition", None)
        for proposal in proposals:
            label = f"{float(proposal['score']):.1f} | {proposal['code'] or ''} | {proposal['designation'] or ''} | {proposal['bibliotheque_nom'] or ''}"
            proposal_combo.addItem(label, proposal["id"])
            if proposal["statut"] == "validee":
                proposal_combo.setCurrentIndex(proposal_combo.count() - 1)
        proposal_combo.setProperty("previous_data", proposal_combo.currentData())
        proposal_combo.currentIndexChanged.connect(
            lambda _index, oid=ouvrage["id"]: self.on_mapping_proposal_combo_changed(oid)
        )
        self.table.setCellWidget(row, self.mapping_col_proposals, proposal_combo)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        btn_validate = QPushButton("Valider")
        btn_validate.clicked.connect(lambda _=False, oid=ouvrage["id"]: self.validate_selected_proposal_for_ouvrage(oid))
        btn_manual = QPushButton("Manuel")
        btn_manual.clicked.connect(lambda _=False, oid=ouvrage["id"]: self.manual_search_for_ouvrage(oid))
        btn_create = QPushButton("Créer")
        btn_create.clicked.connect(lambda _=False, oid=ouvrage["id"]: self.create_ouvrage_for_ouvrage(oid))
        actions_layout.addWidget(btn_validate)
        actions_layout.addWidget(btn_manual)
        actions_layout.addWidget(btn_create)
        actions.setEnabled(self.viewing_version_id is None)
        self.table.setCellWidget(row, self.mapping_col_actions, actions)

    def on_mapping_proposal_combo_changed(self, ouvrage_id):
        if self._updating:
            return
        ouvrage = self._ouvrage_by_id(ouvrage_id)
        if not ouvrage or not ouvrage.get("section_id"):
            return
        row = self.row_by_ouvrage_id.get(ouvrage_id)
        combo = self.table.cellWidget(row, self.mapping_col_proposals) if row is not None else None
        if not combo:
            return
        current_data = combo.currentData()
        if current_data is not None:
            previous_data = combo.property("previous_data")
            if previous_data == current_data and self.correspondance_service.statut_ouvrage(ouvrage["section_id"]) == "Validée":
                return
            reply = QMessageBox.question(
                self,
                "Valider la proposition",
                "Tu veux valider cette proposition pour cette ligne ? Les valeurs seront copiées dans le chiffrage courant.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                previous_index = combo.findData(previous_data)
                combo.blockSignals(True)
                combo.setCurrentIndex(previous_index if previous_index >= 0 else 0)
                combo.blockSignals(False)
                return
            try:
                self.correspondance_service.associer_resultat_pour_ouvrage(ouvrage["section_id"], current_data)
                if self.viewing_version_id is not None:
                    updated = self._copier_proposition_dans_version(ouvrage, current_data)
                else:
                    updated = self.service.copier_depuis_bibliotheque(ouvrage["section_id"])
                self._replace_row_data({**ouvrage, **updated})
                self._refresh_ouvrage_row(row, {**ouvrage, **updated})
                self._refresh_mapping_cells(row, {**ouvrage, **updated})
                self.recalculate_totals()
            except Exception as exc:
                QMessageBox.critical(self, "Erreur", f"Validation impossible :\n{exc}")
            return

        was_validated = self.correspondance_service.statut_ouvrage(ouvrage["section_id"]) == "Validée"
        if was_validated:
            reply = QMessageBox.question(
                self,
                "Annuler la validation",
                "Tu es sûr d'annuler la validation ? Les montants copiés de cette correspondance seront retirés du chiffrage courant.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                previous_data = combo.property("previous_data")
                previous_index = combo.findData(previous_data)
                combo.blockSignals(True)
                combo.setCurrentIndex(previous_index if previous_index >= 0 else 0)
                combo.blockSignals(False)
                return
        try:
            self.correspondance_service.supprimer_correspondances_ouvrage(ouvrage["section_id"])
            if self.viewing_version_id is not None:
                updated = self.version_service.sauvegarder_composants_ligne_version(
                    self.viewing_version_id,
                    ouvrage_id,
                    Decimal("0"),
                    Decimal("0"),
                    Decimal("0"),
                    Decimal("0"),
                    Decimal("0"),
                )
                updated = {"id": ouvrage_id, **updated}
            else:
                updated = self.service.sauvegarder_composants_ouvrage(
                    ouvrage_id,
                    Decimal("0"),
                    Decimal("0"),
                    Decimal("0"),
                    Decimal("0"),
                    Decimal("0"),
                )
            self._replace_row_data({**ouvrage, **updated})
            self._refresh_ouvrage_row(row, {**ouvrage, **updated})
            self._refresh_mapping_cells(row, {**ouvrage, **updated})
            self.recalculate_totals()
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Modification de proposition impossible :\n{exc}")

    def _copier_proposition_dans_version(self, ouvrage, correspondance_id):
        proposition = next(
            (item for item in self.correspondance_service.correspondances_pour_ouvrage(ouvrage["section_id"]) if item["id"] == correspondance_id),
            None,
        )
        if not proposition:
            raise ValueError("Proposition introuvable.")
        quantite = Decimal(str(ouvrage.get("quantite") or 1))
        ds_mo = Decimal(str(proposition.get("mo_ht_import") or 0)) * quantite
        ds_mat = Decimal(str(proposition.get("fournitures_ht_import") or 0)) * quantite
        ds_materiel = Decimal(str(proposition.get("materiel_ht_import") or 0)) * quantite
        ds_transport = Decimal(str(proposition.get("transport_ht_import") or 0)) * quantite
        ds_st = Decimal(str(proposition.get("sous_traitance_ht_import") or 0)) * quantite
        ds_total = Decimal(str(proposition.get("debourse_sec_import") or (ds_mo + ds_mat + ds_materiel + ds_transport + ds_st))) * quantite
        pv_unitaire = Decimal(str(proposition.get("pv_eg_ht_import") or 0))
        pv_total = pv_unitaire * quantite
        values = {
            "ds_mo": ds_mo,
            "ds_mat": ds_mat,
            "ds_materiel": ds_materiel,
            "ds_transport": ds_transport,
            "ds_st": ds_st,
            "ds_total": ds_total,
            "pv_unitaire": pv_unitaire,
            "pv_total": pv_total,
        }
        updated = self.version_service.sauvegarder_ligne_version(self.viewing_version_id, ouvrage["id"], values)
        return {"id": ouvrage["id"], **updated}

    def on_item_double_clicked(self, item):
        meta = item.data(Qt.UserRole) or {}
        if meta.get("row_type") in {"lot", "sous_lot"}:
            self.toggle_group(item.row())

    def toggle_group(self, row):
        meta = self.table.item(row, 0).data(Qt.UserRole)
        group_type = meta["row_type"]
        group_id = meta["id"]
        collapsed = not meta.get("collapsed", False)
        meta["collapsed"] = collapsed
        label = self.table.item(row, 0).text()
        self.table.item(row, 0).setText(("+ " if collapsed else "- ") + label[2:])
        if group_type == "lot":
            affected = [r for r in self.rows if r["lot_id"] == group_id]
            sous_lots = {r["sous_lot_id"] for r in affected}
            hide_rows = [self.group_rows[("sous_lot", sid)] for sid in sous_lots if ("sous_lot", sid) in self.group_rows]
            hide_rows += [self.row_by_ouvrage_id[r["id"]] for r in affected]
        else:
            affected = [r for r in self.rows if r["sous_lot_id"] == group_id]
            hide_rows = [self.row_by_ouvrage_id[r["id"]] for r in affected]
        for hide_row in hide_rows:
            self.table.setRowHidden(hide_row, collapsed)

    def on_item_changed(self, item):
        if self._updating or item.column() not in self.EDITABLE_KEYS:
            return
        meta = item.data(Qt.UserRole) or {}
        if meta.get("row_type") != "ouvrage":
            return
        try:
            value = Decimal(str(item.text()).replace(",", "."))
            if value < 0:
                raise ValueError
        except Exception:
            self._restore_row(meta["ouvrage_id"])
            return
        row = item.row()
        values = {}
        for col, key in self.EDITABLE_KEYS.items():
            values[key] = Decimal(str(self.table.item(row, col).text()).replace(",", "."))
        if self.viewing_version_id is not None:
            updated = self.version_service.sauvegarder_composants_ligne_version(
                self.viewing_version_id,
                meta["ouvrage_id"],
                values["ds_mo"],
                values["ds_mat"],
                values["ds_materiel"],
                values["ds_transport"],
                values["ds_st"],
            )
            updated = {"id": meta["ouvrage_id"], **updated}
        else:
            updated = self.service.sauvegarder_composants_ouvrage(
                meta["ouvrage_id"],
                values["ds_mo"],
                values["ds_mat"],
                values["ds_materiel"],
                values["ds_transport"],
                values["ds_st"],
            )
        self._replace_row_data(updated)
        self._refresh_ouvrage_row(row, updated)
        self.recalculate_totals()

    def recalculate_totals(self):
        for key, row in self.group_rows.items():
            group_type, group_id = key
            if group_type == "lot":
                members = [r for r in self.rows if r["lot_id"] == group_id]
            elif group_type == "sous_lot":
                members = [r for r in self.rows if r["sous_lot_id"] == group_id]
            else:
                members = self.rows
            ds_total = sum((r["ds_total"] for r in members), Decimal("0"))
            pv_total = sum((r["pv_total"] for r in members), Decimal("0"))
            self._set_readonly_text(row, 9, self._money_text(ds_total))
            self._set_readonly_text(row, 12, self._money_text(pv_total))
        self.update_dashboard()
        self.update_mapping_progress()

    def update_dashboard(self):
        if not hasattr(self, "dashboard_labels"):
            return
        total_rows = len([row for row in self.rows if row.get("section_id")])
        dashboard_rows = []
        validated = 0
        proposed = 0
        manual = 0
        if self.mapping_enabled:
            for row in self.rows:
                section_id = row.get("section_id")
                if not section_id:
                    continue
                status = self.correspondance_service.statut_ouvrage(section_id)
                if status == "Validée":
                    validated += 1
                    dashboard_rows.append(row)
                elif status == "Proposée":
                    proposed += 1
                elif Decimal(str(row.get("ds_total") or 0)) > 0:
                    manual += 1
        else:
            dashboard_rows = [row for row in self.rows if row.get("section_id")]
            manual = len([row for row in dashboard_rows if Decimal(str(row.get("ds_total") or 0)) > 0])
        priced_rows = validated if self.mapping_enabled or self.viewing_version_id is not None else manual
        untreated = max(total_rows - validated - proposed - manual, 0)
        ds_total = sum((row["ds_total"] for row in dashboard_rows), Decimal("0"))
        pv_total = sum((row["pv_total"] for row in dashboard_rows), Decimal("0"))
        margin = pv_total - ds_total
        margin_percent = (margin / pv_total * Decimal("100")) if pv_total else Decimal("0")

        self.dashboard_labels["ds_total"].setText(f"{self._money_text(ds_total)} €")
        self.dashboard_labels["pv_total"].setText(f"{self._money_text(pv_total)} €")
        self.dashboard_labels["progress"].setText(f"{priced_rows} / {total_rows}")
        self.dashboard_labels["margin"].setText(f"{self._money_text(margin)} € / {self._percent_text(margin_percent)}")
        self.dashboard_labels["validated"].setText(str(validated))
        self.dashboard_labels["proposed"].setText(str(proposed))
        self.dashboard_labels["manual"].setText(str(manual))
        self.dashboard_labels["untreated"].setText(str(untreated))
        self._update_nature_dashboard(ds_total, dashboard_rows)
        self._update_group_dashboard(dashboard_rows)

    def _update_nature_dashboard(self, ds_total, dashboard_rows):
        components = [
            ("Main d'oeuvre", "ds_mo"),
            ("Matériaux", "ds_mat"),
            ("Matériel", "ds_materiel"),
            ("Transport", "ds_transport"),
            ("Sous-traitance", "ds_st"),
        ]
        for row_index, (label, key) in enumerate(components):
            amount = sum((row[key] for row in dashboard_rows), Decimal("0"))
            percent = (amount / ds_total * Decimal("100")) if ds_total else Decimal("0")
            values = [label, f"{self._money_text(amount)} €", self._percent_text(percent)]
            for col, value in enumerate(values):
                item = self.nature_table.item(row_index, col)
                if item is None:
                    item = QTableWidgetItem()
                    self.nature_table.setItem(row_index, col, item)
                item.setText(value)

    def _update_group_dashboard(self, dashboard_rows):
        self.group_totals_tree.clear()
        lots = []
        for row in self.rows:
            if row["lot_id"] not in [lot["id"] for lot in lots]:
                lots.append({
                    "id": row["lot_id"],
                    "label": f"{row['lot_code']} {row['lot_libelle']}",
                })
        for lot in lots:
            lot_rows = [row for row in dashboard_rows if row["lot_id"] == lot["id"]]
            lot_item = QTreeWidgetItem([
                f"Lot - {lot['label']}",
                f"{self._money_text(sum((row['ds_total'] for row in lot_rows), Decimal('0')))} €",
                f"{self._money_text(sum((row['pv_total'] for row in lot_rows), Decimal('0')))} €",
            ])
            self.group_totals_tree.addTopLevelItem(lot_item)
            sous_lots = []
            all_lot_rows = [row for row in self.rows if row["lot_id"] == lot["id"]]
            for row in all_lot_rows:
                if row["sous_lot_id"] not in [sous_lot["id"] for sous_lot in sous_lots]:
                    sous_lots.append({
                        "id": row["sous_lot_id"],
                        "label": f"{row['sous_lot_code']} {row['sous_lot_libelle']}",
                    })
            for sous_lot in sous_lots:
                sous_lot_rows = [row for row in lot_rows if row["sous_lot_id"] == sous_lot["id"]]
                lot_item.addChild(QTreeWidgetItem([
                    f"Sous-lot - {sous_lot['label']}",
                    f"{self._money_text(sum((row['ds_total'] for row in sous_lot_rows), Decimal('0')))} €",
                    f"{self._money_text(sum((row['pv_total'] for row in sous_lot_rows), Decimal('0')))} €",
                ]))

    def update_mapping_progress(self):
        if self.viewing_version_id is not None:
            self.progress_label.setText("Version sauvegardée affichée")
            return
        if not self.mapping_enabled:
            self.progress_label.setText("")
            return
        total = len([row for row in self.rows if row.get("section_id")])
        treated = 0
        for row in self.rows:
            section_id = row.get("section_id")
            if not section_id:
                continue
            status = self.correspondance_service.statut_ouvrage(section_id)
            if status == "Validée" or (status == "Aucune" and self._has_manual_complete_chiffrage(row)):
                treated += 1
        self.progress_label.setText(f"{treated}/{total} lignes reliées")
        self.maybe_prompt_original_version(treated, total)

    def _has_manual_complete_chiffrage(self, row):
        return row.get("section_id") and Decimal(str(row.get("ds_total") or 0)) > 0

    def maybe_prompt_original_version(self, treated: int, total: int):
        if not self.mapping_enabled or total == 0 or treated < total or self.original_version_prompt_shown:
            return
        self.original_version_prompt_shown = True
        self.prompt_original_version_creation()

    def prompt_original_version_creation(self):
        message = QMessageBox(self)
        message.setWindowTitle("Version originale")
        message.setText("Toutes les lignes sont chiffrées. Créer la version originale ?")
        create_button = message.addButton("Créer la version originale", QMessageBox.AcceptRole)
        message.addButton(QMessageBox.Cancel)
        message.exec()
        if message.clickedButton() != create_button:
            return
        nom, ok = QInputDialog.getText(
            self,
            "Créer la version originale",
            "Nom de la version :",
            text="Version originale",
        )
        if not ok:
            return
        try:
            self.create_original_version(nom)
            QMessageBox.information(self, "Version créée", f"La version '{nom}' a été créée.")
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Création de version impossible :\n{exc}")

    def create_original_version(self, nom: str = "Version originale"):
        return self.version_service.creer_version(self.projet.id, nom)

    def _has_original_version(self) -> bool:
        return any(version.nom == "Version originale" for version in self.version_service.lister_versions(self.projet.id))

    def validate_selected_proposal_for_ouvrage(self, ouvrage_id):
        ouvrage = self._ouvrage_by_id(ouvrage_id)
        if not ouvrage:
            return
        row = self.row_by_ouvrage_id.get(ouvrage_id)
        combo = self.table.cellWidget(row, self.mapping_col_proposals) if row is not None else None
        corr_id = combo.currentData() if combo else None
        if not corr_id:
            QMessageBox.information(self, "Validation", "Sélectionnez une proposition pour cette ligne.")
            return
        self.correspondance_service.associer_resultat_pour_ouvrage(ouvrage["section_id"], corr_id)
        updated = self.service.copier_depuis_bibliotheque(ouvrage["section_id"])
        self._replace_row_data({**ouvrage, **updated})
        self._refresh_ouvrage_row(row, {**ouvrage, **updated})
        self._refresh_mapping_cells(row, {**ouvrage, **updated})
        self.recalculate_totals()

    def manual_search_for_ouvrage(self, ouvrage_id):
        ouvrage = self._ouvrage_by_id(ouvrage_id)
        if not ouvrage:
            return
        dialog = CatalogueSearchDialog(self.correspondance_service, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_ouvrage_id:
            self.correspondance_service.associer_manuellement(ouvrage["section_id"], dialog.selected_ouvrage_id)
            updated = self.service.copier_depuis_bibliotheque(ouvrage["section_id"])
            row = self.row_by_ouvrage_id.get(ouvrage_id)
            self._replace_row_data({**ouvrage, **updated})
            self._refresh_ouvrage_row(row, {**ouvrage, **updated})
            self._refresh_mapping_cells(row, {**ouvrage, **updated})
            self.recalculate_totals()

    def create_ouvrage_for_ouvrage(self, ouvrage_id):
        ouvrage = self._ouvrage_by_id(ouvrage_id)
        if not ouvrage:
            return
        section = self.service.section_repo.get_by_id(ouvrage["section_id"])
        dialog = QuickOuvrageCreateDialog(self.db_manager, section, self)
        if dialog.exec() == QDialog.Accepted and dialog.created_ouvrage_id:
            self.correspondance_service.associer_manuellement(ouvrage["section_id"], dialog.created_ouvrage_id)
            updated = self.service.copier_depuis_bibliotheque(ouvrage["section_id"])
            row = self.row_by_ouvrage_id.get(ouvrage_id)
            self._replace_row_data({**ouvrage, **updated})
            self._refresh_ouvrage_row(row, {**ouvrage, **updated})
            self._refresh_mapping_cells(row, {**ouvrage, **updated})
            self.recalculate_totals()

    def search_auto_for_all_missing(self):
        if not self.mapping_enabled:
            return
        selected_version_id = self.viewing_version_id
        for ouvrage in self.rows:
            section_id = ouvrage.get("section_id")
            if section_id and self.correspondance_service.statut_ouvrage(section_id) != "Validée":
                self.correspondance_service.rechercher(section_id, enregistrer=True)
        if selected_version_id is not None:
            self.show_saved_version(selected_version_id)
        else:
            self.rows = self.service.lister_ouvrages_projet(self.projet.id)
            self.populate_table()

    def search_ai_for_all_missing(self):
        if not self.mapping_enabled:
            return
        if self.ai_matching_thread and self.ai_matching_thread.isRunning():
            return
        scope = self._ask_ai_scope()
        if scope is None:
            return
        self.progress_label.setText("Recherche IA en cours...")
        self.btn_auto_search_ai.setEnabled(False)
        self.ai_matching_thread = QThread(self)
        self.ai_matching_worker = MatchingWorker(
            self.db_manager.db_path,
            self.db_manager.migrations_dir,
            self.projet.id,
            scope,
            "ia",
        )
        self.ai_matching_worker.moveToThread(self.ai_matching_thread)
        self.ai_matching_thread.started.connect(self.ai_matching_worker.run)
        self.ai_matching_worker.progression.connect(self.on_ai_matching_progress)
        self.ai_matching_worker.succes.connect(self.on_ai_matching_success)
        self.ai_matching_worker.erreur.connect(self.on_ai_matching_error)
        self.ai_matching_worker.termine.connect(self.ai_matching_thread.quit)
        self.ai_matching_worker.termine.connect(self.ai_matching_worker.deleteLater)
        self.ai_matching_thread.finished.connect(self.ai_matching_thread.deleteLater)
        self.ai_matching_thread.finished.connect(self.on_ai_matching_finished)
        self.ai_matching_thread.start()

    def _ask_ai_scope(self):
        box = QMessageBox(self)
        box.setWindowTitle("Recherche auto avec IA")
        box.setText("Où rechercher les correspondances IA ?")
        active_button = box.addButton("Bibliothèques actives du projet", QMessageBox.AcceptRole)
        all_button = box.addButton("Toutes les bibliothèques", QMessageBox.DestructiveRole)
        box.addButton("Annuler", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == active_button:
            return False
        if clicked == all_button:
            return True
        return None

    @Slot(int, int, str)
    def on_ai_matching_progress(self, current, total, message):
        self.progress_label.setText(f"IA : {message}")

    @Slot(object)
    def on_ai_matching_success(self, result):
        QMessageBox.information(
            self,
            "Recherche IA terminée",
            f"{result.traites}/{result.total} lignes traitées.\n"
            f"{result.propositions} propositions IA créées ou mises à jour.",
        )
        selected_version_id = self.viewing_version_id
        if selected_version_id is not None:
            self.show_saved_version(selected_version_id)
        else:
            self.rows = self.service.lister_ouvrages_projet(self.projet.id)
            self.populate_table()

    @Slot(str)
    def on_ai_matching_error(self, message):
        QMessageBox.critical(self, "Recherche IA impossible", message)

    @Slot()
    def on_ai_matching_finished(self):
        self.btn_auto_search_ai.setEnabled(True)
        self.progress_label.setText("")
        self.ai_matching_worker = None
        self.ai_matching_thread = None

    def _refresh_mapping_cells(self, row, ouvrage):
        if self.mapping_enabled and row is not None:
            self._add_mapping_cells(row, ouvrage)

    def copy_selected_from_library(self):
        section_ids = self._selected_section_ids()
        if not section_ids:
            QMessageBox.information(self, "Copie bibliothèque", "Sélectionnez au moins une ligne chiffrable.")
            return
        result = self.service.copier_depuis_bibliotheque_plusieurs(section_ids)
        self.rows = self.service.lister_ouvrages_projet(self.projet.id)
        for ouvrage in self.rows:
            row = self.row_by_ouvrage_id.get(ouvrage["id"])
            if row is not None:
                self._refresh_ouvrage_row(row, ouvrage)
        self.recalculate_totals()
        QMessageBox.information(
            self,
            "Copie bibliothèque",
            f"{result['copiees']} ligne(s) copiée(s), {result['ignorees']} ignorée(s).",
        )

    def open_selected_detail(self):
        selected = self._selected_ouvrage_rows()
        if not selected:
            return
        ouvrage = selected[0]
        section_id = ouvrage.get("section_id")
        if section_id:
            ChiffrageLigneDialog(self.service.section_repo.get_by_id(section_id), self.service, self).exec()
            self.rows = self.service.lister_ouvrages_projet(self.projet.id)
            self.populate_table()

    def _selected_ouvrage_rows(self):
        rows = sorted({item.row() for item in self.table.selectedItems()})
        ouvrages = []
        by_id = {r["id"]: r for r in self.rows}
        for row in rows:
            item = self.table.item(row, 0)
            meta = item.data(Qt.UserRole) if item else {}
            if meta and meta.get("row_type") == "ouvrage":
                ouvrages.append(by_id[meta["ouvrage_id"]])
        return ouvrages

    def _selected_section_ids(self):
        return [ouvrage["section_id"] for ouvrage in self._selected_ouvrage_rows() if ouvrage.get("section_id")]

    def _ouvrage_by_id(self, ouvrage_id):
        return next((row for row in self.rows if row["id"] == ouvrage_id), None)

    def _replace_row_data(self, updated):
        for index, ouvrage in enumerate(self.rows):
            if ouvrage["id"] == updated["id"]:
                self.rows[index] = {**ouvrage, **updated}
                return

    def _refresh_ouvrage_row(self, row, ouvrage):
        self._updating = True
        values = {
            4: self._money_text(ouvrage["ds_mo"]),
            5: self._money_text(ouvrage["ds_mat"]),
            6: self._money_text(ouvrage["ds_materiel"]),
            7: self._money_text(ouvrage["ds_transport"]),
            8: self._money_text(ouvrage["ds_st"]),
            9: self._money_text(ouvrage["ds_total"]),
            10: self._coefficient_text(ouvrage),
            11: self._money_text(ouvrage["pv_unitaire"]),
            12: self._money_text(ouvrage["pv_total"]),
        }
        for col, value in values.items():
            self.table.item(row, col).setText(value)
        self._updating = False

    def _restore_row(self, ouvrage_id):
        ouvrage = next((r for r in self.rows if r["id"] == ouvrage_id), None)
        row = self.row_by_ouvrage_id.get(ouvrage_id)
        if ouvrage and row is not None:
            self._refresh_ouvrage_row(row, ouvrage)

    def _set_readonly_text(self, row, col, text):
        item = self.table.item(row, col)
        if item:
            item.setText(text)

    def _focus_requested_section(self):
        if not self.focus_section_id:
            return
        for ouvrage in self.rows:
            if ouvrage.get("section_id") == self.focus_section_id:
                row = self.row_by_ouvrage_id.get(ouvrage["id"])
                if row is not None:
                    self.table.selectRow(row)
                    self.table.scrollToItem(self.table.item(row, 0))
                return

    def _coefficient_text(self, ouvrage):
        ds_total = ouvrage["ds_total"]
        if not ds_total:
            return str(DEFAULT_COEFFICIENT_VENTE)
        return str((ouvrage["pv_total"] / ds_total).quantize(Decimal("0.0001")))

    def _money_text(self, value):
        return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))

    def _percent_text(self, value):
        return f"{Decimal(str(value or 0)).quantize(Decimal('0.01'))} %"

    def _decimal_text(self, value):
        return str(value if value is not None else "")


class MappingPageDialog(QDialog):
    PAGE_SIZE = 80

    def __init__(self, projet, sections, correspondance_service: CorrespondanceService, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.sections = sections
        self.service = correspondance_service
        self.section_by_id = {section.id: section for section in sections}
        self.selected_by_section = {}
        self.render_limit = self.PAGE_SIZE
        self.matching_thread = None
        self.matching_worker = None
        self.setWindowTitle(f"Mapping - {projet.nom}")
        self.resize(1500, 900)
        self.setStyleSheet(APP_STYLESHEET)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("Mapping DPGF ↔ Bibliothèques")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Toutes", "Aucune", "Proposée", "Validée"])
        self.status_filter.currentTextChanged.connect(self.refresh_blocks)
        self.lot_filter = QComboBox()
        self.lot_filter.currentTextChanged.connect(self.refresh_blocks)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher une désignation DPGF...")
        self.search_input.textChanged.connect(self.refresh_blocks)
        self.btn_bulk_validate = QPushButton("Valider les correspondances sélectionnées")
        self.btn_bulk_validate.clicked.connect(self.validate_selected)
        self.btn_run_auto = QPushButton("Lancer / relancer le rapprochement automatique")
        self.btn_run_auto.clicked.connect(self.run_auto_matching)
        self.btn_run_ai = QPushButton("Recherche auto avec IA")
        self.btn_run_ai.clicked.connect(self.run_ai_matching)
        self.expand_mapping_checkbox = QCheckBox("Toutes bibliothèques")
        header.addWidget(title)
        header.addWidget(QLabel("Statut"))
        header.addWidget(self.status_filter)
        header.addWidget(QLabel("Lot"))
        header.addWidget(self.lot_filter)
        header.addWidget(self.search_input, 1)
        header.addWidget(self.expand_mapping_checkbox)
        header.addWidget(self.btn_run_auto)
        header.addWidget(self.btn_run_ai)
        header.addWidget(self.btn_bulk_validate)

        progress_layout = QHBoxLayout()
        self.matching_progress = QProgressBar()
        self.matching_progress.setVisible(False)
        self.matching_progress.setMinimum(0)
        self.matching_progress.setValue(0)
        self.matching_status = QLabel("")
        self.matching_status.setVisible(False)
        self.btn_cancel_matching = QPushButton("Annuler")
        self.btn_cancel_matching.setVisible(False)
        self.btn_cancel_matching.clicked.connect(self.cancel_auto_matching)
        progress_layout.addWidget(self.matching_progress, 1)
        progress_layout.addWidget(self.matching_status)
        progress_layout.addWidget(self.btn_cancel_matching)

        self.empty_label = QLabel("")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.scroll.setWidget(self.content)
        self.btn_load_more = QPushButton("Charger plus")
        self.btn_load_more.clicked.connect(self.load_more)

        layout.addLayout(header)
        layout.addLayout(progress_layout)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.btn_load_more)
        self.refresh_lots()
        self.refresh_blocks()

    def refresh_lots(self):
        lots = ["Tous"] + sorted({self.lot_label(section) for section in self.ouvrage_sections()})
        current = self.lot_filter.currentText()
        self.lot_filter.blockSignals(True)
        self.lot_filter.clear()
        self.lot_filter.addItems(lots)
        if current in lots:
            self.lot_filter.setCurrentText(current)
        self.lot_filter.blockSignals(False)

    def ouvrage_sections(self):
        return [section for section in self.sections if section.type_ligne in ("ouvrage", "pour_memoire")]

    def lot_label(self, section):
        current = section
        while current.parent_id and current.parent_id in self.section_by_id:
            current = self.section_by_id[current.parent_id]
        return current.libelle

    def chapitre_label(self, section):
        current = section
        parent = self.section_by_id.get(current.parent_id)
        while parent and parent.parent_id and parent.parent_id in self.section_by_id:
            current = parent
            parent = self.section_by_id.get(parent.parent_id)
        return current.libelle if current.id != section.id else ""

    def filtered_sections(self):
        status = self.status_filter.currentText()
        lot = self.lot_filter.currentText()
        search = self.search_input.text().strip().lower()
        result = []
        for section in self.ouvrage_sections():
            if status != "Toutes" and self.service.statut_ouvrage(section.id) != status:
                continue
            if lot and lot != "Tous" and self.lot_label(section) != lot:
                continue
            if search and search not in f"{section.numero_article or ''} {section.libelle}".lower():
                continue
            result.append(section)
        return result

    def refresh_blocks(self):
        self.clear_blocks()
        sections = self.filtered_sections()
        has_any_proposal = any(self.service.correspondances_pour_ouvrage(section.id) for section in self.ouvrage_sections())
        has_visible_sections = bool(sections)
        self.empty_label.setVisible(not has_any_proposal or not has_visible_sections)
        if not has_any_proposal:
            self.empty_label.setText("Aucune proposition n'existe encore pour ce projet.")
        elif not has_visible_sections:
            self.empty_label.setText("Aucune ligne DPGF ne correspond aux filtres.")
        else:
            self.empty_label.setText("")

        visible = sections[:self.render_limit]
        previous_group = None
        for section in visible:
            group = (self.lot_label(section), self.chapitre_label(section))
            if group != previous_group:
                label = QLabel(" / ".join(part for part in group if part))
                label.setStyleSheet(band_style())
                self.content_layout.addWidget(label)
                previous_group = group
            self.content_layout.addWidget(self.build_block(section))
        self.content_layout.addStretch()
        self.btn_load_more.setVisible(len(sections) > self.render_limit)

    def clear_blocks(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def build_block(self, section):
        block = QFrame()
        block.setFrameShape(QFrame.StyledPanel)
        block.setStyleSheet("QFrame { border: 1px solid #555; margin: 4px; padding: 6px; }")
        layout = QVBoxLayout(block)
        status = self.service.statut_ouvrage(section.id)
        validated = next((c for c in self.service.correspondances_pour_ouvrage(section.id) if c["statut"] == "validee"), None)
        top = QHBoxLayout()
        status_label = QLabel(status)
        status_label.setStyleSheet(status_style(status))
        top.addWidget(QLabel(f"{section.numero_article or ''} - {section.libelle}"))
        top.addWidget(QLabel(f"U: {section.unite or ''}"))
        top.addWidget(QLabel(f"Qté: {self.decimal_text(section.quantite)}"))
        top.addWidget(status_label)
        if validated:
            valid_label = QLabel(f"Validée: {validated['code']} - {validated['designation']}")
            valid_label.setStyleSheet("font-weight: bold; color: #1b7f3a;")
            top.addWidget(valid_label)
        top.addStretch()
        layout.addLayout(top)

        proposals = self.service.correspondances_pour_ouvrage(section.id)[:10]
        if not proposals:
            layout.addWidget(QLabel("Aucune proposition calculée."))
        proposal_group = QButtonGroup(block)
        proposal_group.setExclusive(True)
        block.proposal_group = proposal_group
        for proposal in proposals:
            row = QHBoxLayout()
            radio = QRadioButton(block)
            radio.setObjectName(f"proposal_radio_{section.id}_{proposal['id']}")
            radio.setChecked(self.selected_by_section.get(section.id) == proposal["id"])
            proposal_group.addButton(radio, proposal["id"])
            radio.toggled.connect(lambda checked, sid=section.id, cid=proposal["id"]: self.on_choice_toggled(checked, sid, cid))
            row.addWidget(radio)
            row.addWidget(QLabel(f"{float(proposal['score']):.1f}"))
            row.addWidget(QLabel(proposal["code"] or ""))
            row.addWidget(QLabel(proposal["designation"] or ""), 2)
            row.addWidget(QLabel(proposal["famille"] or ""))
            row.addWidget(QLabel(proposal["unite"] or ""))
            row.addWidget(QLabel(self.decimal_text(proposal["debourse_sec_import"])))
            row.addWidget(QLabel(self.decimal_text(proposal["pv_eg_ht_import"])))
            row.addWidget(QLabel(proposal["bibliotheque_nom"] or ""))
            btn_detail = QPushButton("Voir le détail")
            btn_detail.clicked.connect(lambda _=False, p=proposal: OuvrageBibliothequeDetailDialog(p, self).exec())
            row.addWidget(btn_detail)
            layout.addLayout(row)
        actions = QHBoxLayout()
        btn_search = QPushButton("Rechercher")
        btn_search.clicked.connect(lambda _=False, sid=section.id: self.search_one(sid, False))
        btn_search_all = QPushButton("Rechercher toutes bibliothèques")
        btn_search_all.clicked.connect(lambda _=False, sid=section.id: self.search_one(sid, True))
        btn_validate = QPushButton("Valider")
        btn_validate.setEnabled(section.id in self.selected_by_section)
        btn_validate.clicked.connect(lambda _=False, sid=section.id: self.validate_one(sid))
        btn_manual = QPushButton("Rechercher manuellement dans le catalogue")
        btn_manual.clicked.connect(lambda _=False, sid=section.id: self.manual_search(sid))
        actions.addWidget(btn_search)
        actions.addWidget(btn_search_all)
        actions.addWidget(btn_validate)
        actions.addWidget(btn_manual)
        actions.addStretch()
        layout.addLayout(actions)
        return block

    def on_choice_toggled(self, checked, section_id, correspondance_id):
        if checked:
            self.selected_by_section[section_id] = correspondance_id
        elif self.selected_by_section.get(section_id) == correspondance_id:
            self.selected_by_section.pop(section_id, None)
        self.refresh_blocks()

    def validate_one(self, section_id):
        corr_id = self.selected_by_section.get(section_id)
        if corr_id:
            self.service.associer_resultat_pour_ouvrage(section_id, corr_id)
            self.selected_by_section.pop(section_id, None)
            self.refresh_blocks()

    def validate_selected(self):
        if not self.selected_by_section:
            QMessageBox.information(self, "Validation", "Aucune proposition sélectionnée.")
            return
        try:
            self.service.associer_selection(dict(self.selected_by_section))
            self.selected_by_section.clear()
            self.refresh_blocks()
        except Exception as exc:
            QMessageBox.critical(self, "Validation impossible", str(exc))

    def manual_search(self, section_id):
        dialog = CatalogueSearchDialog(self.service, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_ouvrage_id:
            self.service.associer_manuellement(section_id, dialog.selected_ouvrage_id)
            self.refresh_blocks()

    def search_one(self, section_id, elargir_toutes_bibliotheques=False):
        self.service.rechercher(section_id, elargir_toutes_bibliotheques, enregistrer=True)
        self.refresh_blocks()

    def run_auto_matching(self):
        if self.matching_thread and self.matching_thread.isRunning():
            return
        elargir = self.expand_mapping_checkbox.isChecked()
        self._start_matching_worker(elargir, "textuel")

    def run_ai_matching(self):
        if self.matching_thread and self.matching_thread.isRunning():
            return
        scope = self._ask_ai_scope()
        if scope is None:
            return
        self._start_matching_worker(scope, "ia")

    def _ask_ai_scope(self):
        box = QMessageBox(self)
        box.setWindowTitle("Recherche auto avec IA")
        box.setText("Où rechercher les correspondances IA ?")
        active_button = box.addButton("Bibliothèques actives du projet", QMessageBox.AcceptRole)
        all_button = box.addButton("Toutes les bibliothèques", QMessageBox.DestructiveRole)
        box.addButton("Annuler", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == active_button:
            return False
        if clicked == all_button:
            return True
        return None

    def _start_matching_worker(self, elargir, mode):
        estimate = self.service.estimer_rapprochement(self.projet.id, elargir)
        seuil = self.matching_comparison_threshold()
        if mode != "ia" and estimate["comparaisons_estimees"] > seuil:
            reply = QMessageBox.question(
                self,
                "Rapprochement volumineux",
                f"{estimate['lignes']} lignes DPGF à traiter.\n"
                f"Environ {estimate['comparaisons_estimees']:,} comparaisons fines estimées après préfiltrage.\n\n"
                "Le traitement peut prendre plusieurs minutes. Continuer ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.matching_progress.setMaximum(max(estimate["lignes"], 1))
        self.matching_progress.setValue(0)
        self.matching_progress.setVisible(True)
        self.matching_status.setText("Préparation du rapprochement...")
        self.matching_status.setVisible(True)
        self.btn_cancel_matching.setVisible(True)
        self.btn_cancel_matching.setEnabled(True)
        self.btn_run_auto.setEnabled(False)
        self.btn_run_ai.setEnabled(False)

        self.matching_thread = QThread(self)
        self.matching_worker = MatchingWorker(
            self.service.db.db_path,
            self.service.db.migrations_dir,
            self.projet.id,
            elargir,
            mode,
        )
        self.matching_worker.moveToThread(self.matching_thread)
        self.matching_thread.started.connect(self.matching_worker.run)
        self.matching_worker.progression.connect(self.on_matching_progress)
        self.matching_worker.succes.connect(self.on_matching_success)
        self.matching_worker.erreur.connect(self.on_matching_error)
        self.matching_worker.termine.connect(self.matching_thread.quit)
        self.matching_worker.termine.connect(self.matching_worker.deleteLater)
        self.matching_thread.finished.connect(self.matching_thread.deleteLater)
        self.matching_thread.finished.connect(self.on_matching_finished)
        self.matching_thread.start()

    def matching_comparison_threshold(self):
        param = self.service.parametre_service.obtenir_parametre("seuil_comparaisons_matching")
        if not param:
            self.service.parametre_service.creer_ou_modifier_parametre(
                "seuil_comparaisons_matching",
                "500000",
                "integer",
                "comparaisons",
                "Seuil d'avertissement avant rapprochement DPGF-bibliothèques",
            )
            return 500000
        try:
            return int(param.valeur)
        except (TypeError, ValueError):
            return 500000

    @Slot(int, int, str)
    def on_matching_progress(self, current, total, message):
        self.matching_progress.setMaximum(max(total, 1))
        self.matching_progress.setValue(current)
        self.matching_status.setText(message)

    @Slot(object)
    def on_matching_success(self, result):
        if result.annule:
            QMessageBox.information(self, "Rapprochement annulé", f"Traitement annulé après {result.traites}/{result.total} lignes.")
        else:
            QMessageBox.information(
                self,
                "Rapprochement terminé",
                f"{result.traites}/{result.total} lignes traitées.\n"
                f"{result.propositions} propositions créées ou mises à jour.",
            )
        self.refresh_blocks()

    @Slot(str)
    def on_matching_error(self, message):
        QMessageBox.critical(self, "Erreur rapprochement", message)

    @Slot()
    def on_matching_finished(self):
        self.btn_run_auto.setEnabled(True)
        self.btn_run_ai.setEnabled(True)
        self.btn_cancel_matching.setVisible(False)
        self.matching_status.setText("Rapprochement terminé")
        self.matching_worker = None
        self.matching_thread = None

    def cancel_auto_matching(self):
        if self.matching_worker:
            self.matching_status.setText("Annulation demandée...")
            self.btn_cancel_matching.setEnabled(False)
            self.matching_worker.cancel()

    def closeEvent(self, event):
        if self.matching_thread and self.matching_thread.isRunning():
            self.cancel_auto_matching()
            event.ignore()
            QMessageBox.information(self, "Rapprochement en cours", "Annulation demandée. La fenêtre se fermera après l'arrêt du traitement.")
            return
        super().closeEvent(event)

    def load_more(self):
        self.render_limit += self.PAGE_SIZE
        self.refresh_blocks()

    def decimal_text(self, value):
        return "" if value is None else str(value)


class ComparaisonVersionsDialog(QDialog):
    def __init__(self, projet, version_service: VersionProjetService, parent=None):
        super().__init__(parent)
        self.projet = projet
        self.version_service = version_service
        self.versions = []
        self.lots = []
        self.setWindowTitle(f"Comparaison de versions - {projet.nom}")
        self.resize(1180, 780)
        self.setStyleSheet(APP_STYLESHEET)
        self._setup_ui()
        self.refresh_versions()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Comparaison de versions")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")

        selectors = QHBoxLayout()
        self.reference_combo = QComboBox()
        self.compare_combo = QComboBox()
        self.lot_combo = QComboBox()
        self.reference_combo.currentIndexChanged.connect(self.refresh_comparison)
        self.compare_combo.currentIndexChanged.connect(self.refresh_comparison)
        self.lot_combo.currentIndexChanged.connect(self.refresh_comparison)
        selectors.addWidget(QLabel("Version de référence"))
        selectors.addWidget(self.reference_combo, 1)
        selectors.addWidget(QLabel("Version à comparer"))
        selectors.addWidget(self.compare_combo, 1)
        selectors.addWidget(QLabel("Lot"))
        selectors.addWidget(self.lot_combo, 1)

        charts_layout = QHBoxLayout()
        self.reference_chart_box = QGroupBox("Référence")
        self.compare_chart_box = QGroupBox("Comparée")
        self.reference_chart_layout = QVBoxLayout(self.reference_chart_box)
        self.compare_chart_layout = QVBoxLayout(self.compare_chart_box)
        charts_layout.addWidget(self.reference_chart_box)
        charts_layout.addWidget(self.compare_chart_box)

        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(4)
        self.summary_table.setHorizontalHeaderLabels(["Composante", "Version référence", "Version comparée", "Écart"])
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.summary_table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.impact_group = QGroupBox("20 lignes les plus impactées")
        self.impact_group.setCheckable(True)
        self.impact_group.setChecked(False)
        self.impact_group.toggled.connect(self._toggle_impacts)
        impact_layout = QVBoxLayout(self.impact_group)
        self.impact_table = QTableWidget()
        self.impact_table.setColumnCount(6)
        self.impact_table.setHorizontalHeaderLabels(["Code", "Désignation", "Lot", "Référence DS", "Comparé DS", "Écart"])
        self.impact_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.impact_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.impact_table.setVisible(False)
        impact_layout.addWidget(self.impact_table)

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.reject)

        layout.addWidget(title)
        layout.addLayout(selectors)
        layout.addLayout(charts_layout)
        layout.addWidget(self.summary_table)
        layout.addWidget(self.impact_group)
        layout.addWidget(close_buttons)

    def refresh_versions(self):
        self.versions = self.version_service.lister_versions(self.projet.id)
        self.lots = self.version_service.lister_lots(self.projet.id)
        self.reference_combo.blockSignals(True)
        self.compare_combo.blockSignals(True)
        self.lot_combo.blockSignals(True)
        self.reference_combo.clear()
        self.compare_combo.clear()
        self.lot_combo.clear()
        for version in self.versions:
            label = f"{version.nom} ({version.date_creation})"
            self.reference_combo.addItem(label, str(version.id))
            self.compare_combo.addItem(label, str(version.id))
        self.compare_combo.insertItem(0, "Version actuelle", SOURCE_ACTUEL)
        self.lot_combo.addItem("Tous les lots", None)
        for lot in self.lots:
            self.lot_combo.addItem(f"{lot['code']} - {lot['libelle']}", lot["id"])
        self.reference_combo.blockSignals(False)
        self.compare_combo.blockSignals(False)
        self.lot_combo.blockSignals(False)
        self.refresh_comparison()

    def refresh_comparison(self):
        if self.reference_combo.count() == 0:
            self.summary_table.setRowCount(0)
            self.impact_table.setRowCount(0)
            self._set_chart_placeholder(self.reference_chart_layout, "Aucune version créée")
            self._set_chart_placeholder(self.compare_chart_layout, "Créez une version depuis la fiche projet.")
            return
        reference_source = self.reference_combo.currentData()
        compare_source = self.compare_combo.currentData()
        lot_id = self.lot_combo.currentData()
        comparison = self.version_service.comparer(self.projet.id, reference_source, compare_source, lot_id)
        self._populate_summary(comparison)
        self._populate_impacts(comparison["top_impacted"])
        self._populate_chart(self.reference_chart_layout, comparison["reference"], "Référence")
        self._populate_chart(self.compare_chart_layout, comparison["comparee"], "Comparée")

    def _populate_summary(self, comparison):
        self.summary_table.setRowCount(0)
        for row, data in enumerate(comparison["lignes"]):
            self.summary_table.insertRow(row)
            values = [
                data["composante"],
                self.version_service.format_euro(data["reference"]),
                self.version_service.format_euro(data["comparee"]),
                data["ecart_formate"],
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if data["cle"] == "pv_total" and col == 3:
                    if data["ecart_montant"] < 0:
                        item.setBackground(QColor(COLORS["success"]))
                    elif data["ecart_montant"] > 0:
                        item.setBackground(QColor(COLORS["danger"]))
                self.summary_table.setItem(row, col, item)

    def _populate_impacts(self, lines):
        self.impact_table.setRowCount(0)
        for row, line in enumerate(lines):
            self.impact_table.insertRow(row)
            values = [
                line["code"],
                line["designation"],
                line["lot"],
                self.version_service.format_euro(line["reference"]),
                self.version_service.format_euro(line["comparee"]),
                line["ecart_formate"],
            ]
            for col, value in enumerate(values):
                self.impact_table.setItem(row, col, QTableWidgetItem(value))

    def _toggle_impacts(self, checked):
        self.impact_table.setVisible(checked)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _populate_chart(self, layout, aggregate, title):
        self._clear_layout(layout)
        pie_data = self.version_service.pie_data(aggregate)
        positive_data = [item for item in pie_data if item["valeur"] > 0]
        if not positive_data:
            layout.addWidget(QLabel("Aucun déboursé sec à afficher."))
            return
        FigureCanvasQTAgg = None
        Figure = None
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
        except Exception:
            pass
        if FigureCanvasQTAgg and Figure:
            figure = Figure(figsize=(4.2, 2.4), tight_layout=True, facecolor=COLORS["background"])
            canvas = FigureCanvasQTAgg(figure)
            axis = figure.add_subplot(111)
            axis.set_facecolor(COLORS["background"])
            axis.pie(
                [float(item["valeur"]) for item in positive_data],
                labels=[item["label"] for item in positive_data],
                autopct="%1.1f%%",
                startangle=90,
                textprops={"color": COLORS["text"]},
            )
            axis.set_title(title, color=COLORS["text"])
            canvas.setMinimumHeight(240)
            layout.addWidget(canvas)
            return
        if QChart and QChartView and QPieSeries:
            series = QPieSeries()
            for item in positive_data:
                percent = self.version_service.format_percent(item["pourcentage"])
                series.append(f"{item['label']} ({percent})", float(item["valeur"]))
            chart = QChart()
            chart.addSeries(series)
            chart.setTitle(title)
            chart.legend().setVisible(True)
            view = QChartView(chart)
            view.setRenderHint(QPainter.Antialiasing)
            view.setMinimumHeight(220)
            layout.addWidget(view)
            return
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Composante", "Montant", "% DS"])
        table.setRowCount(len(pie_data))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, item in enumerate(pie_data):
            table.setItem(row, 0, QTableWidgetItem(item["label"]))
            table.setItem(row, 1, QTableWidgetItem(self.version_service.format_euro(item["valeur"])))
            table.setItem(row, 2, QTableWidgetItem(self.version_service.format_percent(item["pourcentage"])))
        layout.addWidget(table)

    def _set_chart_placeholder(self, layout, text):
        self._clear_layout(layout)
        layout.addWidget(QLabel(text))


class ProjetsPage(QWidget):
    TABLE_COLUMNS = [
        "N° Art.",
        "Libellé",
        "Type",
        "U.",
        "Qté",
        "P.U.",
        "Total",
        "Feuille",
        "Ligne Excel",
        "Correspondance",
        "Action",
    ]
    MATCH_COLUMNS = ["Score", "Code", "Désignation", "Famille", "Unité", "Déboursé sec", "PV EG HT", "Bibliothèque"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_manager = DatabaseManager()
        self.projet_repo = ProjetRepository(self.db_manager)
        self.projet_service = ProjetService(self.projet_repo)
        self.section_repo = SectionProjetRepository(self.db_manager)
        self.section_service = SectionProjetService(self.section_repo)
        self.import_service = ImportDpgfService(self.section_repo)
        self.parametre_repo = ParametreRepository(self.db_manager)
        self.parametre_service = ParametreService(self.parametre_repo)
        self.version_repo = VersionProjetRepository(self.db_manager)
        self.version_service = VersionProjetService(self.version_repo)
        self.correspondance_repo = CorrespondanceDpgfRepository(self.db_manager)
        self.correspondance_service = CorrespondanceService(
            self.db_manager,
            self.correspondance_repo,
            self.section_repo,
            self.parametre_service,
        )
        self.chiffrage_service = ChiffrageProjetService(
            self.db_manager,
            self.section_repo,
            self.correspondance_repo,
        )

        self.projets = []
        self.sections = []
        self.current_project = None
        self.section_by_id = {}
        self.selected_section_id = None
        self.import_thread = None
        self.import_worker = None
        self._thread = None
        self._worker = None
        self.import_timeout_timer = None
        self.import_in_progress = False
        self.cursor_overridden = False
        self.import_project = None
        self._setup_ui()
        self.load_projects()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        header_layout = QHBoxLayout()
        titre = QLabel("Gestion des Projets")
        titre.setStyleSheet("font-size: 24px; font-weight: bold;")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher un projet...")
        self.search_input.textChanged.connect(self.apply_project_filter)

        self.btn_new = QPushButton("Nouveau")
        self.btn_new.clicked.connect(self.on_new_project)
        self.btn_edit = QPushButton("Modifier")
        self.btn_edit.clicked.connect(self.on_edit_project)
        self.btn_delete = QPushButton("Supprimer")
        self.btn_delete.clicked.connect(self.on_delete_project)
        self.btn_open = QPushButton("Ouvrir")
        self.btn_open.clicked.connect(self.on_open_project)
        self.btn_import = QPushButton("Importer DPGF")
        self.btn_import.clicked.connect(self.on_import_dpgf)
        self.btn_mapping = QPushButton("Mapping")
        self.btn_mapping.clicked.connect(self.on_open_mapping)
        self.btn_chiffrage = QPushButton("Chiffrage")
        self.btn_chiffrage.clicked.connect(self.on_open_chiffrage)
        self.btn_create_version = QPushButton("Créer une version")
        self.btn_create_version.clicked.connect(self.on_create_version)
        self.btn_compare_versions = QPushButton("Comparaison de versions")
        self.btn_compare_versions.clicked.connect(self.on_compare_versions)

        header_layout.addWidget(titre)
        header_layout.addWidget(self.search_input, 1)
        header_layout.addWidget(self.btn_new)
        header_layout.addWidget(self.btn_edit)
        header_layout.addWidget(self.btn_delete)
        header_layout.addWidget(self.btn_open)
        header_layout.addWidget(self.btn_import)
        header_layout.addWidget(self.btn_mapping)
        header_layout.addWidget(self.btn_chiffrage)
        header_layout.addWidget(self.btn_create_version)
        header_layout.addWidget(self.btn_compare_versions)

        splitter = QSplitter(Qt.Vertical)
        projects_panel = QWidget()
        projects_panel_layout = QVBoxLayout(projects_panel)
        projects_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.projects_table = QTableWidget()
        self.projects_table.setColumnCount(5)
        self.projects_table.setHorizontalHeaderLabels(["ID", "Nom", "Client", "Référence", "Statut"])
        self.projects_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.projects_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.projects_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.projects_table.itemSelectionChanged.connect(self.on_project_selection_changed)
        self.projects_table.itemDoubleClicked.connect(self.on_open_project)

        versions_header = QHBoxLayout()
        versions_title = QLabel("Versions du projet")
        versions_title.setStyleSheet("font-weight: bold;")
        self.btn_delete_version = QPushButton("Supprimer la version")
        self.btn_delete_version.clicked.connect(self.on_delete_version)
        versions_header.addWidget(versions_title)
        versions_header.addStretch()
        versions_header.addWidget(self.btn_delete_version)

        self.versions_table = QTableWidget()
        self.versions_table.setColumnCount(5)
        self.versions_table.setHorizontalHeaderLabels(["ID", "Nom", "Date", "Lignes", "Action"])
        self.versions_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.versions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.versions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.versions_table.itemDoubleClicked.connect(self.on_compare_versions)
        self.versions_table.itemSelectionChanged.connect(self.update_project_buttons)

        projects_panel_layout.addWidget(self.projects_table)
        projects_panel_layout.addLayout(versions_header)
        projects_panel_layout.addWidget(self.versions_table)

        dpgf_splitter = QSplitter(Qt.Horizontal)
        dpgf_right = QWidget()
        dpgf_right_layout = QVBoxLayout(dpgf_right)
        dpgf_right_layout.setContentsMargins(0, 0, 0, 0)

        controls_layout = QHBoxLayout()
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Enfants directs", "Tous les ouvrages descendants"])
        self.view_mode_combo.currentTextChanged.connect(self.refresh_section_table)

        self.include_info_checkbox = QCheckBox("Inclure informations")
        self.include_info_checkbox.setEnabled(False)
        self.include_info_checkbox.stateChanged.connect(self.refresh_section_table)

        self.dpgf_search_input = QLineEdit()
        self.dpgf_search_input.setPlaceholderText("Rechercher N° article ou libellé...")
        self.dpgf_search_input.textChanged.connect(self.refresh_section_table)

        self.type_filter = QComboBox()
        self.type_filter.currentTextChanged.connect(self.refresh_section_table)
        self.unite_filter = QComboBox()
        self.unite_filter.currentTextChanged.connect(self.refresh_section_table)
        self.feuille_filter = QComboBox()
        self.feuille_filter.currentTextChanged.connect(self.refresh_section_table)

        controls_layout.addWidget(QLabel("Mode"))
        controls_layout.addWidget(self.view_mode_combo)
        controls_layout.addWidget(self.include_info_checkbox)
        controls_layout.addWidget(self.dpgf_search_input, 1)
        controls_layout.addWidget(QLabel("Type"))
        controls_layout.addWidget(self.type_filter)
        controls_layout.addWidget(QLabel("Unité"))
        controls_layout.addWidget(self.unite_filter)
        controls_layout.addWidget(QLabel("Feuille/Lot"))
        controls_layout.addWidget(self.feuille_filter)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["DPGF"])
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)

        self.children_table = QTableWidget()
        self.children_table.setColumnCount(len(self.TABLE_COLUMNS))
        self.children_table.setHorizontalHeaderLabels(self.TABLE_COLUMNS)
        self.children_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.children_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.children_table.setColumnWidth(0, 90)
        self.children_table.setColumnWidth(1, 520)
        self.children_table.setColumnWidth(2, 110)
        self.children_table.setColumnWidth(3, 55)
        self.children_table.setColumnWidth(4, 80)
        self.children_table.setColumnWidth(5, 80)
        self.children_table.setColumnWidth(6, 90)
        self.children_table.setColumnWidth(7, 160)
        self.children_table.setColumnWidth(8, 90)
        self.children_table.setColumnWidth(9, 120)
        self.children_table.setColumnWidth(10, 110)
        self.children_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.children_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.children_table.itemSelectionChanged.connect(self.on_dpgf_table_selection_changed)
        self.children_table.itemDoubleClicked.connect(self.on_dpgf_table_double_clicked)

        dpgf_splitter.addWidget(self.tree)
        dpgf_right_layout.addLayout(controls_layout)
        dpgf_right_layout.addWidget(self.children_table)
        dpgf_splitter.addWidget(dpgf_right)
        dpgf_splitter.setSizes([420, 780])

        splitter.addWidget(projects_panel)
        splitter.addWidget(dpgf_splitter)
        splitter.setSizes([230, 560])

        main_layout.addLayout(header_layout)
        main_layout.addWidget(splitter)
        self.update_project_buttons()

    def load_projects(self):
        self.projets = self.projet_service.lister_projets()
        self.apply_project_filter()

    def apply_project_filter(self):
        search = self.search_input.text().strip().lower()
        filtered = []
        for projet in self.projets:
            haystack = " ".join([projet.nom, projet.client, projet.reference, projet.statut]).lower()
            if not search or search in haystack:
                filtered.append(projet)
        self.projects_table.setRowCount(0)
        for row, projet in enumerate(filtered):
            self.projects_table.insertRow(row)
            values = [str(projet.id), projet.nom, projet.client, projet.reference, projet.statut]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, projet.id)
                self.projects_table.setItem(row, col, item)
        self.update_project_buttons()

    def selected_project(self):
        selected = self.projects_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        projet_id = self.projects_table.item(row, 0).data(Qt.UserRole)
        return next((projet for projet in self.projets if projet.id == projet_id), None)

    def update_project_buttons(self):
        has_selection = self.selected_project() is not None
        has_version_selection = self.selected_version_id() is not None
        self.btn_edit.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)
        self.btn_open.setEnabled(has_selection)
        self.btn_import.setEnabled(has_selection and not self.import_in_progress)
        if hasattr(self, "btn_mapping"):
            self.btn_mapping.setEnabled(has_selection)
        if hasattr(self, "btn_chiffrage"):
            self.btn_chiffrage.setEnabled(has_selection)
        if hasattr(self, "btn_create_version"):
            self.btn_create_version.setEnabled(has_selection)
            self.btn_compare_versions.setEnabled(has_selection)
        if hasattr(self, "btn_delete_version"):
            self.btn_delete_version.setEnabled(has_version_selection)

    def on_project_selection_changed(self):
        self.update_project_buttons()
        self.refresh_versions_table()

    def on_new_project(self):
        dialog = ProjetFormDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.projet_service.creer_projet(
                dialog.nom_input.text().strip(),
                dialog.client_input.text().strip(),
                dialog.reference_input.text().strip(),
                dialog.statut_input.text().strip() or "Nouveau",
            )
            self.load_projects()

    def on_edit_project(self):
        projet = self.selected_project()
        if not projet:
            return
        dialog = ProjetFormDialog(projet, self)
        if dialog.exec() == QDialog.Accepted:
            self.projet_service.modifier_projet(
                projet.id,
                dialog.nom_input.text().strip(),
                dialog.client_input.text().strip(),
                dialog.reference_input.text().strip(),
                dialog.statut_input.text().strip(),
            )
            self.load_projects()

    def on_delete_project(self):
        projet = self.selected_project()
        if not projet:
            return
        reply = QMessageBox.question(
            self,
            "Supprimer le projet",
            f"Supprimer le projet '{projet.nom}' et son DPGF importé ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.projet_service.supprimer_projet(projet.id)
            if self.current_project and self.current_project.id == projet.id:
                self.current_project = None
                self.sections = []
                self.populate_tree()
            self.load_projects()

    def refresh_versions_table(self):
        if not hasattr(self, "versions_table"):
            return
        projet = self.selected_project() or self.current_project
        self.versions_table.setRowCount(0)
        if not projet:
            self.update_project_buttons()
            return
        versions = self.version_service.lister_versions(projet.id)
        for row, version in enumerate(versions):
            self.versions_table.insertRow(row)
            values = [
                str(version.id),
                version.nom + (" (courante)" if version.est_version_courante else ""),
                version.date_creation,
                str(version.nombre_lignes),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, version.id)
                self.versions_table.setItem(row, col, item)
            btn_duplicate = QPushButton("Dupliquer cette version")
            btn_duplicate.clicked.connect(lambda _=False, vid=version.id: self.on_duplicate_version(vid))
            self.versions_table.setCellWidget(row, 4, btn_duplicate)
        self.update_project_buttons()

    def selected_version_id(self):
        if not hasattr(self, "versions_table"):
            return None
        selected = self.versions_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        return self.versions_table.item(row, 0).data(Qt.UserRole)

    def on_create_version(self):
        projet = self.selected_project() or self.current_project
        if not projet:
            return
        nom, ok = QInputDialog.getText(self, "Créer une version", "Nom de la version :")
        if not ok:
            return
        try:
            version_id = self.version_service.creer_version(projet.id, nom)
            self.refresh_versions_table()
            QMessageBox.information(self, "Version créée", f"La version #{version_id} a été créée.")
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Création de version impossible :\n{exc}")

    def on_duplicate_version(self, version_id):
        projet = self.selected_project() or self.current_project
        if not projet:
            return
        if self.version_service.a_modifications_non_sauvegardees(projet.id):
            choice = QMessageBox(self)
            choice.setWindowTitle("Modifications non enregistrées")
            choice.setText(
                "Les modifications actuelles non enregistrées seront perdues. "
                "Créer une version avec l'état actuel d'abord, ou continuer sans sauvegarder ?"
            )
            save_button = choice.addButton("Créer une version avec l'état actuel", QMessageBox.AcceptRole)
            continue_button = choice.addButton("Continuer sans sauvegarder", QMessageBox.DestructiveRole)
            choice.addButton(QMessageBox.Cancel)
            choice.exec()
            clicked = choice.clickedButton()
            if clicked == save_button:
                if not self._create_current_version_before_duplicate(projet.id):
                    return
            elif clicked != continue_button:
                return

        nom, ok = QInputDialog.getText(
            self,
            "Dupliquer la version",
            "Nom de la nouvelle version :",
            text=self._default_duplicate_version_name(projet.id),
        )
        if not ok:
            return
        try:
            new_version_id = self.version_service.dupliquer_version(version_id, nom)
            if self.current_project and self.current_project.id == projet.id:
                self.open_project(projet)
            else:
                self.refresh_versions_table()
            QMessageBox.information(
                self,
                "Version dupliquée",
                f"La version #{new_version_id} a été créée et appliquée au chiffrage courant.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Duplication de version impossible :\n{exc}")

    def _create_current_version_before_duplicate(self, projet_id: int) -> bool:
        nom, ok = QInputDialog.getText(
            self,
            "Créer une version",
            "Nom de la version actuelle :",
            text="Version actuelle",
        )
        if not ok:
            return False
        try:
            self.version_service.creer_version(projet_id, nom)
            self.refresh_versions_table()
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Création de version impossible :\n{exc}")
            return False

    def _default_duplicate_version_name(self, projet_id: int) -> str:
        return f"Version {len(self.version_service.lister_versions(projet_id)) + 1}"

    def on_compare_versions(self):
        projet = self.selected_project() or self.current_project
        if not projet:
            return
        dialog = ComparaisonVersionsDialog(projet, self.version_service, self)
        dialog.exec()
        self.refresh_versions_table()

    def on_delete_version(self):
        version_id = self.selected_version_id()
        if not version_id:
            return
        reply = QMessageBox.question(
            self,
            "Supprimer la version",
            "Supprimer cette version figée ? Les données du projet et l'historique ne seront pas modifiés.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.version_service.supprimer_version(version_id)
            self.refresh_versions_table()

    def on_open_project(self):
        projet = self.selected_project()
        if projet:
            self.open_project(projet)

    def on_open_mapping(self):
        projet = self.selected_project() or self.current_project
        if not projet:
            return
        self.open_project(projet)
        dialog = ChiffrageTableDialog(
            projet,
            self.chiffrage_service,
            parent=self,
            correspondance_service=self.correspondance_service,
            db_manager=self.db_manager,
            version_service=self.version_service,
        )
        dialog.exec()
        self.open_project(projet)

    def on_open_chiffrage(self):
        projet = self.selected_project() or self.current_project
        if not projet:
            return
        self.open_project(projet)
        dialog = ChiffrageTableDialog(
            projet,
            self.chiffrage_service,
            parent=self,
            correspondance_service=self.correspondance_service,
            db_manager=self.db_manager,
            version_service=self.version_service,
        )
        dialog.exec()
        self.refresh_versions_table()

    def open_project(self, projet):
        self.current_project = projet
        self.chiffrage_service = ChiffrageProjetService(
            self.db_manager,
            self.section_repo,
            self.correspondance_repo,
        )
        self.sections = self.section_service.lister_sections(projet.id)
        self.section_by_id = {section.id: section for section in self.sections}
        self.refresh_dpgf_filters()
        self.populate_tree()
        self.refresh_versions_table()

    def on_import_dpgf(self):
        if self.import_in_progress:
            logger.warning("Import DPGF : tentative ignorée, import déjà en cours")
            return
        projet = self.selected_project()
        if not projet:
            return

        if self.section_service.compter_sections(projet.id) > 0:
            reply = QMessageBox.question(
                self,
                "Remplacer le DPGF existant",
                "Ce projet contient déjà un DPGF importé. Remplacer entièrement le DPGF existant ?\n\n"
                "Le remplacement du DPGF supprimera aussi toutes les correspondances déjà proposées ou validées pour ce projet.",
                QMessageBox.Yes | QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner le DPGF Excel",
            "",
            "Fichiers Excel (*.xlsx *.xlsm *.xltx *.xltm)",
        )
        if not filepath:
            return

        try:
            logger.info("Import DPGF UI : analyse fichier %s", filepath)
            sheets = self.import_service.analyser_fichier(filepath)
            overrides = self._resolve_header_overrides(sheets)
            if overrides is None:
                logger.info("Import DPGF UI : import annulé avant démarrage")
                return
            logger.info("Import DPGF UI : validation utilisateur terminée, démarrage worker")
            self._start_import_worker(filepath, projet, overrides)
        except Exception as exc:
            logger.exception("Import DPGF UI : erreur avant worker")
            QMessageBox.critical(self, "Erreur", f"Import DPGF annulé :\n{exc}")

    def _resolve_header_overrides(self, sheets):
        recognized = [sheet for sheet in sheets if sheet.recognized]
        if not recognized:
            ignored = "\n".join(f"- {sheet.nom}: {sheet.warning}" for sheet in sheets if sheet.warning)
            QMessageBox.warning(self, "Aucune feuille DPGF", f"Aucune feuille de lot reconnue.\n\n{ignored}")
            return None

        ignored = [sheet for sheet in sheets if not sheet.recognized and not sheet.excluded]
        if not ignored:
            logger.info("Import DPGF UI : en-têtes détectés automatiquement, pas de dialogue manuel")
            return {}

        defaults = ", ".join(f"{sheet.nom}={sheet.header_row}" for sheet in recognized)
        text, ok = QInputDialog.getText(
            self,
            "En-têtes DPGF partiels",
            "Certaines feuilles n'ont pas été reconnues. Confirmez ou modifiez les lignes d'en-tête des feuilles reconnues :",
            text=defaults,
        )
        if not ok:
            return None
        overrides = {}
        for part in text.split(","):
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            try:
                overrides[name.strip()] = int(value.strip())
            except ValueError:
                QMessageBox.warning(self, "Ligne invalide", f"Ligne d'en-tête invalide : {part}")
                return None
        return overrides

    def _start_import_worker(self, filepath, projet, overrides):
        if self.import_in_progress:
            logger.warning("Import DPGF UI : start ignoré, import déjà en cours")
            return
        self._set_import_running(True)
        self.import_project = projet
        logger.info("Import DPGF UI : avant création QThread")
        self._thread = QThread(self)
        self.import_thread = self._thread
        logger.info("Import DPGF UI : après création QThread thread=%s", self._thread)

        logger.info("Import DPGF UI : avant création worker")
        self._worker = DpgfImportWorker(
            self.db_manager.db_path,
            self.db_manager.migrations_dir,
            filepath,
            projet.id,
            overrides,
            timeout_seconds=120,
        )
        self.import_worker = self._worker
        logger.info("Import DPGF UI : après création worker worker=%s", self._worker)

        logger.info("Import DPGF UI : avant moveToThread")
        self._worker.moveToThread(self._thread)
        logger.info("Import DPGF UI : après moveToThread")

        self._thread.started.connect(self._worker.run, Qt.ConnectionType.QueuedConnection)
        self._worker.progression.connect(self._on_import_progress, Qt.ConnectionType.QueuedConnection)
        self._worker.succes.connect(self._on_import_success, Qt.ConnectionType.QueuedConnection)
        self._worker.erreur.connect(self._on_import_error, Qt.ConnectionType.QueuedConnection)
        self._worker.termine.connect(self._thread.quit, Qt.ConnectionType.QueuedConnection)
        self._worker.termine.connect(self._worker.deleteLater, Qt.ConnectionType.QueuedConnection)
        self._worker.termine.connect(self._on_import_finished, Qt.ConnectionType.QueuedConnection)
        self._thread.finished.connect(self._thread.deleteLater, Qt.ConnectionType.QueuedConnection)

        self.import_timeout_timer = QTimer(self)
        self.import_timeout_timer.setSingleShot(True)
        self.import_timeout_timer.timeout.connect(self._on_import_timeout)
        self.import_timeout_timer.start(125_000)
        logger.info("Import DPGF UI : avant start QThread")
        self._thread.start()
        logger.info("Import DPGF UI : après start QThread")

    def _set_import_running(self, running: bool):
        self.import_in_progress = running
        self.btn_import.setEnabled(not running and self.selected_project() is not None)
        if running and not self.cursor_overridden:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.cursor_overridden = True
        elif not running and self.cursor_overridden:
            QApplication.restoreOverrideCursor()
            self.cursor_overridden = False

    @Slot(int, str)
    def _on_import_progress(self, percent: int, message: str):
        logger.info("Import DPGF UI : progression %s%% %s thread=%s", percent, message, QThread.currentThread())

    @Slot(object)
    def _on_import_success(self, summary):
        app = QApplication.instance()
        is_main_thread = app is not None and QThread.currentThread() == app.thread()
        logger.info(
            "Import DPGF UI : succès reçu thread=%s main_thread=%s",
            QThread.currentThread(),
            is_main_thread,
        )
        self._cleanup_import_ui()
        if self.import_project:
            self.open_project(self.import_project)
        QMessageBox.information(self, "Rapport d'import DPGF", self._format_import_summary(summary))

    @Slot(str)
    def _on_import_error(self, message: str):
        app = QApplication.instance()
        is_main_thread = app is not None and QThread.currentThread() == app.thread()
        logger.info(
            "Import DPGF UI : erreur reçue thread=%s main_thread=%s",
            QThread.currentThread(),
            is_main_thread,
        )
        self._cleanup_import_ui()
        QMessageBox.critical(self, "Erreur", f"Import DPGF annulé :\n{message}")

    @Slot()
    def _on_import_finished(self):
        logger.info("Import DPGF UI : worker terminé thread=%s", QThread.currentThread())
        self._cleanup_import_ui()
        self.import_worker = None
        self.import_thread = None
        self._worker = None
        self._thread = None
        self.import_project = None

    def _cleanup_import_ui(self):
        if self.import_timeout_timer:
            self.import_timeout_timer.stop()
            self.import_timeout_timer.deleteLater()
            self.import_timeout_timer = None
        self._set_import_running(False)

    @Slot()
    def _on_import_timeout(self):
        logger.error("Import DPGF UI : timeout worker")
        if self.import_thread and self.import_thread.isRunning():
            self.import_thread.requestInterruption()
        QMessageBox.critical(self, "Timeout", "L'import DPGF a dépassé le délai autorisé.")
        self._cleanup_import_ui()

    def populate_tree(self):
        self.tree.clear()
        self.children_table.setRowCount(0)
        self.selected_section_id = None
        items_by_id = {}
        roots = []
        for section in self.sections:
            label = f"{section.numero_article} {section.libelle}" if section.numero_article else section.libelle
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, section.id)
            items_by_id[section.id] = item
            if section.parent_id and section.parent_id in items_by_id:
                items_by_id[section.parent_id].addChild(item)
            else:
                roots.append(item)
        for item in roots:
            self.tree.addTopLevelItem(item)
        self.tree.expandToDepth(1)
        self.refresh_section_table()

    def on_tree_selection_changed(self):
        selected = self.tree.selectedItems()
        if not selected:
            self.selected_section_id = None
        else:
            self.selected_section_id = selected[0].data(0, Qt.UserRole)
        self.refresh_section_table()

    def refresh_dpgf_filters(self):
        self._set_combo_items(self.type_filter, ["Tous"] + sorted({section.type_ligne for section in self.sections}))
        self._set_combo_items(self.unite_filter, ["Toutes"] + sorted({section.unite for section in self.sections if section.unite}))
        self._set_combo_items(self.feuille_filter, ["Toutes"] + sorted({section.feuille_source for section in self.sections if section.feuille_source}))

    def _set_combo_items(self, combo, values):
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        if current in values:
            combo.setCurrentText(current)
        combo.blockSignals(False)

    def refresh_section_table(self):
        if not hasattr(self, "view_mode_combo"):
            return
        mode = self.view_mode_combo.currentText()
        self.include_info_checkbox.setEnabled(mode == "Tous les ouvrages descendants")
        if mode == "Tous les ouvrages descendants":
            sections = self._descendant_sections(self.selected_section_id)
            allowed = {"ouvrage", "pour_memoire"}
            if self.include_info_checkbox.isChecked():
                allowed.add("information")
            sections = [section for section in sections if section.type_ligne in allowed]
        else:
            sections = [
                section for section in self.sections
                if section.parent_id == self.selected_section_id
                or (self.selected_section_id is None and section.parent_id is None)
            ]
        self.populate_children_table(self._apply_section_filters(sections))

    def _descendant_sections(self, section_id):
        children_by_parent = {}
        for section in self.sections:
            children_by_parent.setdefault(section.parent_id, []).append(section)
        result = []
        stack = list(reversed(children_by_parent.get(section_id, [])))
        while stack:
            section = stack.pop()
            result.append(section)
            stack.extend(reversed(children_by_parent.get(section.id, [])))
        return result

    def _apply_section_filters(self, sections):
        search = self.dpgf_search_input.text().strip().lower()
        type_filter = self.type_filter.currentText()
        unite_filter = self.unite_filter.currentText()
        feuille_filter = self.feuille_filter.currentText()
        filtered = []
        for section in sections:
            haystack = " ".join([section.numero_article or "", section.libelle or ""]).lower()
            if search and search not in haystack:
                continue
            if type_filter and type_filter != "Tous" and section.type_ligne != type_filter:
                continue
            if unite_filter and unite_filter != "Toutes" and section.unite != unite_filter:
                continue
            if feuille_filter and feuille_filter != "Toutes" and section.feuille_source != feuille_filter:
                continue
            filtered.append(section)
        return filtered

    def populate_children_table(self, sections):
        self.children_table.setRowCount(0)
        for row, section in enumerate(sections):
            self.children_table.insertRow(row)
            statut = self.correspondance_service.statut_ouvrage(section.id) if section.type_ligne in ("ouvrage", "pour_memoire") else ""
            values = [
                section.numero_article or "",
                section.libelle,
                section.type_ligne,
                section.unite or "",
                self._decimal_text(section.quantite),
                self._decimal_text(section.prix_unitaire),
                self._decimal_text(section.total),
                section.feuille_source,
                str(section.ligne_excel_source),
                statut,
                "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, section.id)
                if col == 7:
                    item.setToolTip(section.feuille_source)
                if col == 9:
                    if value == "Aucune":
                        item.setBackground(QColor(COLORS["danger"]))
                    elif value == "Proposée":
                        item.setBackground(QColor(COLORS["warning"]))
                    elif value == "Validée":
                        item.setBackground(QColor(COLORS["success"]))
                self.children_table.setItem(row, col, item)
            if section.type_ligne in ("ouvrage", "pour_memoire"):
                self.children_table.setCellWidget(row, 10, self._dpgf_action_widget(section.id, statut))

    def _dpgf_action_widget(self, section_id, statut):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if statut == "Validée":
            btn_annuler = QPushButton("Annuler")
            btn_annuler.setToolTip("Annuler la validation de la correspondance")
            btn_annuler.clicked.connect(lambda _=False, sid=section_id: self.annuler_validation_dpgf(sid))
            layout.addWidget(btn_annuler)
        elif statut == "Proposée":
            btn_valider = QPushButton("Valider")
            btn_valider.setToolTip("Choisir et valider une proposition")
            btn_valider.clicked.connect(lambda _=False, sid=section_id: self.valider_proposition_dpgf(sid))
            layout.addWidget(btn_valider)
        layout.addWidget(self._dpgf_action_button(section_id, statut))
        return widget

    def _dpgf_action_button(self, section_id, statut):
        btn = QPushButton("...")
        btn.setToolTip("Actions sur la ligne DPGF")

        def show_menu():
            menu = QMenu(btn)
            chiffrer_action = menu.addAction("Ouvrir le chiffrage")
            valider_action = menu.addAction("Valider une proposition...")
            annuler_action = menu.addAction("Annuler la validation")
            valider_action.setEnabled(statut in {"Proposée", "Validée"})
            annuler_action.setEnabled(statut == "Validée")
            action = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
            if action == chiffrer_action:
                self.open_chiffrage_for_section(section_id)
            elif action == valider_action:
                self.valider_proposition_dpgf(section_id)
            elif action == annuler_action:
                self.annuler_validation_dpgf(section_id)

        btn.clicked.connect(show_menu)
        return btn

    def valider_proposition_dpgf(self, section_id):
        propositions = self.correspondance_service.correspondances_pour_ouvrage(section_id)
        if not propositions:
            QMessageBox.information(self, "Validation", "Aucune proposition à valider pour cette ligne.")
            return
        labels = []
        ids_by_label = {}
        for proposition in propositions:
            label = (
                f"{float(proposition['score']):.1f} | {proposition['code'] or ''} | "
                f"{proposition['designation'] or ''} | {proposition['bibliotheque_nom'] or ''}"
            )
            labels.append(label)
            ids_by_label[label] = proposition["id"]
        selected, ok = QInputDialog.getItem(
            self,
            "Valider une proposition",
            "Proposition à valider :",
            labels,
            0,
            False,
        )
        if not ok or selected not in ids_by_label:
            return
        try:
            self.correspondance_service.associer_resultat_pour_ouvrage(section_id, ids_by_label[selected])
            self.chiffrage_service.copier_depuis_bibliotheque(section_id)
            self.refresh_section_table()
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Validation impossible :\n{exc}")

    def annuler_validation_dpgf(self, section_id):
        try:
            self.correspondance_service.annuler_validation_ouvrage(section_id)
            self.refresh_section_table()
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Annulation impossible :\n{exc}")

    def on_dpgf_table_selection_changed(self):
        selected = self.children_table.selectedItems()
        if not selected:
            return
        section_id = self.children_table.item(selected[0].row(), 0).data(Qt.UserRole)
        section = self.section_by_id.get(section_id)
        if not section or section.type_ligne not in ("ouvrage", "pour_memoire"):
            return

    def on_dpgf_table_double_clicked(self, item):
        section_id = self.children_table.item(item.row(), 0).data(Qt.UserRole)
        self.open_chiffrage_for_section(section_id)

    def open_chiffrage_for_section(self, section_id):
        section = self.section_by_id.get(section_id)
        if not section or section.type_ligne not in ("ouvrage", "pour_memoire"):
            return
        projet = self.current_project or self.selected_project()
        if not projet:
            return
        dialog = ChiffrageTableDialog(
            projet,
            self.chiffrage_service,
            focus_section_id=section_id,
            parent=self,
            correspondance_service=self.correspondance_service,
            db_manager=self.db_manager,
            version_service=self.version_service,
        )
        dialog.exec()
        self.refresh_versions_table()

    def _format_import_summary(self, summary):
        return "\n".join([
            f"Feuilles analysées : {summary.feuilles_analysees}",
            f"Feuilles de lots reconnues : {len(summary.feuilles_lots_reconnues)} ({', '.join(summary.feuilles_lots_reconnues)})",
            f"Feuilles BD exclues : {len(summary.feuilles_bd_exclues)} ({', '.join(summary.feuilles_bd_exclues)})",
            f"Feuilles ignorées : {len(summary.feuilles_ignorees)} ({', '.join(summary.feuilles_ignorees)})",
            f"Conteneurs : {summary.conteneurs}",
            f"Ouvrages chiffrables : {summary.ouvrages_chiffrables}",
            f"Ouvrages pour mémoire : {summary.ouvrages_pour_memoire}",
            f"Lignes informatives : {summary.lignes_informatives}",
            f"Lignes ignorées : {summary.lignes_ignorees}",
            f"Numéros d'article normalisés : {summary.numeros_articles_normalises}",
            f"Cellules fusionnées traitées : {summary.cellules_fusionnees_traitees}",
            f"Sections importées : {summary.sections_importees}",
            f"Erreurs : {len(summary.erreurs)}",
            f"Avertissements : {len(summary.avertissements)}",
        ])

    def _decimal_text(self, value: Decimal | None) -> str:
        return str(value) if value is not None else ""
