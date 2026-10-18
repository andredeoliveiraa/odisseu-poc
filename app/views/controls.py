"""Controles compactos do painel: linha com deslizador e seção recolhível."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

SLIDER_STEPS = 1000
"""Resolução do deslizador; o campo numérico mantém a precisão completa."""


class SliderField(QWidget):
    """Deslizador com campo numérico sincronizado.

    Expõe a mesma interface usada pelo painel para ``QDoubleSpinBox`` e
    ``QSpinBox`` (``value``, ``setValue``, ``valueChanged``), então pode
    substituí-los sem mudar quem lê os valores.
    """

    valueChanged = Signal(float)

    def __init__(
        self,
        value: float,
        minimum: float,
        maximum: float,
        decimals: int = 2,
        suffix: str = "",
        step: float | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._integer = decimals == 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(0, SLIDER_STEPS)
        self.slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.spin = QDoubleSpinBox(self)
        self.spin.setObjectName("sliderValue")
        # As setas ficam com largura zero na folha de estilo; usar NoButtons
        # junto com a folha de estilo faz o Qt reduzir o campo a 1 pixel.
        self.spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.spin.setDecimals(decimals)
        self.spin.setRange(minimum, maximum)
        self.spin.setSuffix(suffix)
        self.spin.setSingleStep(step if step is not None else (maximum - minimum) / 100)
        self.spin.setKeyboardTracking(False)
        self.spin.setFixedWidth(84)
        self.spin.setValue(value)

        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)

        self._sync_slider(self.spin.value())
        self.slider.valueChanged.connect(self._on_slider_moved)
        self.spin.valueChanged.connect(self._on_spin_changed)

    def value(self) -> float | int:
        value = self.spin.value()
        return int(round(value)) if self._integer else value

    def setValue(self, value: float) -> None:
        self.spin.setValue(value)

    def setRange(self, minimum: float, maximum: float) -> None:
        self.spin.setRange(minimum, maximum)
        self._sync_slider(self.spin.value())

    def setSuffix(self, suffix: str) -> None:
        self.spin.setSuffix(suffix)

    def setSingleStep(self, step: float) -> None:
        self.spin.setSingleStep(step)

    def setToolTip(self, text: str) -> None:
        super().setToolTip(text)
        self.slider.setToolTip(text)
        self.spin.setToolTip(text)

    def _sync_slider(self, value: float) -> None:
        span = self.spin.maximum() - self.spin.minimum()
        position = 0 if span <= 0 else round((value - self.spin.minimum()) / span * SLIDER_STEPS)
        self.slider.blockSignals(True)
        self.slider.setValue(position)
        self.slider.blockSignals(False)

    def _on_slider_moved(self, position: int) -> None:
        span = self.spin.maximum() - self.spin.minimum()
        value = self.spin.minimum() + span * position / SLIDER_STEPS
        step = self.spin.singleStep()
        if self._integer:
            # Inteiros respeitam o passo (ex.: pontos por seção ímpares).
            value = self.spin.minimum() + round((value - self.spin.minimum()) / step) * step
        self.spin.setValue(value)

    def _on_spin_changed(self, value: float) -> None:
        self._sync_slider(value)
        self.valueChanged.emit(self.value())


class Section(QFrame):
    """Seção recolhível, com interruptor On/Off opcional no cabeçalho.

    Quando a seção tem interruptor e está desligada, o conteúdo fica
    desabilitado, como os grupos "Step" e "Shape Topsides" da referência.
    """

    EXPANDED_MARK = "▾"
    COLLAPSED_MARK = "▸"

    switched = Signal(bool)

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        expanded: bool = True,
        switchable: bool = False,
        switched_on: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panelSection")
        self._title = title

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(0)
        self.header_button = QPushButton(self)
        self.header_button.setObjectName("sectionHeader")
        self.header_button.setCheckable(True)
        self.header_button.setChecked(expanded)
        self.header_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_button.toggled.connect(self._set_expanded)
        header.addWidget(self.header_button, 1)

        self.switch: QCheckBox | None = None
        if switchable:
            self.switch = QCheckBox(self)
            self.switch.setObjectName("sectionSwitch")
            self.switch.setChecked(switched_on)
            self.switch.setCursor(Qt.CursorShape.PointingHandCursor)
            self.switch.toggled.connect(self._on_switched)
            header.addWidget(self.switch)
        outer.addLayout(header)

        self.body = QWidget(self)
        self.body.setObjectName("sectionBody")
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(12, 8, 12, 12)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(8)
        self.grid.setColumnStretch(1, 1)
        outer.addWidget(self.body)

        self._set_expanded(expanded)
        self._on_switched(self.is_on(), emit=False)

    def add_row(self, label: str, field: QWidget, tooltip: str = "") -> None:
        """Adiciona uma linha "rótulo | controle" ao corpo da seção."""
        row = self.grid.rowCount()
        caption = QLabel(label, self.body)
        caption.setObjectName("fieldLabel")
        if tooltip:
            caption.setToolTip(tooltip)
            field.setToolTip(tooltip)
        self.grid.addWidget(caption, row, 0)
        self.grid.addWidget(field, row, 1)

    def add_widget(self, widget: QWidget) -> None:
        """Adiciona um widget ocupando a largura toda da seção."""
        self.grid.addWidget(widget, self.grid.rowCount(), 0, 1, 2)

    def is_on(self) -> bool:
        return self.switch is None or self.switch.isChecked()

    def set_on(self, on: bool) -> None:
        if self.switch is not None:
            self.switch.setChecked(on)

    def _set_expanded(self, expanded: bool) -> None:
        mark = self.EXPANDED_MARK if expanded else self.COLLAPSED_MARK
        self.header_button.setText(f"{mark}  {self._title}")
        self.body.setVisible(expanded)

    def _on_switched(self, on: bool, emit: bool = True) -> None:
        if self.switch is not None:
            self.switch.setText("On" if on else "Off")
        self.body.setEnabled(on)
        if emit:
            self.switched.emit(on)
