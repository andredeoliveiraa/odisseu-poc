"""Coordenação entre controles Qt, restrições e geração de malha."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

from app.hull_generator import HullGenerator
from app.models.constraints import HullConstraintValidator


class HullController(QObject):
    """Aplica parâmetros do formulário e atualiza o visualizador."""

    hull_generated = Signal()

    def __init__(self, viewer, parameter_view) -> None:
        super().__init__(parameter_view)
        self.viewer = viewer
        self.parameter_view = parameter_view
        self.validator = HullConstraintValidator()
        self.generator = HullGenerator()
        self.parameter_view.draw_requested.connect(self.draw)
        self.parameter_view.live_update_requested.connect(self.draw_live)

    def draw_live(self) -> None:
        """Redesenha durante o ajuste dos controles, mantendo a câmera."""
        self.draw(reset_camera=False, interactive=False)

    def draw(self, reset_camera: bool = True, interactive: bool = True) -> None:
        """Lê o formulário, valida restrições e redesenha o casco.

        Com ``interactive=False`` (modo ao vivo), erros não abrem diálogos: o
        painel já os mostra na linha de validação.
        """
        try:
            self.generator = HullGenerator(**self.parameter_view.generator_options())
            result = self.validator.validate(
                self.generator,
                self.parameter_view.concavity.value(),
                self.parameter_view.minimum_radius.value(),
            )
        except ValueError as error:
            if interactive:
                QMessageBox.warning(self.parameter_view, "Parâmetros inválidos", str(error))
            return

        if not result.valid:
            if interactive:
                QMessageBox.warning(self.parameter_view, "Curvatura inválida", result.message)
            return

        self.viewer.set_hull(self.generator.generate_mesh())
        if reset_camera:
            self.viewer.reset_camera()
        self.viewer.render()
        self.hull_generated.emit()
        self.viewer.status_message.emit("Casco recalculado com sucesso")
