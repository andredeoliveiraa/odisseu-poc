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

    def draw(self) -> None:
        """Lê o formulário, valida restrições e redesenha o casco."""
        try:
            self.generator = HullGenerator(
                total_length=self.parameter_view.total_length.value(),
                midship_length=self.parameter_view.midship_length.value(),
                beam=self.parameter_view.beam.value(),
                draft=self.parameter_view.draft.value(),
                bow_angle=self.parameter_view.bow_angle.value(),
                station_concavity=self.parameter_view.concavity.value(),
                stations=self.parameter_view.stations.value(),
                section_points=self.parameter_view.section_points.value(),
            )
            result = self.validator.validate(
                self.generator,
                self.parameter_view.concavity.value(),
                self.parameter_view.minimum_radius.value(),
            )
        except ValueError as error:
            QMessageBox.warning(self.parameter_view, "Parâmetros inválidos", str(error))
            return

        if not result.valid:
            QMessageBox.warning(self.parameter_view, "Curvatura inválida", result.message)
            return

        self.viewer.set_hull(self.generator.generate_mesh())
        self.viewer.reset_camera()
        self.viewer.render()
        self.hull_generated.emit()
        self.viewer.status_message.emit("Casco recalculado com sucesso")
