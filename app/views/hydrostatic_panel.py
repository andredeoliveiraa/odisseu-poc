"""Painel de hidrostática (Tabela 3.6 da referência)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.hydrostatics import COLUMN_INFO, HydrostaticResult


class HydrostaticPanel(QWidget):
    """Calcula e mostra a hidrostática do casco para três calados."""

    calculate_requested = Signal(list)
    export_requested = Signal()

    DRAFT_COUNT = 3

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._results: list[HydrostaticResult] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Hidrostática")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        description = QLabel(
            "Propriedades do casco na linha d'água, para calados medidos a partir "
            "da linha de base (ponto mais baixo da quilha). O espelho de popa é "
            "tampado para o cálculo do volume."
        )
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        self._drafts: list[QDoubleSpinBox] = []
        for index in range(self.DRAFT_COUNT):
            spin = QDoubleSpinBox()
            spin.setRange(0.05, 100.0)
            spin.setDecimals(2)
            spin.setSingleStep(0.1)
            spin.setSuffix(" m")
            spin.setMinimumHeight(32)
            spin.setKeyboardTracking(False)
            self._drafts.append(spin)
            form.addRow(f"Calado T{index + 1}", spin)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.calculate_button = QPushButton("Calcular hidrostática")
        self.calculate_button.setObjectName("primaryButton")
        self.calculate_button.setMinimumHeight(38)
        self.calculate_button.clicked.connect(self._request_calculation)
        self.export_button = QPushButton("Exportar CSV...")
        self.export_button.setMinimumHeight(38)
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_requested)
        buttons.addWidget(self.calculate_button, 1)
        buttons.addWidget(self.export_button)
        layout.addLayout(buttons)

        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        self.table = QTableWidget(len(COLUMN_INFO), self.DRAFT_COUNT)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setVerticalHeaderLabels(
            [
                f"{name} ({unit})" if unit else name
                for name, (_label, unit) in zip(COLUMN_INFO, COLUMN_INFO.values())
            ]
        )
        for row, (name, (label, _unit)) in enumerate(COLUMN_INFO.items()):
            header = self.table.verticalHeaderItem(row)
            if header is not None:
                header.setToolTip(label)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(430)
        layout.addWidget(self.table)
        layout.addStretch()

        self.set_available(True)

    def set_default_drafts(self, drafts: tuple[float, ...]) -> None:
        for spin, value in zip(self._drafts, drafts):
            spin.setValue(value)

    def drafts(self) -> list[float]:
        return [spin.value() for spin in self._drafts]

    def _request_calculation(self) -> None:
        self.calculate_requested.emit(self.drafts())

    def set_available(self, available: bool) -> None:
        """Habilita o cálculo só para cascos paramétricos."""
        self.calculate_button.setEnabled(available)
        for spin in self._drafts:
            spin.setEnabled(available)
        if not available:
            self.show_message(
                "A hidrostática só se aplica a cascos paramétricos.", ""
            )
            self.clear_results()

    def show_message(self, text: str, state: str) -> None:
        self.message.setText(text)
        self.message.setProperty("state", state)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)

    def clear_results(self) -> None:
        self._results = []
        self.table.clearContents()
        self.export_button.setEnabled(False)

    def results(self) -> list[HydrostaticResult]:
        return list(self._results)

    def set_results(self, results: list[HydrostaticResult]) -> None:
        self._results = results
        self.table.clearContents()
        for column, result in enumerate(results):
            self.table.setHorizontalHeaderItem(column, QTableWidgetItem(f"T{column + 1}"))
            for row, name in enumerate(COLUMN_INFO):
                value = getattr(result, name)
                decimals = 3 if name in {"Cp", "Cm", "Cw", "Cb"} else 2
                item = QTableWidgetItem(f"{value:.{decimals}f}")
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(row, column, item)
        self.export_button.setEnabled(bool(results))
