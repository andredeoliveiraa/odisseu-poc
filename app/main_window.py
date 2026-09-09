"""Janela principal e comandos de alto nível da aplicação."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QComboBox,
    QFileDialog,
    QFrame,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QStyle,
    QToolBar,
)

from app.commands.mesh_commands import TransformMeshCommand
from app.controllers.hull_controller import HullController
from app.models.transforms import TransformParameters, transformation_matrix
from app.models.profiles import HULL_PROFILES
from app.visualization import HullViewer
from app.views.parameter_panel import ParameterPanel


class MainWindow(QMainWindow):
    """Janela principal do Odisseu.

    A janela coordena a navegação da aplicação, enquanto a geometria e o
    renderizador ficam isolados em :class:`HullViewer`.
    """

    SUPPORTED_MESH_EXTENSIONS = {".stl", ".obj", ".ply", ".vtk", ".vtp"}

    def __init__(self) -> None:
        super().__init__()
        self._model_name = "Casco paramétrico"
        self._model_kind = "Gerado no Odisseu"
        self._source_path: Path | None = None
        self._active_profile_name = "Usual (Comum)"

        self.setWindowTitle("Casco paramétrico — Odisseu")
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        self.setAcceptDrops(True)

        self.viewer = HullViewer(self)
        self.setCentralWidget(self.viewer)
        self.parameter_panel = ParameterPanel(self)

        parameter_scroll = QScrollArea(self)
        parameter_scroll.setWidgetResizable(True)
        parameter_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        parameter_scroll.setFrameShape(QFrame.Shape.NoFrame)
        parameter_scroll.setWidget(self.parameter_panel)

        self.parameter_dock = QDockWidget("Parâmetros do casco", self)
        self.parameter_dock.setObjectName("parameterDock")
        self.parameter_dock.setMinimumWidth(340)
        self.parameter_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.parameter_dock.setWidget(parameter_scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.parameter_dock)

        self.controller = HullController(self.viewer, self.parameter_panel)
        self.undo_stack = QUndoStack(self)
        self.controller.hull_generated.connect(self._on_parametric_hull_generated)
        self.parameter_panel.transform_requested.connect(self._apply_transform)
        self.viewer.status_message.connect(self.statusBar().showMessage)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._select_profile_by_name(self._active_profile_name)
        self._refresh_model_info()
        self.statusBar().showMessage(
            "Pronto · ajuste os parâmetros ou arraste uma malha 3D para a janela"
        )

    def _create_actions(self) -> None:
        """Cria ações reutilizadas pelos menus e pela barra de ferramentas."""
        self.new_action = QAction("Novo casco", self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.setStatusTip("Cria um novo casco com os parâmetros iniciais")
        self.new_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        self.new_action.triggered.connect(self._new_hull)

        self.open_action = QAction("Abrir casco...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setStatusTip("Importa uma malha STL, OBJ, PLY ou VTK")
        self.open_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.open_action.triggered.connect(self._open_hull)

        self.export_action = QAction("Exportar malha...", self)
        self.export_action.setShortcut("Ctrl+Shift+S")
        self.export_action.setStatusTip("Exporta o modelo visível para um novo arquivo")
        self.export_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.export_action.triggered.connect(self._export_hull)

        self.undo_action = self.undo_stack.createUndoAction(self, "Desfazer")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setStatusTip("Desfaz a última edição do objeto")

        self.redo_action = self.undo_stack.createRedoAction(self, "Refazer")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setStatusTip("Refaz a última edição desfeita")

        self.reset_view_action = QAction("Redefinir vista", self)
        self.reset_view_action.setShortcut("Home")
        self.reset_view_action.setStatusTip("Volta a câmera à orientação inicial")
        self.reset_view_action.triggered.connect(self._reset_view)

        self.fit_view_action = QAction("Ajustar modelo", self)
        self.fit_view_action.setShortcut("F")
        self.fit_view_action.setStatusTip("Enquadra todo o modelo na janela")
        self.fit_view_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.fit_view_action.triggered.connect(self._fit_view)

        self.quit_action = QAction("Sair", self)
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.triggered.connect(self.close)

        self.about_action = QAction("Sobre o Odisseu", self)
        self.about_action.triggered.connect(self._show_about)

    def _create_menus(self) -> None:
        """Monta a barra de menus principal."""
        file_menu = self.menuBar().addMenu("Arquivo")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = self.menuBar().addMenu("Editar")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)

        view_menu = self.menuBar().addMenu("Visualizar")
        view_menu.addAction(self.reset_view_action)
        view_menu.addAction(self.fit_view_action)
        view_menu.addSeparator()
        view_menu.addAction(self.parameter_dock.toggleViewAction())

        help_menu = self.menuBar().addMenu("Ajuda")
        help_menu.addAction(self.about_action)

    def _create_toolbar(self) -> None:
        """Monta a barra de ferramentas com comandos de visualização."""
        toolbar = QToolBar("Ferramentas principais", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.export_action)
        toolbar.addSeparator()
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.reset_view_action)
        toolbar.addAction(self.fit_view_action)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Perfil:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(210)
        self.profile_combo.setToolTip("Escolha um preset; os parâmetros continuam editáveis no painel.")
        self.profile_combo.addItems([profile.name for profile in HULL_PROFILES])
        self.profile_combo.currentIndexChanged.connect(self._select_profile)
        toolbar.addWidget(self.profile_combo)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

    def _select_profile(self, index: int) -> None:
        if 0 <= index < len(HULL_PROFILES):
            profile = HULL_PROFILES[index]
            self._active_profile_name = profile.name
            self.parameter_panel.set_profile_values(profile)
            self.parameter_panel.set_parametric_enabled(True)
            self.controller.draw()

    def _select_profile_by_name(self, name: str) -> None:
        index = next((i for i, profile in enumerate(HULL_PROFILES) if profile.name == name), 0)
        self.profile_combo.blockSignals(True)
        self.profile_combo.setCurrentIndex(index)
        self.profile_combo.blockSignals(False)
        self._select_profile(index)

    def _open_hull(self) -> None:
        """Seleciona e importa um arquivo de malha 3D."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir casco",
            "",
            "Malhas 3D (*.stl *.obj *.ply *.vtk *.vtp);;Todos os arquivos (*)",
        )
        if file_path:
            self._load_hull_path(Path(file_path))

    def _load_hull_path(self, file_path: Path) -> None:
        """Executa a importação com mensagens compreensíveis para o usuário."""
        if file_path.suffix.lower() not in self.SUPPORTED_MESH_EXTENSIONS:
            QMessageBox.warning(
                self,
                "Formato não suportado",
                "Escolha uma malha STL, OBJ, PLY, VTK ou VTP.",
            )
            return

        self.statusBar().showMessage(f"Abrindo {file_path.name}...")
        try:
            self.viewer.load_mesh(file_path)
        except Exception as error:  # PyVista/VTK usa exceções específicas por leitor.
            QMessageBox.critical(
                self,
                "Não foi possível abrir o modelo",
                f"O arquivo “{file_path.name}” não pôde ser lido.\n\n{error}",
            )
            self.statusBar().showMessage("Falha ao abrir o modelo")
            return

        self._source_path = file_path
        self._model_name = file_path.stem
        self._model_kind = f"Malha {file_path.suffix[1:].upper()} importada"
        self.undo_stack.clear()
        self.parameter_panel.set_parametric_enabled(False)
        self.viewer.reset_camera()
        self.viewer.render()
        self._refresh_model_info()
        self.statusBar().showMessage(
            f"“{file_path.name}” foi importado com sucesso"
        )

    def _export_hull(self) -> None:
        """Exporta a superfície atual sem alterar o arquivo de origem."""
        default_name = f"{self._model_name}_exportado.stl"
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exportar malha",
            default_name,
            "STL (*.stl);;PLY (*.ply);;VTK (*.vtk);;VTK PolyData (*.vtp)",
        )
        if not file_path:
            return

        output_path = self._path_with_selected_extension(
            Path(file_path), selected_filter
        )
        try:
            self.viewer.save_mesh(output_path)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Não foi possível exportar",
                f"O modelo não pôde ser salvo em “{output_path.name}”.\n\n{error}",
            )
            self.statusBar().showMessage("Falha ao exportar o modelo")
            return

        self.statusBar().showMessage(
            f"“{output_path.name}” foi exportado com sucesso"
        )

    @staticmethod
    def _path_with_selected_extension(path: Path, selected_filter: str) -> Path:
        """Acrescenta a extensão do filtro quando ela não foi digitada."""
        if path.suffix:
            return path
        extensions = {
            "STL (*.stl)": ".stl",
            "PLY (*.ply)": ".ply",
            "VTK (*.vtk)": ".vtk",
            "VTK PolyData (*.vtp)": ".vtp",
        }
        return path.with_suffix(extensions.get(selected_filter, ".stl"))

    def _new_hull(self) -> None:
        """Volta ao fluxo paramétrico e cria um casco com valores iniciais."""
        self.parameter_panel.set_parametric_enabled(True)
        self.parameter_panel.reset_defaults()
        self._active_profile_name = "Usual (Comum)"
        self._select_profile_by_name(self._active_profile_name)

    def _on_parametric_hull_generated(self) -> None:
        """Sincroniza a interface após um recálculo paramétrico."""
        self._source_path = None
        self._model_name = self._active_profile_name
        self._model_kind = "Gerado no Odisseu"
        self.undo_stack.clear()
        self.parameter_panel.set_parametric_enabled(True)
        self._refresh_model_info()

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
        """Mantém visualização e informações sincronizadas após undo/redo."""
        self.viewer.reset_camera()
        self.viewer.render()
        self._refresh_model_info()
        self.statusBar().showMessage(message)

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
            "m" if self._source_path is None else "unidades do arquivo",
        )
        self.setWindowTitle(f"{self._model_name} — Odisseu")

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

    def _reset_view(self) -> None:
        """Restaura a câmera para a orientação inicial."""
        self.viewer.reset_camera()
        self.viewer.render()
        self.statusBar().showMessage("Vista redefinida")

    def _fit_view(self) -> None:
        """Enquadra todos os atores visíveis na janela."""
        self.viewer.reset_camera()
        self.viewer.render()
        self.statusBar().showMessage("Modelo ajustado à vista")

    def _show_about(self) -> None:
        """Exibe informações básicas sobre a versão estrutural."""
        QMessageBox.information(
            self,
            "Sobre o Odisseu",
            "Odisseu · MVP\n\n"
            "Modelagem paramétrica e visualização de cascos.\n"
            "Suporta importação e exportação de malhas 3D.",
        )
