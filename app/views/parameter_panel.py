"""Painel Qt para os parâmetros de geração do casco."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ParameterPanel(QWidget):
    """Formulário dos parâmetros dos Grupos 1 e 2."""

    draw_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(self._create_group_1())
        layout.addWidget(self._create_group_2())

        self.draw_button = QPushButton("DRAW")
        self.draw_button.setMinimumHeight(36)
        self.draw_button.clicked.connect(self.draw_requested)
        layout.addWidget(self.draw_button)
        layout.addStretch()

    def _spin_box(self, value: float, minimum: float, maximum: float) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(minimum, maximum)
        field.setValue(value)
        field.setDecimals(2)
        field.setSingleStep(0.1)
        return field

    def _create_group_1(self) -> QGroupBox:
        group = QGroupBox("Grupo 1 - Dimensões")
        form = QFormLayout(group)
        self.total_length = self._spin_box(12.0, 0.1, 1000.0)
        self.midship_length = self._spin_box(6.0, 0.1, 1000.0)
        self.beam = self._spin_box(4.0, 0.1, 1000.0)
        self.draft = self._spin_box(1.8, 0.1, 1000.0)
        form.addRow("Comprimento total", self.total_length)
        form.addRow("Seção média", self.midship_length)
        form.addRow("Boca", self.beam)
        form.addRow("Calado", self.draft)
        return group

    def _create_group_2(self) -> QGroupBox:
        group = QGroupBox("Grupo 2 - Restrições")
        form = QFormLayout(group)
        self.concavity = self._spin_box(0.0, 0.0, 1.0)
        self.minimum_radius = self._spin_box(2.0, 0.01, 1000.0)
        form.addRow("Concavidade das estações", self.concavity)
        form.addRow("Raio mínimo (m)", self.minimum_radius)
        return group
