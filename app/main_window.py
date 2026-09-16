"""Janela principal e comandos de alto nível da aplicação."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
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
from app.models.profiles import CUSTOM_PROFILE_NAME, DEFAULT_PROFILE, HULL_PROFILES
from app.visualization import HullViewer
from app.views.parameter_panel import ParameterPanel


class MainWindow(QMainWindow):
    """Janela principal do Odisseu.

    A janela coordena a navegação da aplicação, enquanto a geometria e o
    renderizador ficam isolados em :class:`HullViewer`.
    """

    SUPPORTED_MESH_EXTENSIONS = {".stl", ".obj", ".ply", ".vtk", ".vtp"}
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

    def __init__(self) -> None:
        super().__init__()
        self._model_name = DEFAULT_PROFILE.name
        self._model_kind = "Gerado no Odisseu"
        self._source_path: Path | None = None

        self.setWindowTitle(f"{DEFAULT_PROFILE.name} — Odisseu")
        self.resize(1280, 800)
        self.setMinimumSize(900, 620)
        self.setAcceptDrops(True)

        self.viewer = HullViewer(self)
        self.setCentralWidget(self.viewer)
        self.parameter_panel = ParameterPanel(self)

        parameter_scroll = QScrollArea(self)
        parameter_scroll.setWidgetResizable(True)
        # A barra horizontal precisa aparecer quando o painel fica mais estreito
        # que o formulário: desligada, o conteúdo excedente ficava inacessível.
        parameter_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        parameter_scroll.setFrameShape(QFrame.Shape.NoFrame)
        parameter_scroll.setWidget(self.parameter_panel)

        self.parameter_dock = QDockWidget("Parâmetros do casco", self)
        self.parameter_dock.setObjectName("parameterDock")
        self.parameter_dock.setMinimumWidth(300)
        self.parameter_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.parameter_dock.setWidget(parameter_scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.parameter_dock)

        self.controller = HullController(self.viewer, self.parameter_panel)
        self.undo_stack = QUndoStack(self)
        # Cada comando guarda duas cópias da malha; sem teto, o histórico cresce
        # sem limite em modelos importados grandes.
        self.undo_stack.setUndoLimit(self.UNDO_HISTORY_LIMIT)
        self.controller.hull_generated.connect(self._on_parametric_hull_generated)
        self.parameter_panel.transform_requested.connect(self._apply_transform)
        self.parameter_panel.parameters_changed.connect(self._on_parameters_edited)
        self.viewer.status_message.connect(self._show_status)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._select_profile_by_name(DEFAULT_PROFILE.name)
        self._refresh_model_info()
        self._show_status(
            "Pronto · ajuste os parâmetros ou arraste uma malha 3D para a janela"
        )

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------
    def _icon(self, pixmap: QStyle.StandardPixmap):
        return self.style().standardIcon(pixmap)

    def _create_actions(self) -> None:
        """Cria ações reutilizadas pelos menus e pela barra de ferramentas."""
        self.new_action = QAction("Novo casco", self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.setStatusTip(
            f"Cria um casco novo com o perfil {DEFAULT_PROFILE.name}"
        )
        self.new_action.setIcon(self._icon(QStyle.StandardPixmap.SP_FileIcon))
        self.new_action.triggered.connect(self._new_hull)

        self.open_action = QAction("Abrir casco...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setStatusTip("Importa uma malha STL, OBJ, PLY ou VTK")
        self.open_action.setIcon(self._icon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.open_action.triggered.connect(self._open_hull)

        self.export_action = QAction("Exportar malha...", self)
        self.export_action.setShortcut("Ctrl+Shift+S")
        self.export_action.setStatusTip("Exporta o modelo visível para um novo arquivo")
        self.export_action.setIcon(self._icon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.export_action.triggered.connect(self._export_hull)

        self.draw_action = QAction("Atualizar modelo 3D", self)
        self.draw_action.setShortcut("Ctrl+Return")
        self.draw_action.setStatusTip("Recalcula a malha com os parâmetros atuais")
        self.draw_action.setIcon(self._icon(QStyle.StandardPixmap.SP_BrowserReload))
        self.draw_action.setEnabled(self.parameter_panel.draw_button.isEnabled())
        self.draw_action.triggered.connect(self.parameter_panel.draw_requested)
        # A ação acompanha o botão: com malha importada ou parâmetro inválido,
        # o atalho de teclado fica indisponível junto com ele.
        self.parameter_panel.draw_availability_changed.connect(
            self.draw_action.setEnabled
        )

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
        edit_menu.addSeparator()
        edit_menu.addAction(self.draw_action)

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
        profile_label = QLabel("Perfil:")
        profile_label.setObjectName("secondaryText")
        toolbar.addWidget(profile_label)
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(210)
        self.profile_combo.setAccessibleName("Perfil de casco")
        self.profile_combo.setToolTip(
            "Escolha um preset; os parâmetros continuam editáveis no painel."
        )
        self.profile_combo.addItems([profile.name for profile in HULL_PROFILES])
        # Entrada final usada quando os campos não correspondem a nenhum preset.
        self.profile_combo.addItem(CUSTOM_PROFILE_NAME)
        self.profile_combo.currentIndexChanged.connect(self._select_profile)
        toolbar.addWidget(self.profile_combo)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

    # ------------------------------------------------------------------
    # Perfis e sincronia do formulário
    # ------------------------------------------------------------------
    def _select_profile(self, index: int) -> None:
        """Aplica um preset e redesenha; a entrada final não altera valores."""
        if not 0 <= index < len(HULL_PROFILES):
            return
        profile = HULL_PROFILES[index]
        self.parameter_panel.set_parametric_enabled(True)
        self.parameter_panel.set_profile_values(profile)
        self.controller.draw()

    def _select_profile_by_name(self, name: str) -> None:
        index = self.profile_combo.findText(name)
        if index < 0:
            index = HULL_PROFILES.index(DEFAULT_PROFILE)
        self.profile_combo.blockSignals(True)
        self.profile_combo.setCurrentIndex(index)
        self.profile_combo.blockSignals(False)
        self._select_profile(index)

    def _on_parameters_edited(self) -> None:
        """Mantém o seletor de perfil honesto quando os campos mudam.

        Editar um campo à mão deixa de corresponder ao preset exibido, então o
        seletor passa a mostrar “Personalizado”.
        """
        matched = next(
            (
                position
                for position, profile in enumerate(HULL_PROFILES)
                if self.parameter_panel.matches_profile(profile)
            ),
            self.profile_combo.count() - 1,
        )
        if self.profile_combo.currentIndex() == matched:
            return
        self.profile_combo.blockSignals(True)
        self.profile_combo.setCurrentIndex(matched)
        self.profile_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Arquivos
    # ------------------------------------------------------------------
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

        self._show_status(f"Abrindo {file_path.name}...")
        try:
            self.viewer.load_mesh(file_path)
        except Exception as error:  # PyVista/VTK usa exceções específicas por leitor.
            self._show_error(
                "Não foi possível abrir o modelo",
                f"O arquivo “{file_path.name}” não pôde ser lido.",
                error,
            )
            self._show_status("Falha ao abrir o modelo")
            return

        self._source_path = file_path
        self._model_name = file_path.stem
        self._model_kind = f"Malha {file_path.suffix[1:].upper()} importada"
        self.undo_stack.clear()
        self.parameter_panel.set_parametric_enabled(False)
        self.viewer.reset_view()
        self._refresh_model_info()
        self._show_status(f"“{file_path.name}” foi importado com sucesso")

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
    # Modelo e histórico
    # ------------------------------------------------------------------
    def _new_hull(self) -> None:
        """Volta ao fluxo paramétrico com o perfil padrão da aplicação."""
        self.parameter_panel.set_parametric_enabled(True)
        self._select_profile_by_name(DEFAULT_PROFILE.name)

    def _on_parametric_hull_generated(self) -> None:
        """Sincroniza a interface após um recálculo paramétrico."""
        self._source_path = None
        self._model_name = self.profile_combo.currentText()
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
            "m" if self._source_path is None else "unidades do arquivo",
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
            "Nenhum arquivo solto tem formato de malha suportado (STL, OBJ, PLY, VTK, VTP)"
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
            "Modelagem paramétrica e visualização de cascos.\n"
            "Suporta importação e exportação de malhas 3D.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Encerra o renderizador VTK antes de fechar a janela."""
        self.viewer.close()
        super().closeEvent(event)
