"""Janela principal e comandos de alto nível da aplicação."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from app.visualization import HullViewer
from app.controllers.hull_controller import HullController
from app.views.parameter_panel import ParameterPanel


class MainWindow(QMainWindow):
    """Janela principal do Odisseu.

    A janela coordena a navegação da aplicação, enquanto a geometria e o
    renderizador ficam isolados em :class:`HullViewer`.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Odisseu - Modelagem Paramétrica de Cascos")
        self.resize(1280, 800)

        self.viewer = HullViewer(self)
        self.setCentralWidget(self.viewer)
        self.parameter_panel = ParameterPanel(self)
        self.parameter_dock = QDockWidget("Parâmetros do casco", self)
        self.parameter_dock.setWidget(self.parameter_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.parameter_dock)
        self.controller = HullController(self.viewer, self.parameter_panel)
        self.viewer.status_message.connect(self.statusBar().showMessage)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self.statusBar().showMessage("Pronto - cena de exemplo carregada")

    def _create_actions(self) -> None:
        """Cria ações reutilizadas pelos menus e pela barra de ferramentas."""
        self.open_action = QAction("Abrir casco...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self._open_hull)

        self.reset_view_action = QAction("Redefinir vista", self)
        self.reset_view_action.setShortcut("Home")
        self.reset_view_action.triggered.connect(self._reset_view)

        self.fit_view_action = QAction("Ajustar modelo", self)
        self.fit_view_action.triggered.connect(self._fit_view)

        self.quit_action = QAction("Sair", self)
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.triggered.connect(self.close)

        self.about_action = QAction("Sobre o Odisseu", self)
        self.about_action.triggered.connect(self._show_about)

    def _create_menus(self) -> None:
        """Monta a barra de menus principal."""
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.reset_view_action)
        view_menu.addAction(self.fit_view_action)

        self.menuBar().addMenu("Shape Operators")
        self.menuBar().addMenu("Attribute Modeling")
        self.menuBar().addMenu("Export")

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.about_action)

    def _create_toolbar(self) -> None:
        """Monta a barra de ferramentas com comandos de visualização."""
        toolbar = QToolBar("Ferramentas principais", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.addAction(self.open_action)
        toolbar.addSeparator()
        toolbar.addAction(self.reset_view_action)
        toolbar.addAction(self.fit_view_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

    def _open_hull(self) -> None:
        """Seleciona um arquivo de casco (a importação será implementada depois)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir casco",
            "",
            "Malhas 3D (*.stl *.obj *.ply *.vtk);;Todos os arquivos (*)",
        )
        if file_path:
            self.statusBar().showMessage(
                f"Arquivo selecionado: {file_path} (importação pendente)"
            )

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
            "Odisseu\nBoilerplate da plataforma CAD paramétrica de cascos.",
        )
