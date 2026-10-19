"""Janela principal e comandos de alto nível da aplicação."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pyvista as pv
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QStyle,
    QToolBar,
)

from app.commands.mesh_commands import TransformMeshCommand
from app.controllers.hull_controller import HullController
from app.models.attributes import ATTRIBUTES_BY_KEY, HullDesign, evaluate_attributes
from app.models.hull_types import (
    DISPLACEMENT,
    HULL_DESCRIPTIONS,
    HULL_TYPE_NAMES,
    PLANING,
    SEMI_DISPLACEMENT,
    build_hull,
)
from app.models.hydrostatics import COLUMN_INFO, default_drafts, hydrostatic_table
from app.models.nurbs_surface import (
    EditableNurbsSurface,
    NurbsSurfaceError,
    list_editable_surfaces,
)
from app.models.sampling import SampledDesign
from app.models.transforms import TransformParameters, transformation_matrix
from app.rhino_import import RhinoImportReport, read_3dm_as_polydata
from app.views.attribute_panel import AttributePanel
from app.views.curvature_dialog import CurvatureDialog
from app.views.hydrostatic_panel import HydrostaticPanel
from app.views.nurbs_face_dialog import NurbsFaceSelectionDialog
from app.views.parameter_panel import ParameterPanel
from app.visualization import HullViewer
from app.workers import SamplingWorker

#: Rótulos curtos dos cascos iniciais, como na barra do ModiYacht (SD, P, D).
HULL_TYPE_BUTTONS = (
    (SEMI_DISPLACEMENT, "SD"),
    (PLANING, "P"),
    (DISPLACEMENT, "D"),
)


class MainWindow(QMainWindow):
    """Janela principal do Odisseu.

    A janela coordena a navegação da aplicação, enquanto a geometria e o
    renderizador ficam isolados em :class:`HullViewer`.
    """

    SUPPORTED_MESH_EXTENSIONS = (".stl", ".obj", ".ply", ".vtk", ".vtp", ".3dm")
    #: Os mesmos formatos, por extenso, para mensagens ao usuário.
    SUPPORTED_FORMATS_TEXT = "STL, OBJ, PLY, VTK, VTP ou .3dm do Rhino"
    EXPORT_EXTENSIONS = {
        "STL (*.stl)": ".stl",
        "PLY (*.ply)": ".ply",
        "VTK (*.vtk)": ".vtk",
        "VTK PolyData (*.vtp)": ".vtp",
    }
    #: Tempo que uma mensagem permanece na barra de status.
    STATUS_TIMEOUT_MS = 8000
    #: Transformações mantidas no histórico de desfazer.
    UNDO_HISTORY_LIMIT = 20
    #: Quantidade de seções transversais desenhadas na inspeção de fairness.
    SECTION_COUNT = 30

    def __init__(self) -> None:
        super().__init__()
        self._model_name = HULL_TYPE_NAMES[SEMI_DISPLACEMENT]
        self._model_kind = "Gerado no Odisseu"
        self._source_path: Path | None = None
        #: Unidade de comprimento do modelo exibido, ou ``None`` se desconhecida.
        self._model_unit: str | None = "m"
        self._nurbs_surface: EditableNurbsSurface | None = None
        self._nurbs_edit_active = False
        self._samples: list[SampledDesign] = []
        self._sample_attributes: list[str] = []
        self._worker: SamplingWorker | None = None

        self.setWindowTitle(f"{self._model_name} — Odisseu")
        self.resize(1280, 800)
        self.setMinimumSize(900, 620)
        self.setAcceptDrops(True)

        self.viewer = HullViewer(self)
        self.setCentralWidget(self.viewer)

        self.parameter_panel = ParameterPanel(self)
        self.parameter_dock = self._create_dock(
            "Parâmetros do casco", "parameterDock", self.parameter_panel, 330,
            horizontal_scroll=True,
        )
        self.attribute_panel = AttributePanel(self)
        self.attribute_dock = self._create_dock(
            "Atributos", "attributeDock", self.attribute_panel, 340
        )
        self.hydrostatic_panel = HydrostaticPanel(self)
        self.hydrostatic_dock = self._create_dock(
            "Hidrostática", "hydrostaticDock", self.hydrostatic_panel, 340
        )
        self.tabifyDockWidget(self.parameter_dock, self.attribute_dock)
        self.tabifyDockWidget(self.attribute_dock, self.hydrostatic_dock)
        self.parameter_dock.raise_()

        self.controller = HullController(self.viewer, self.parameter_panel)
        self.undo_stack = QUndoStack(self)
        # Cada comando guarda duas cópias da malha; sem teto, o histórico cresce
        # sem limite em modelos importados grandes.
        self.undo_stack.setUndoLimit(self.UNDO_HISTORY_LIMIT)
        self.controller.hull_generated.connect(self._on_parametric_hull_generated)
        self.parameter_panel.transform_requested.connect(self._apply_transform)
        self.parameter_panel.reset_requested.connect(self._restore_initial_hull)
        # Ao abrir uma malha (ou voltar ao casco paramétrico) a avaliação por
        # atributos e a hidrostática precisam acompanhar.
        self.parameter_panel.parametric_mode_changed.connect(self._on_parametric_mode_changed)
        self.attribute_panel.sample_requested.connect(self._sample_designs)
        self.attribute_panel.cancel_requested.connect(self._cancel_sampling)
        self.attribute_panel.design_selected.connect(self._show_sampled_design)
        self.hydrostatic_panel.calculate_requested.connect(self._calculate_hydrostatics)
        self.hydrostatic_panel.export_requested.connect(self._export_hydrostatics)
        self.viewer.status_message.connect(self._show_status)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self.controller.load_initial(SEMI_DISPLACEMENT)
        self.viewer.reset_view()
        self._refresh_model_info()
        self._show_status(
            "Pronto · escolha um casco inicial (SD, P, D) ou arraste uma malha 3D para a janela"
        )

    def _create_dock(
        self,
        title: str,
        name: str,
        widget,
        minimum_width: int,
        horizontal_scroll: bool = False,
    ) -> QDockWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        # A barra horizontal precisa aparecer quando o painel fica mais estreito
        # que o formulário: desligada, o conteúdo excedente ficava inacessível.
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if horizontal_scroll
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setMinimumWidth(minimum_width)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        return dock

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------
    def _icon(self, pixmap: QStyle.StandardPixmap):
        return self.style().standardIcon(pixmap)

    def _create_actions(self) -> None:
        """Cria ações reutilizadas pelos menus e pela barra de ferramentas."""
        self.new_action = QAction("Novo casco", self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.setStatusTip("Cria um casco inicial de semi-deslocamento")
        self.new_action.setIcon(self._icon(QStyle.StandardPixmap.SP_FileIcon))
        self.new_action.triggered.connect(self._new_hull)

        self.hull_type_group = QActionGroup(self)
        self.hull_type_group.setExclusive(True)
        self.hull_type_actions: dict[str, QAction] = {}
        for hull_type, label in HULL_TYPE_BUTTONS:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setToolTip(f"{HULL_TYPE_NAMES[hull_type]}: {HULL_DESCRIPTIONS[hull_type]}")
            action.setStatusTip(
                f"Carrega o casco inicial de {HULL_TYPE_NAMES[hull_type].lower()}"
            )
            action.triggered.connect(lambda _checked, kind=hull_type: self._load_initial(kind))
            self.hull_type_group.addAction(action)
            self.hull_type_actions[hull_type] = action

        self.open_action = QAction("Abrir casco...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setStatusTip(
            f"Importa uma malha {self.SUPPORTED_FORMATS_TEXT}"
        )
        self.open_action.setIcon(self._icon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.open_action.triggered.connect(self._open_hull)

        self.export_action = QAction("Exportar malha...", self)
        self.export_action.setShortcut("Ctrl+Shift+S")
        self.export_action.setStatusTip("Exporta o modelo visível para um novo arquivo")
        self.export_action.setIcon(self._icon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.export_action.triggered.connect(self._export_hull)

        self.export_hydrostatics_action = QAction("Exportar hidrostática (CSV)...", self)
        self.export_hydrostatics_action.setStatusTip(
            "Salva a tabela de hidrostática calculada em um arquivo CSV"
        )
        self.export_hydrostatics_action.triggered.connect(self._export_hydrostatics)

        self.edit_nurbs_action = QAction("Editar superfície NURBS...", self)
        self.edit_nurbs_action.setStatusTip(
            "Abre um .3dm e edita uma superfície pelos pontos de controle"
        )
        self.edit_nurbs_action.triggered.connect(self._start_nurbs_edit)

        self.finish_nurbs_action = QAction("Concluir edição de superfície", self)
        self.finish_nurbs_action.setStatusTip(
            "Sai do modo de edição e mantém o resultado como o modelo atual"
        )
        self.finish_nurbs_action.setEnabled(False)
        self.finish_nurbs_action.triggered.connect(self._finish_nurbs_edit)

        self.save_nurbs_action = QAction("Salvar superfície como .3dm...", self)
        self.save_nurbs_action.setStatusTip(
            "Salva só a superfície editada num novo arquivo .3dm"
        )
        self.save_nurbs_action.setEnabled(False)
        self.save_nurbs_action.triggered.connect(self._save_nurbs_as_3dm)

        self.draw_action = QAction("Aplicar operadores", self)
        self.draw_action.setShortcut("Ctrl+Return")
        self.draw_action.setStatusTip("Aplica os operadores de forma aos campos alterados")
        self.draw_action.setIcon(self._icon(QStyle.StandardPixmap.SP_BrowserReload))
        self.draw_action.setEnabled(self.parameter_panel.draw_button.isEnabled())
        self.draw_action.triggered.connect(self.parameter_panel.draw_requested)
        # A ação acompanha o botão: com malha importada ou nada a aplicar,
        # o atalho de teclado fica indisponível junto com ele.
        self.parameter_panel.draw_availability_changed.connect(self.draw_action.setEnabled)

        self.undo_action = self.undo_stack.createUndoAction(self, "Desfazer")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setStatusTip("Desfaz a última edição do objeto")
        self.undo_action.setIcon(self._icon(QStyle.StandardPixmap.SP_ArrowBack))

        self.redo_action = self.undo_stack.createRedoAction(self, "Refazer")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setStatusTip("Refaz a última edição desfeita")
        self.redo_action.setIcon(self._icon(QStyle.StandardPixmap.SP_ArrowForward))

        self.reset_view_action = QAction("Vista isométrica", self)
        self.reset_view_action.setShortcut("Home")
        self.reset_view_action.setStatusTip(
            "Devolve a câmera à orientação isométrica inicial"
        )
        self.reset_view_action.setIcon(self._icon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.reset_view_action.triggered.connect(self._reset_view)

        self.fit_view_action = QAction("Enquadrar modelo", self)
        self.fit_view_action.setShortcut("F")
        self.fit_view_action.setStatusTip(
            "Enquadra o modelo mantendo a orientação atual da câmera"
        )
        self.fit_view_action.setIcon(
            self._icon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        )
        self.fit_view_action.triggered.connect(self._fit_view)

        self.edges_action = self._checkable("Mostrar arestas da malha", self._toggle_edges)
        self.zebra_action = self._checkable("Listras de zebra", self._toggle_zebra)
        self.zebra_action.setStatusTip(
            "Inspeciona a suavidade e a continuidade G1 do casco com listras de zebra"
        )
        self.sections_action = self._checkable("Curvas de seção", self._toggle_overlays)
        self.sections_action.setStatusTip(
            "Mostra seções transversais; devem ser suaves e sem pontos de inflexão"
        )
        self.curves_action = self._checkable("Curvas características", self._toggle_overlays)
        self.curves_action.setStatusTip(
            "Mostra convés, quinas, quilha, roda de proa e linhas de estação"
        )
        self.polygons_action = self._checkable("Polígonos de controle", self._toggle_overlays)
        self.polygons_action.setStatusTip(
            "Mostra os polígonos de controle das curvas de Bézier"
        )
        self.curvature_action = QAction("Gráfico de curvatura...", self)
        self.curvature_action.setStatusTip(
            "Compara a curvatura das curvas antes e depois dos operadores (F)"
        )
        self.curvature_action.triggered.connect(self._show_curvature)

        self.quit_action = QAction("Sair", self)
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.triggered.connect(self.close)

        self.about_action = QAction("Sobre o Odisseu", self)
        self.about_action.triggered.connect(self._show_about)

    def _checkable(self, text: str, slot) -> QAction:
        action = QAction(text, self)
        action.setCheckable(True)
        action.toggled.connect(slot)
        return action

    def _create_menus(self) -> None:
        """Monta a barra de menus principal."""
        file_menu = self.menuBar().addMenu("Arquivo")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.export_action)
        file_menu.addAction(self.export_hydrostatics_action)
        file_menu.addSeparator()
        file_menu.addAction(self.edit_nurbs_action)
        file_menu.addAction(self.finish_nurbs_action)
        file_menu.addAction(self.save_nurbs_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        hull_menu = self.menuBar().addMenu("Casco inicial")
        for hull_type, _label in HULL_TYPE_BUTTONS:
            hull_menu.addAction(self.hull_type_actions[hull_type])
        hull_menu.addSeparator()
        hull_menu.addAction(self.draw_action)

        edit_menu = self.menuBar().addMenu("Editar")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)

        view_menu = self.menuBar().addMenu("Visualizar")
        view_menu.addAction(self.reset_view_action)
        view_menu.addAction(self.fit_view_action)
        view_menu.addSeparator()
        view_menu.addAction(self.edges_action)
        view_menu.addAction(self.zebra_action)
        view_menu.addAction(self.sections_action)
        view_menu.addAction(self.curves_action)
        view_menu.addAction(self.polygons_action)
        view_menu.addAction(self.curvature_action)
        view_menu.addSeparator()
        view_menu.addAction(self.parameter_dock.toggleViewAction())
        view_menu.addAction(self.attribute_dock.toggleViewAction())
        view_menu.addAction(self.hydrostatic_dock.toggleViewAction())

        help_menu = self.menuBar().addMenu("Ajuda")
        help_menu.addAction(self.about_action)

    def _create_toolbar(self) -> None:
        """Monta a barra de ferramentas com comandos de arquivo e vista."""
        toolbar = QToolBar("Ferramentas principais", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.export_action)
        toolbar.addSeparator()
        label = QLabel("Casco inicial:")
        label.setObjectName("secondaryText")
        toolbar.addWidget(label)
        for hull_type, _label in HULL_TYPE_BUTTONS:
            toolbar.addAction(self.hull_type_actions[hull_type])
        toolbar.addSeparator()
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.reset_view_action)
        toolbar.addAction(self.fit_view_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

    # ------------------------------------------------------------------
    # Cascos iniciais e estado paramétrico
    # ------------------------------------------------------------------
    def _load_initial(self, hull_type: str) -> None:
        """Carrega um casco inicial, descartando o modelo atual."""
        self._exit_nurbs_edit_mode()
        self.parameter_panel.set_parametric_enabled(True)
        self._reset_samples()
        self.controller.load_initial(hull_type)

    def _new_hull(self) -> None:
        """Volta ao fluxo paramétrico com o casco de semi-deslocamento."""
        self._load_initial(SEMI_DISPLACEMENT)

    def _restore_initial_hull(self) -> None:
        """Descarta as modificações e volta ao casco inicial do tipo atual."""
        model = self.controller.model
        self._load_initial(model.hull_type if model is not None else SEMI_DISPLACEMENT)

    def _on_parametric_hull_generated(self) -> None:
        """Sincroniza a interface após um novo casco paramétrico."""
        model = self.controller.model
        self._source_path = None
        self._model_name = model.name
        self._model_kind = f"Gerado no Odisseu · {HULL_TYPE_NAMES[model.hull_type]}"
        self._model_unit = "m"
        self.undo_stack.clear()
        self.parameter_panel.set_parametric_enabled(True)
        action = self.hull_type_actions.get(model.hull_type)
        if action is not None:
            action.setChecked(True)
        self._refresh_model_info()
        self._refresh_attribute_scores()
        self._refresh_overlays()
        self._refresh_hydrostatics()

    def _on_parametric_mode_changed(self, enabled: bool) -> None:
        self._refresh_attribute_scores()
        self.hydrostatic_panel.set_available(enabled)
        if not enabled:
            self._clear_overlays()

    def _refresh_attribute_scores(self) -> None:
        """Reavalia os modelos de atributo com o casco atual."""
        model = self.controller.model
        if not self.parameter_panel.is_parametric_enabled() or model is None:
            self.attribute_panel.set_scores(None)
            return
        design = HullDesign.from_parameters(model.parameters())
        self.attribute_panel.set_scores(evaluate_attributes(design))

    # ------------------------------------------------------------------
    # Amostragem por atributos
    # ------------------------------------------------------------------
    def _reset_samples(self) -> None:
        self._samples = []
        self._sample_attributes = []
        self.attribute_panel.set_samples([])

    def _sample_designs(
        self, attributes: list[str], count: int, preference: str, population: int
    ) -> None:
        """Executa o S-TLBO em segundo plano e exibe o primeiro projeto amostrado."""
        if self._worker is not None:
            return
        self._worker = SamplingWorker(attributes, count, preference, population, self)
        self._worker.progress.connect(self.attribute_panel.set_progress)
        self._worker.sampled.connect(lambda samples: self._on_sampled(samples, attributes))
        self._worker.failed.connect(self._on_sampling_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self.attribute_panel.set_sampling(True)
        self._show_status("Amostrando projetos com S-TLBO...")
        self._worker.start()

    def _cancel_sampling(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._show_status("Cancelando a amostragem...")

    def _on_worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        self._worker = None
        self.attribute_panel.set_sampling(False)

    def _on_sampling_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Amostragem inválida", message)
        self._show_status("Amostragem cancelada")

    def _on_sampled(self, samples: list[SampledDesign], attributes: list[str]) -> None:
        self._samples = samples
        self._sample_attributes = attributes
        self.attribute_panel.set_samples(samples)
        infeasible = sum(not sample.feasible for sample in samples)
        if infeasible:
            self._show_status(
                f"{len(samples)} projetos amostrados · {infeasible} não atenderam "
                "a todas as restrições"
            )
        else:
            self._show_status(f"{len(samples)} projetos amostrados")
        if samples:
            self._show_sampled_design(0)

    def _show_sampled_design(self, index: int) -> None:
        """Constrói o casco do projeto amostrado e o exibe."""
        if not 0 <= index < len(self._samples):
            return
        self._exit_nurbs_edit_mode()
        design = self._samples[index].design
        names = " + ".join(
            ATTRIBUTES_BY_KEY[key].label.split(" (")[0] for key in self._sample_attributes
        )
        try:
            model = build_hull(
                design.to_parameters(),
                SEMI_DISPLACEMENT,
                f"Amostra {index + 1} · {names}",
            )
        except ValueError as error:
            QMessageBox.warning(self, "Projeto inválido", str(error))
            return
        self.parameter_panel.set_parametric_enabled(True)
        self.controller.set_model(model, fit=True)

    # ------------------------------------------------------------------
    # Hidrostática
    # ------------------------------------------------------------------
    def _refresh_hydrostatics(self) -> None:
        """Atualiza os calados e, se já havia resultado, recalcula a tabela."""
        model = self.controller.model
        if model is None or not self.parameter_panel.is_parametric_enabled():
            return
        had_results = bool(self.hydrostatic_panel.results())
        if not had_results:
            self.hydrostatic_panel.set_default_drafts(default_drafts(model))
            return
        self._calculate_hydrostatics(self.hydrostatic_panel.drafts())

    def _calculate_hydrostatics(self, drafts: list[float]) -> None:
        model = self.controller.model
        if model is None or not self.parameter_panel.is_parametric_enabled():
            return
        try:
            results = hydrostatic_table(model, drafts)
        except ValueError as error:
            self.hydrostatic_panel.clear_results()
            self.hydrostatic_panel.show_message(str(error), "error")
            return
        self.hydrostatic_panel.set_results(results)
        self.hydrostatic_panel.show_message(
            f"Hidrostática calculada para {len(results)} calados.", "valid"
        )

    def _export_hydrostatics(self) -> None:
        results = self.hydrostatic_panel.results()
        if not results:
            QMessageBox.information(
                self,
                "Hidrostática",
                "Calcule a hidrostática antes de exportar a tabela.",
            )
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar hidrostática", f"{self._model_name}_hidrostatica.csv", "CSV (*.csv)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["Propriedade", "Unidade", *[f"T{i + 1}" for i in range(len(results))]])
                for name, (label, unit) in COLUMN_INFO.items():
                    writer.writerow(
                        [f"{name} · {label}", unit, *[f"{getattr(r, name):.6g}" for r in results]]
                    )
        except OSError as error:
            self._show_error("Não foi possível exportar", "A tabela não pôde ser salva.", error)
            return
        self._show_status(f"“{Path(file_path).name}” foi exportado com sucesso")

    # ------------------------------------------------------------------
    # Inspeção de fairness
    # ------------------------------------------------------------------
    def _toggle_edges(self, enabled: bool) -> None:
        self.viewer.set_show_edges(enabled)

    def _toggle_zebra(self, enabled: bool) -> None:
        self.viewer.set_zebra(enabled)

    def _toggle_overlays(self, _checked: bool = False) -> None:
        self._refresh_overlays()

    def _clear_overlays(self) -> None:
        for name in ("sections", "curves", "polygons"):
            self.viewer.set_overlay(name, None)

    def _refresh_overlays(self) -> None:
        """Redesenha as sobreposições ligadas, para o casco atual."""
        model = self.controller.model
        if model is None or not self.parameter_panel.is_parametric_enabled():
            self._clear_overlays()
            return

        def mirrored(curves: dict[str, np.ndarray]) -> list[np.ndarray]:
            lines = []
            for points in curves.values():
                lines.append(points)
                other = points.copy()
                other[:, 1] *= -1.0
                lines.append(other)
            return lines

        if self.sections_action.isChecked():
            sections = model.section_polylines(self.SECTION_COUNT)
            self.viewer.set_overlay(
                "sections", [np.concatenate(sections)] if sections else None, "#7bd88f", 1.5
            )
        else:
            self.viewer.set_overlay("sections", None)
        if self.curves_action.isChecked():
            self.viewer.set_overlay("curves", mirrored(model.feature_curves()), "#ffd166", 3.0)
        else:
            self.viewer.set_overlay("curves", None)
        if self.polygons_action.isChecked():
            self.viewer.set_overlay(
                "polygons", mirrored(model.control_polygons()), "#ff6b6b", 1.5
            )
        else:
            self.viewer.set_overlay("polygons", None)

    def _show_curvature(self) -> None:
        model = self.controller.model
        if model is None or not self.parameter_panel.is_parametric_enabled():
            QMessageBox.information(
                self,
                "Gráfico de curvatura",
                "O gráfico de curvatura só se aplica a cascos paramétricos.",
            )
            return
        previous = self.controller.previous or model
        CurvatureDialog(previous, model, self).exec()

    # ------------------------------------------------------------------
    # Arquivos
    # ------------------------------------------------------------------
    def _open_hull(self) -> None:
        """Seleciona e importa um arquivo de malha 3D."""
        patterns = " ".join(f"*{extension}" for extension in self.SUPPORTED_MESH_EXTENSIONS)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir casco",
            "",
            f"Malhas 3D ({patterns});;Todos os arquivos (*)",
        )
        if file_path:
            self._load_hull_path(Path(file_path))

    def _load_hull_path(self, file_path: Path) -> None:
        """Executa a importação com mensagens compreensíveis para o usuário."""
        if file_path.suffix.lower() not in self.SUPPORTED_MESH_EXTENSIONS:
            QMessageBox.warning(
                self,
                "Formato não suportado",
                f"Escolha um arquivo {self.SUPPORTED_FORMATS_TEXT}.",
            )
            return

        self._show_busy_status(f"Abrindo {file_path.name}...")
        report: RhinoImportReport | None = None
        try:
            if file_path.suffix.lower() == ".3dm":
                polydata, report = read_3dm_as_polydata(file_path)
                mesh = HullViewer.displayable(polydata)
            else:
                mesh = HullViewer.read_mesh_file(file_path)
        except Exception as error:  # PyVista/VTK/rhino3dm usam exceções próprias por leitor.
            self._show_error(
                "Não foi possível abrir o modelo",
                f"O arquivo “{file_path.name}” não pôde ser lido.",
                error,
            )
            self._show_status("Falha ao abrir o modelo")
            return

        # Só agora o modelo atual é descartado: uma leitura que falha não pode
        # encerrar uma edição de superfície que ainda estava em andamento.
        self._exit_nurbs_edit_mode()
        self.viewer.set_mesh(mesh, hull=False)
        self._source_path = file_path
        self._model_name = file_path.stem
        self._model_kind = f"Malha {file_path.suffix[1:].upper()} importada"
        # Só o .3dm declara a unidade; STL, OBJ e afins guardam números puros.
        self._model_unit = report.unit if report is not None else None
        self.undo_stack.clear()
        self.parameter_panel.set_parametric_enabled(False)
        self.hull_type_group.setExclusive(False)
        for action in self.hull_type_actions.values():
            action.setChecked(False)
        self.hull_type_group.setExclusive(True)
        self.viewer.reset_view()
        self._refresh_model_info()
        if report is not None and report.has_omissions:
            QMessageBox.information(
                self, "Importado com ressalvas", report.describe_omissions()
            )
        detail = f" · {report.summary()}" if report is not None else ""
        self._show_status(f"“{file_path.name}” foi importado com sucesso{detail}")

    def _export_hull(self) -> None:
        """Exporta a superfície atual sem alterar o arquivo de origem."""
        default_name = f"{self._model_name}_exportado.stl"
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exportar malha",
            default_name,
            ";;".join(self.EXPORT_EXTENSIONS),
        )
        if not file_path:
            return

        output_path = self._path_with_selected_extension(
            Path(file_path), selected_filter
        )
        try:
            self.viewer.save_mesh(output_path)
        except Exception as error:
            self._show_error(
                "Não foi possível exportar",
                f"O modelo não pôde ser salvo em “{output_path.name}”. "
                "Confira a extensão escolhida e a permissão de escrita na pasta.",
                error,
            )
            self._show_status("Falha ao exportar o modelo")
            return

        self._show_status(f"“{output_path.name}” foi exportado com sucesso")

    @classmethod
    def _path_with_selected_extension(cls, path: Path, selected_filter: str) -> Path:
        """Garante uma extensão de malha válida no arquivo de saída.

        Nomes com ponto no meio, como ``casco v1.2``, têm sufixo mas não têm
        extensão de malha; nesse caso a extensão do filtro é acrescentada em
        vez de substituir o trecho digitado.
        """
        extension = cls.EXPORT_EXTENSIONS.get(selected_filter, ".stl")
        if path.suffix.lower() in cls.EXPORT_EXTENSIONS.values():
            return path
        if not path.suffix:
            return path.with_suffix(extension)
        return path.with_name(path.name + extension)

    # ------------------------------------------------------------------
    # Edição de superfície NURBS
    # ------------------------------------------------------------------
    def _start_nurbs_edit(self) -> None:
        """Abre um .3dm, deixa escolher uma superfície e entra no modo de edição."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Abrir .3dm para editar", "", "Arquivos Rhino (*.3dm)"
        )
        if not file_path:
            return

        try:
            candidates = list_editable_surfaces(file_path)
        except NurbsSurfaceError as error:
            self._show_error("Não foi possível abrir o arquivo", str(error), error)
            return

        if not candidates:
            QMessageBox.information(
                self,
                "Nenhuma superfície editável",
                "Este arquivo não tem nenhuma superfície com forma NURBS "
                "reconhecível. Curvas soltas e malhas sem Brep não têm "
                "pontos de controle para editar.",
            )
            return

        dialog = NurbsFaceSelectionDialog(candidates, self)
        if dialog.exec() != NurbsFaceSelectionDialog.DialogCode.Accepted:
            return
        face_index = dialog.selected_face_index()
        if face_index is None:
            return

        try:
            surface = EditableNurbsSurface.from_3dm_face(file_path, face_index)
        except NurbsSurfaceError as error:
            self._show_error("Não foi possível carregar a superfície", str(error), error)
            return

        self._exit_nurbs_edit_mode()
        self._nurbs_surface = surface
        self._nurbs_edit_active = True
        self._source_path = Path(file_path)
        self._model_name = f"{Path(file_path).stem} (editando NURBS)"
        self._model_kind = "Superfície NURBS em edição"
        self._model_unit = surface.unit

        # Uma transformação rígida aplicada durante a edição seria desfeita
        # sem aviso no próximo arraste, porque a retesselação sempre parte
        # das coordenadas originais da superfície: as duas edições não se
        # compõem neste MVP, então mantemos só uma disponível por vez.
        self.parameter_panel.set_transform_enabled(False)
        self.parameter_panel.set_parametric_enabled(False)
        self.undo_stack.clear()
        self._refresh_nurbs_preview()
        self._show_control_point_handles()
        self._refresh_model_info()

        self.finish_nurbs_action.setEnabled(True)
        self.save_nurbs_action.setEnabled(True)
        self._show_status(
            "Editando pontos de controle · arraste as esferas na cena 3D "
            "para remodelar a superfície"
        )

    def _refresh_nurbs_preview(self) -> None:
        """Retesela a superfície atual e substitui a malha exibida por ela."""
        mesh = self._nurbs_surface.tessellate()
        self.viewer.set_mesh(pv.PolyData(mesh.vertices, mesh.pyvista_faces), hull=False)

    def _show_control_point_handles(self) -> None:
        points = self._nurbs_surface.control_points().reshape(-1, 3)
        self.viewer.show_control_point_handles(points, self._on_control_point_moved)
        self.viewer.reset_view()

    def _on_control_point_moved(self, index: int, new_position: tuple[float, float, float]) -> None:
        """Aplica o arraste de uma alça: move o CV e retesela ao vivo.

        Só a posição dos pontos muda a cada arraste — a topologia da malha de
        exibição é sempre a mesma —, então atualizamos os pontos no lugar em
        vez de reconstruir o ator inteiro, para o arraste ficar fluido.
        """
        if self._nurbs_surface is None:
            return
        self._nurbs_surface.move_control_point_flat(index, new_position)
        mesh = self._nurbs_surface.tessellate()
        try:
            self.viewer.update_current_mesh_points(mesh.vertices)
        except ValueError:
            # A malha exibida não é a que esperávamos (não deveria acontecer
            # em uso normal); refaz o ator do zero para não travar a edição.
            self.viewer.set_mesh(pv.PolyData(mesh.vertices, mesh.pyvista_faces), hull=False)

    def _finish_nurbs_edit(self) -> None:
        """Sai do modo de edição, mantendo o resultado como o modelo atual."""
        if not self._nurbs_edit_active:
            return
        self.viewer.clear_control_point_handles()
        self._nurbs_edit_active = False
        # A malha exibida passa a ser o resultado; a superfície não é mais
        # editável nem salvável como .3dm, então não precisa ficar na memória.
        self._nurbs_surface = None
        self.finish_nurbs_action.setEnabled(False)
        self.save_nurbs_action.setEnabled(False)
        self.parameter_panel.set_transform_enabled(True)
        if self._source_path is not None:
            self._model_name = f"{self._source_path.stem} (NURBS editado)"
        self._model_kind = "Superfície NURBS editada"
        self.viewer.reset_view()
        self._refresh_model_info()
        self._show_status("Edição concluída · use “Exportar malha” para salvar o resultado")

    def _save_nurbs_as_3dm(self) -> None:
        """Salva só a superfície editada, como um novo arquivo .3dm."""
        if self._nurbs_surface is None:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar superfície como .3dm", "superficie_editada.3dm", "Arquivos Rhino (*.3dm)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".3dm"):
            file_path += ".3dm"
        try:
            self._nurbs_surface.save_to_3dm(file_path)
        except Exception as error:
            self._show_error("Não foi possível salvar", "A superfície não pôde ser salva.", error)
            return
        self._show_status(
            f"Superfície salva em “{Path(file_path).name}” "
            "(arquivo novo, só com esta superfície)"
        )

    def _exit_nurbs_edit_mode(self) -> None:
        """Encerra a edição de NURBS sem preservar o resultado, se estiver ativa.

        Chamado antes de trocar de modelo por qualquer outro caminho (novo
        casco, abrir outro arquivo), para não deixar alças órfãs na cena
        apontando para uma superfície que já não é mais a atual.
        """
        if not self._nurbs_edit_active:
            return
        self.viewer.clear_control_point_handles()
        self._nurbs_edit_active = False
        self._nurbs_surface = None
        self.finish_nurbs_action.setEnabled(False)
        self.save_nurbs_action.setEnabled(False)
        self.parameter_panel.set_transform_enabled(True)

    # ------------------------------------------------------------------
    # Modelo e histórico
    # ------------------------------------------------------------------
    def _apply_transform(self, parameters: TransformParameters) -> None:
        """Registra uma transformação reversível sobre o objeto atual."""
        try:
            matrix = transformation_matrix(parameters, self.viewer.mesh_center())
            command = TransformMeshCommand(
                self.viewer,
                matrix,
                self._after_geometry_change,
            )
        except ValueError as error:
            QMessageBox.warning(self, "Transformação inválida", str(error))
            return
        self.undo_stack.push(command)

    def _after_geometry_change(self, message: str) -> None:
        """Mantém visualização e informações sincronizadas após undo/redo.

        A câmera não é redefinida aqui: reenquadrar a cada transformação
        descartaria o ponto de vista que o usuário acabou de escolher.
        """
        self.viewer.render()
        self._refresh_model_info()
        self._show_status(message)

    def _refresh_model_info(self) -> None:
        """Atualiza título e resumo sem duplicar a geometria na camada de UI."""
        summary = self.viewer.mesh_summary()
        if summary is None:
            return
        self.parameter_panel.set_model_info(
            self._model_name,
            self._model_kind,
            summary.points,
            summary.cells,
            summary.dimensions,
            self._model_unit or "unidades do arquivo",
        )
        self.parameter_panel.set_length_unit(self._model_unit)
        # Sem arquivo de origem, o modelo é o casco gerado aqui, com proa em +X.
        self.viewer.set_axis_titles(
            self._model_unit, hull_axes=self._source_path is None
        )
        self.setWindowTitle(f"{self._model_name} — Odisseu")

    # ------------------------------------------------------------------
    # Arrastar e soltar
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Aceita arquivos de malha arrastados para a janela."""
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        if any(path.suffix.lower() in self.SUPPORTED_MESH_EXTENSIONS for path in paths):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """Abre a primeira malha válida solta sobre a aplicação."""
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in self.SUPPORTED_MESH_EXTENSIONS:
                self._load_hull_path(path)
                event.acceptProposedAction()
                return
        self._show_status(
            "Nenhum arquivo solto tem formato suportado "
            f"({self.SUPPORTED_FORMATS_TEXT})"
        )

    # ------------------------------------------------------------------
    # Vista e mensagens
    # ------------------------------------------------------------------
    def _reset_view(self) -> None:
        """Restaura a orientação isométrica da câmera."""
        self.viewer.reset_view()
        self._show_status("Vista isométrica restaurada")

    def _fit_view(self) -> None:
        """Reenquadra o modelo mantendo a orientação escolhida pelo usuário."""
        self.viewer.fit_view()
        self._show_status("Modelo enquadrado na orientação atual")

    def _show_status(self, message: str) -> None:
        """Publica uma mensagem temporária, que não sobrevive ao contexto."""
        self.statusBar().showMessage(message, self.STATUS_TIMEOUT_MS)

    def _show_busy_status(self, message: str) -> None:
        """Mostra uma mensagem antes de uma operação que bloqueia a interface.

        Sem o repaint, a mensagem só seria desenhada depois da operação, quando
        já tivesse sido substituída pelo resultado.
        """
        self.statusBar().showMessage(message)
        self.statusBar().repaint()

    def _show_error(self, title: str, message: str, error: Exception) -> None:
        """Mostra um erro legível, com o detalhe técnico em segundo plano."""
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setDetailedText(f"{type(error).__name__}: {error}")
        dialog.exec()

    def _show_about(self) -> None:
        """Exibe informações básicas sobre a versão estrutural."""
        QMessageBox.information(
            self,
            "Sobre o Odisseu",
            "Odisseu · MVP\n\n"
            "Modelagem paramétrica e por atributos de cascos de iates, "
            "segundo o ModiYacht (Khan, 2017): operadores de forma com "
            "abordagem iterativa, amostragem S-TLBO e hidrostática.\n"
            "Suporta importação e exportação de malhas 3D.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Encerra a amostragem e o renderizador VTK antes de fechar a janela."""
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(5000)
        self.viewer.close()
        super().closeEvent(event)
