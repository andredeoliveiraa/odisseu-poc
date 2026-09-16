"""Coordenação entre controles Qt, restrições e geração de malha."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox

from app.models.constraints import HullConstraintValidator


class HullController(QObject):
    """Aplica parâmetros do formulário e atualiza o visualizador."""

    hull_generated = Signal()

    def __init__(self, viewer, parameter_view) -> None:
        super().__init__(parameter_view)
        self.viewer = viewer
        self.parameter_view = parameter_view
        self.validator = HullConstraintValidator()
        self.generator = None
        self.parameter_view.draw_requested.connect(self.draw)

    def _dialog_parent(self):
        """Usa a janela principal como pai, e não o painel lateral.

        Um diálogo parentado no painel é centralizado sobre ele, o que em
        ambiente de dois monitores pode abri-lo fora da janela do aplicativo.
        """
        return self.parameter_view.window()

    def draw(self) -> None:
        """Lê o formulário, valida restrições e redesenha o casco."""
        if not self.parameter_view.is_parametric_enabled():
            return

        self.parameter_view.set_busy(True)
        QGuiApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        try:
            try:
                generator = self.parameter_view.current_generator()
                result = self.validator.validate(
                    generator,
                    self.parameter_view.concavity.value(),
                    self.parameter_view.minimum_radius.value(),
                )
            except ValueError as error:
                QMessageBox.warning(
                    self._dialog_parent(), "Parâmetros inválidos", str(error)
                )
                return

            if not result.valid:
                QMessageBox.warning(
                    self._dialog_parent(), "Curvatura inválida", result.message
                )
                return

            self.generator = generator
            self.viewer.set_hull(generator.generate_mesh())
            self.viewer.fit_view()
        finally:
            QGuiApplication.restoreOverrideCursor()
            self.parameter_view.set_busy(False)

        self.parameter_view.mark_synced()
        self.hull_generated.emit()
        self.viewer.status_message.emit("Casco recalculado com sucesso")
