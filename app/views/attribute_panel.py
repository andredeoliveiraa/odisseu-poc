"""Painel Qt de modelagem por atributos (Figuras 5.6 a 5.8 da referência)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.models.attributes import ATTRIBUTE_MODELS, ATTRIBUTE_THRESHOLD
from app.models.sampling import PARTICIPANT_CONSTRAINTS, SampledDesign

NO_PRESET = "Nenhuma (espaço da Tabela 4.1)"


class AttributePanel(QWidget):
    """Avalia o casco atual e solicita a amostragem por atributos."""

    #: ``(atributos, N, preferências, tamanho da subpopulação)``.
    sample_requested = Signal(list, int, str, int)
    cancel_requested = Signal()
    design_selected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._samples: list[SampledDesign] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Modelagem por atributos")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        description = QLabel(
            "Cada atributo é avaliado por um modelo polinomial sobre os parâmetros "
            f"padronizados do casco. Valores acima de {ATTRIBUTE_THRESHOLD:.1f} "
            "indicam que o casco expressa o atributo."
        )
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.score_group = self._create_score_group()
        layout.addWidget(self.score_group)
        layout.addWidget(self._create_sampling_group())
        layout.addStretch()

    def _create_score_group(self) -> QGroupBox:
        group = QGroupBox("Avaliação do casco atual")
        grid = QGridLayout(group)
        grid.setColumnStretch(1, 1)
        self._score_bars: dict[str, QProgressBar] = {}
        self._score_labels: dict[str, QLabel] = {}
        for row, model in enumerate(ATTRIBUTE_MODELS):
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setMaximumHeight(10)
            value = QLabel("—")
            value.setMinimumWidth(40)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(QLabel(model.label), row, 0)
            grid.addWidget(bar, row, 1)
            grid.addWidget(value, row, 2)
            self._score_bars[model.key] = bar
            self._score_labels[model.key] = value

        self.expressed_label = QLabel()
        self.expressed_label.setWordWrap(True)
        grid.addWidget(self.expressed_label, len(ATTRIBUTE_MODELS), 0, 1, 3)
        return group

    def _create_sampling_group(self) -> QGroupBox:
        group = QGroupBox("Gerar cascos por atributo")
        layout = QVBoxLayout(group)

        hint = QLabel(
            "Escolha um ou mais atributos. O S-TLBO amostra projetos distintos "
            "que satisfazem todos eles."
        )
        hint.setObjectName("secondaryText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        self._checkboxes: dict[str, QCheckBox] = {}
        for index, model in enumerate(ATTRIBUTE_MODELS):
            checkbox = QCheckBox(model.label)
            checkbox.toggled.connect(self._update_sample_button)
            grid.addWidget(checkbox, index // 2, index % 2)
            self._checkboxes[model.key] = checkbox
        layout.addLayout(grid)

        form = QFormLayout()
        self.design_count = QSpinBox()
        self.design_count.setRange(1, 60)
        self.design_count.setValue(5)
        self.design_count.setMinimumHeight(32)
        self.design_count.setToolTip("Quantidade de projetos (N) a amostrar.")
        form.addRow("Número de projetos (N)", self.design_count)

        self.preference = QComboBox()
        self.preference.addItem(NO_PRESET)
        self.preference.addItems(list(PARTICIPANT_CONSTRAINTS))
        self.preference.setToolTip(
            "Restrições geométricas das preferências de um participante "
            "(Tabela 4.1), aplicadas junto com os atributos."
        )
        form.addRow("Preferências", self.preference)

        self.population = QSpinBox()
        self.population.setRange(10, 120)
        self.population.setValue(30)
        self.population.setMinimumHeight(32)
        self.population.setToolTip(
            "Alunos por subpopulação (s). Valores maiores exploram melhor o espaço, "
            "com mais tempo de cálculo; a tese recomenda mais de 20."
        )
        form.addRow("Alunos por subpopulação (s)", self.population)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.sample_button = QPushButton("Amostrar projetos")
        self.sample_button.setObjectName("primaryButton")
        self.sample_button.setMinimumHeight(40)
        self.sample_button.clicked.connect(self._request_sample)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_requested)
        buttons.addWidget(self.sample_button, 1)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.progress_label = QLabel()
        self.progress_label.setObjectName("secondaryText")
        self.progress_label.setWordWrap(True)
        self.progress_label.hide()
        layout.addWidget(self.progress_label)

        layout.addWidget(QLabel("Desenhar modelo específico"))
        self.design_slider = QSlider(Qt.Orientation.Horizontal)
        self.design_slider.setRange(1, 1)
        self.design_slider.setEnabled(False)
        self.design_slider.valueChanged.connect(self._on_slider_changed)
        self.design_label = QLabel("Nenhum projeto amostrado")
        self.design_label.setObjectName("secondaryText")
        self.design_label.setWordWrap(True)
        self.draw_button = QPushButton("Desenhar")
        self.draw_button.setEnabled(False)
        self.draw_button.clicked.connect(self._request_draw)
        layout.addWidget(self.design_slider)
        layout.addWidget(self.design_label)
        layout.addWidget(self.draw_button)

        self._update_sample_button()
        return group

    def selected_attributes(self) -> list[str]:
        return [key for key, box in self._checkboxes.items() if box.isChecked()]

    def _update_sample_button(self, _checked: bool = False) -> None:
        self.sample_button.setEnabled(
            bool(self.selected_attributes()) and not self.cancel_button.isEnabled()
        )

    def _request_sample(self) -> None:
        self.sample_requested.emit(
            self.selected_attributes(),
            self.design_count.value(),
            self.preference.currentText(),
            self.population.value(),
        )

    def set_sampling(self, running: bool) -> None:
        """Alterna entre o estado ocioso e o de amostragem em andamento."""
        self.cancel_button.setEnabled(running)
        self.progress.setVisible(running)
        self.progress_label.setVisible(running)
        if running:
            self.progress_label.setText("Iniciando S-TLBO...")
        self.sample_button.setEnabled(not running and bool(self.selected_attributes()))

    def set_progress(self, iteration: int, cost: float) -> None:
        self.progress_label.setText(f"Iteração {iteration} · custo Ū(T) = {cost:,.1f}")

    def set_samples(self, samples: list[SampledDesign]) -> None:
        """Mostra os projetos amostrados e seleciona o primeiro."""
        self._samples = samples
        self.design_slider.blockSignals(True)
        self.design_slider.setRange(1, max(1, len(samples)))
        self.design_slider.setValue(1)
        self.design_slider.blockSignals(False)
        self.design_slider.setEnabled(len(samples) > 1)
        self.draw_button.setEnabled(bool(samples))
        if samples:
            self._update_label(1)
        else:
            self.design_label.setText("Nenhum projeto amostrado")

    def _update_label(self, value: int) -> None:
        if not self._samples:
            return
        sample = self._samples[value - 1]
        feasibility = (
            ""
            if sample.feasible
            else f" · {sample.violated} restrição(ões) não atendida(s)"
        )
        self.design_label.setText(f"Projeto {value} de {len(self._samples)}{feasibility}")

    def _on_slider_changed(self, value: int) -> None:
        self._update_label(value)

    def _request_draw(self) -> None:
        if self._samples:
            self.design_selected.emit(self.design_slider.value() - 1)

    def current_index(self) -> int:
        return self.design_slider.value() - 1

    def set_scores(self, scores: dict[str, float] | None) -> None:
        """Atualiza as barras; ``None`` indica que a avaliação não se aplica."""
        self.score_group.setEnabled(scores is not None)
        if scores is None:
            for key in self._score_bars:
                self._score_bars[key].setValue(0)
                self._score_labels[key].setText("—")
            self.expressed_label.setText(
                "A avaliação por atributos só se aplica a cascos paramétricos."
            )
            self.expressed_label.setProperty("state", "")
        else:
            expressed = []
            for model in ATTRIBUTE_MODELS:
                score = scores[model.key]
                self._score_bars[model.key].setValue(round(100 * min(max(score, 0.0), 1.0)))
                self._score_labels[model.key].setText(f"{score:.2f}")
                active = score > ATTRIBUTE_THRESHOLD
                self._score_labels[model.key].setProperty("state", "valid" if active else "")
                self._refresh_style(self._score_labels[model.key])
                if active:
                    expressed.append(model.label.split(" (")[0])
            self.expressed_label.setText(
                "Atributos expressos: " + ", ".join(expressed)
                if expressed
                else "O casco não expressa nenhum atributo acima do limiar."
            )
            self.expressed_label.setProperty("state", "valid" if expressed else "error")
        self._refresh_style(self.expressed_label)

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
