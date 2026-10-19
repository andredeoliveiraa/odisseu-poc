"""Painel de desempenho: hidrostática e resistência ao avanço."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.models.hydrodynamics import KNOT, Hydrostatics, ResistancePoint
from app.views.controls import Section, SliderField
from app.views.resistance_chart import ResistanceChart

HYDROSTATIC_ROWS = (
    ("volume", "Volume deslocado", "{:.2f} m³"),
    ("displacement", "Deslocamento", "{:.2f} t"),
    ("waterline_length", "Comprimento na flutuação (LWL)", "{:.2f} m"),
    ("waterline_beam", "Boca na flutuação (BWL)", "{:.2f} m"),
    ("draft", "Calado", "{:.2f} m"),
    ("wetted_area", "Superfície molhada", "{:.2f} m²"),
    ("waterplane_area", "Área de flutuação", "{:.2f} m²"),
    ("block_coefficient", "Coef. de bloco (Cb)", "{:.3f}"),
    ("prismatic_coefficient", "Coef. prismático (Cp)", "{:.3f}"),
    ("midship_coefficient", "Coef. de seção mestra (Cm)", "{:.3f}"),
    ("waterplane_coefficient", "Coef. de flutuação (Cw)", "{:.3f}"),
    ("lcb", "LCB (a partir da meia-nau)", "{:+.2f} m"),
    ("lcf", "LCF (a partir da meia-nau)", "{:+.2f} m"),
    ("km", "KM (altura metacêntrica da quilha)", "{:.2f} m"),
)


class PerformancePanel(QWidget):
    """Mostra hidrostática na hora e a curva de resistência quando pronta."""

    design_speed_changed = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Desempenho")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        description = QLabel(
            "Hidrostática na linha d'água e resistência ao avanço pelo método do "
            "conjunto ShipD: ondas pela integral de Michell e atrito pela linha ITTC-57."
        )
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.hydrostatics_section = Section("Hidrostática", self)
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 1)
        self._hydro_values: dict[str, QLabel] = {}
        for row, (key, label, _) in enumerate(HYDROSTATIC_ROWS):
            caption = QLabel(label)
            caption.setObjectName("fieldLabel")
            value = QLabel("—")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(caption, row, 0)
            grid.addWidget(value, row, 1)
            self._hydro_values[key] = value
        self.hydrostatics_section.add_widget(holder)
        layout.addWidget(self.hydrostatics_section)

        self.resistance_section = Section("Resistência ao avanço", self)
        self.design_speed = SliderField(8.0, 1.0, 40.0, 1, " nós", 0.5)
        self.design_speed.valueChanged.connect(
            lambda value: self.design_speed_changed.emit(value * KNOT)
        )
        self.resistance_section.add_row(
            "Velocidade de projeto", self.design_speed,
            "Velocidade em que Rt e a potência efetiva são informadas.",
        )
        self.design_result = QLabel("—")
        self.design_result.setWordWrap(True)
        self.resistance_section.add_widget(self.design_result)
        self.chart = ResistanceChart(self)
        self.resistance_section.add_widget(self.chart)
        self.notes = QLabel()
        self.notes.setObjectName("modeHint")
        self.notes.setWordWrap(True)
        self.notes.hide()
        self.resistance_section.add_widget(self.notes)
        layout.addWidget(self.resistance_section)

        self.table_section = Section("Tabela da curva", self, expanded=False)
        self.table = QLabel("—")
        self.table.setObjectName("monoTable")
        self.table.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.table_section.add_widget(self.table)
        layout.addWidget(self.table_section)
        layout.addStretch()

    def set_unavailable(self, message: str) -> None:
        for value in self._hydro_values.values():
            value.setText("—")
        self.design_result.setText(message)
        self.chart.set_message(message)
        self.table.setText("—")
        self.notes.hide()

    def set_hydrostatics(self, hydrostatics: Hydrostatics) -> None:
        for key, _, template in HYDROSTATIC_ROWS:
            self._hydro_values[key].setText(template.format(getattr(hydrostatics, key)))
        self.chart.set_message("Calculando resistência…")
        self.design_result.setText("Calculando resistência…")

    def set_resistance(
        self,
        curve: list[ResistancePoint],
        design: ResistancePoint,
        notes: list[str],
    ) -> None:
        self.design_result.setText(
            f"<b>{design.speed / KNOT:.1f} nós</b> (Fn {design.froude:.2f}): "
            f"Rt = <b>{design.total / 1000:.2f} kN</b> · Rw = {design.wave / 1000:.2f} kN · "
            f"Rf = {design.friction / 1000:.2f} kN · potência efetiva = "
            f"<b>{design.effective_power / 1000:.1f} kW</b>"
        )
        self.chart.set_curve(curve, design.speed)
        rows = ["  nós     Fn    Rw kN   Rf kN   Rt kN   PE kW"]
        for point in curve:
            rows.append(
                f"{point.speed / KNOT:5.1f}  {point.froude:5.3f}  {point.wave / 1000:7.2f} "
                f"{point.friction / 1000:7.2f} {point.total / 1000:7.2f} "
                f"{point.effective_power / 1000:7.1f}"
            )
        self.table.setText("\n".join(rows))
        self.notes.setText("\n\n".join(notes))
        self.notes.setVisible(bool(notes))
