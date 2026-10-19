"""Painel Qt dos operadores de forma (Figuras 5.3 e 5.4 da referência).

O painel reúne os diálogos do ModiYacht: os operadores do **Grupo 1**
(alongamento, alargamento, aprofundamento, quinas, quilha, ângulos e roda de
proa) e do **Grupo 2** (concavidade e raio mínimo de curvatura das estações).
Os campos mostram os valores medidos no casco atual; só os campos alterados
pelo usuário são aplicados ao clicar em **Aplicar operadores**.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.models.hull_model import PARAMETER_INFO, HullParameters, MeshResolution
from app.models.shape_operators import (
    CONCAVE,
    CONVEX,
    DOUBLE_CHINE,
    NO_CHINE,
    SINGLE_CHINE,
)
from app.models.transforms import TransformParameters
from app.views.collapsible_section import CollapsibleSection


class RangedSpinBox(QDoubleSpinBox):
    """Campo numérico que avisa quando uma tecla é recusada.

    ``QDoubleSpinBox`` descarta em silêncio tudo que sai do intervalo, o que
    faz um valor digitado virar outro sem nenhum sinal. Aqui a recusa vira um
    evento observável, para que o painel possa explicá-la ao usuário.
    """

    input_rejected = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.lineEdit().inputRejected.connect(self.input_rejected)

    def range_description(self) -> str:
        """Descreve o intervalo aceito, na mesma formatação do campo."""
        return (
            f"{self.textFromValue(self.minimum())}{self.suffix()} a "
            f"{self.textFromValue(self.maximum())}{self.suffix()}"
        )


class RadiusSpinBox(RangedSpinBox):
    """Raio mínimo de curvatura: o valor máximo do campo representa "reta" (∞)."""

    STRAIGHT_TEXT = "reta (∞)"

    def textFromValue(self, value: float) -> str:
        if value >= self.maximum() - 1e-9:
            return self.STRAIGHT_TEXT
        return super().textFromValue(value)

    def valueFromText(self, text: str) -> float:
        if text.strip().lower().startswith(("reta", "∞", "inf")):
            return self.maximum()
        return super().valueFromText(text.replace(self.suffix(), "").strip())

    def validate(self, text: str, position: int):
        if text.strip().lower().startswith(("r", "∞", "i")):
            return QValidator.State.Acceptable, text, position
        return super().validate(text, position)

    def set_radius(self, radius: float) -> None:
        """Mostra um raio medido; ``inf`` (curva reta) vira o valor máximo."""
        self.setValue(self.maximum() if radius == float("inf") else min(radius, self.maximum()))


class RangedIntSpinBox(QSpinBox):
    """Versão inteira de :class:`RangedSpinBox`, com o mesmo aviso de recusa."""

    input_rejected = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.lineEdit().inputRejected.connect(self.input_rejected)

    def range_description(self) -> str:
        return f"{self.minimum()}{self.suffix()} a {self.maximum()}{self.suffix()}"


#: Qualidade da malha de exibição (subdivisões dos patches de Coons).
MESH_QUALITIES: dict[str, MeshResolution] = {
    "Baixa": MeshResolution.coarse(),
    "Média": MeshResolution(),
    "Alta": MeshResolution(longitudinal=96, upper=16, lower=24),
}

#: Campos de cada operador do Grupo 1: (título, [(parâmetro, rótulo)]).
GROUP_1_LAYOUT: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Alongamento", (("Le", "Entrada Lₑ"), ("Lm", "Meio Lₘ"), ("Lr", "Popa Lᵣ"))),
    ("Alargamento (boca)", (("Be", "Estação 1 Bₑ"), ("Bm", "Estação 2 Bₘ"), ("Br", "Estação 3 Bᵣ"))),
    ("Aprofundamento (pontal)", (("De", "Estação 1 Dₑ"), ("Dm", "Estação 2 Dₘ"), ("Dr", "Estação 3 Dᵣ"))),
    (
        "Posição da quina",
        (("Fe", "Estação 1 Fₑ"), ("Fm", "Estação 2 Fₘ"), ("Fr", "Estação 3 Fᵣ"), ("Fb", "Proa F_b")),
    ),
    ("Espessura da quina", (("Ce", "Estação 1 Cₑ"), ("Cm", "Estação 2 Cₘ"), ("Cr", "Estação 3 Cᵣ"))),
    ("Quilha e roda de proa", (("K", "Espessura da quilha K"), ("H", "Comprimento vertical H"))),
    (
        "Ângulos",
        (("beta", "Ângulo de proa β"), ("theta", "Ângulo de entrada θ"), ("alpha", "Tosamento α")),
    ),
)

#: Intervalos e passos dos campos numéricos.
PARAMETER_RANGES: dict[str, tuple[float, float, float]] = {
    **{name: (0.1, 200.0, 0.1) for name in ("Le", "Lm", "Lr")},
    **{name: (0.1, 100.0, 0.1) for name in ("Be", "Bm", "Br")},
    **{name: (0.1, 50.0, 0.1) for name in ("De", "Dm", "Dr")},
    **{name: (0.0, 50.0, 0.1) for name in ("Fe", "Fm", "Fr", "Fb")},
    **{name: (0.0, 10.0, 0.01) for name in ("Ce", "Cm", "Cr", "K")},
    "H": (0.05, 50.0, 0.1),
    "beta": (1.0, 179.0, 1.0),
    "theta": (1.0, 89.0, 1.0),
    "alpha": (-45.0, 45.0, 0.5),
}

#: Linhas de estação com concavidade: (estação, linha, rótulo).
CONCAVITY_LINES: tuple[tuple[int, str, str], ...] = tuple(
    (station, line, f"Estação {station + 1} · linha {'superior' if line == 'upper' else 'inferior'}")
    for station in range(3)
    for line in ("upper", "lower")
)

#: Parâmetros de raio, na ordem do diálogo do Grupo 2.
RADIUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("Res1", "Estação 1 · superior Rₑₛ₁"),
    ("Res2", "Estação 1 · inferior Rₑₛ₂"),
    ("Rms1", "Estação 2 · superior Rₘₛ₁"),
    ("Rms2", "Estação 2 · inferior Rₘₛ₂"),
    ("Rrs1", "Estação 3 · superior Rᵣₛ₁"),
    ("Rrs2", "Estação 3 · inferior Rᵣₛ₂"),
    ("Rek", "Quilha na entrada Rₑₖ"),
)

CHINE_LABELS = {
    DOUBLE_CHINE: "Quina dupla",
    SINGLE_CHINE: "Quina simples",
    NO_CHINE: "Sem quina",
}


class ParameterPanel(QWidget):
    """Formulário dos operadores de forma dos Grupos 1 e 2."""

    draw_requested = Signal()
    reset_requested = Signal()
    transform_requested = Signal(object)
    parameters_changed = Signal()
    mesh_options_changed = Signal()
    draw_availability_changed = Signal(bool)
    #: Emitido quando o fluxo paramétrico liga ou desliga (malha importada,
    #: edição NURBS), para quem depende dos campos do formulário se atualizar.
    parametric_mode_changed = Signal(bool)

    #: Tempo que um aviso de entrada recusada permanece visível.
    REJECTION_FEEDBACK_MS = 5000
    #: Largura máxima da coluna de rótulos, em pixels.
    LABEL_COLUMN_MAX = 190

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._built = False
        self._parametric_enabled = True
        self._transform_enabled = True
        self._busy = False
        self._row_labels: list[QLabel] = []
        self._fields: dict[str, RangedSpinBox] = {}
        self._dirty: set[str] = set()
        self._chine_current = DOUBLE_CHINE
        self._concavity_current: dict[tuple[int, str], str] = {}
        self._concavity_boxes: dict[tuple[int, str], QComboBox] = {}
        self._rejection_timer = QTimer(self)
        self._rejection_timer.setSingleShot(True)
        self._rejection_timer.setInterval(self.REJECTION_FEEDBACK_MS)
        self._rejection_timer.timeout.connect(self._clear_rejection_feedback)
        self._rejected_field: RangedSpinBox | RangedIntSpinBox | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Modelagem paramétrica")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        description = QLabel(
            "Altere os valores dos parâmetros desejados e clique em “Aplicar "
            "operadores”. Só os campos alterados são aplicados; sem alterações, "
            "o casco permanece como está. Medidas em metros e graus."
        )
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        layout.addWidget(description)

        layout.addWidget(self._create_model_group())
        self.group_1 = self._create_group_1()
        self.group_2 = self._create_group_2()
        layout.addWidget(self.group_1)
        layout.addWidget(self.group_2)

        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        self.validation_label.setObjectName("validationLabel")
        layout.addWidget(self.validation_label)

        self.draw_button = QPushButton("Aplicar operadores")
        self.draw_button.setObjectName("primaryButton")
        self.draw_button.setMinimumHeight(42)
        self.draw_button.setToolTip(
            "Aplica os operadores de forma aos parâmetros alterados. "
            "Atalho: Enter em qualquer campo."
        )
        self.draw_button.setAccessibleName("Aplicar operadores")
        self.draw_button.clicked.connect(self._request_draw)

        self.reset_button = QPushButton("Restaurar casco")
        self.reset_button.setMinimumHeight(36)
        self.reset_button.setToolTip("Volta ao casco inicial do tipo atual.")
        self.reset_button.setAccessibleName("Restaurar casco inicial")
        self.reset_button.clicked.connect(self.reset_requested)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.draw_button, 1)
        layout.addLayout(button_layout)

        self.mode_hint = QLabel()
        self.mode_hint.setObjectName("modeHint")
        self.mode_hint.setWordWrap(True)
        self.mode_hint.hide()
        layout.addWidget(self.mode_hint)

        self.transform_group = self._create_transform_group()
        layout.addWidget(self.transform_group)
        layout.addStretch()

        self._align_label_columns()
        self._built = True
        self._refresh_draw_state()

    # ------------------------------------------------------------------
    # Construção do formulário
    # ------------------------------------------------------------------
    def _add_row(
        self, form: QFormLayout, text: str, widget: QWidget, tooltip: str = ""
    ) -> QLabel:
        """Adiciona uma linha rotulada, registrando o rótulo para alinhamento."""
        label = QLabel(text)
        label.setWordWrap(True)
        label.setBuddy(widget)
        if tooltip:
            label.setToolTip(tooltip)
            widget.setToolTip(tooltip)
        widget.setAccessibleName(text)
        label.setAccessibleName(text)
        self._row_labels.append(label)
        form.addRow(label, widget)
        return label

    @staticmethod
    def _configure_form(form: QFormLayout) -> None:
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

    def _align_label_columns(self) -> None:
        """Dá a todos os formulários a mesma coluna de rótulos."""
        if not self._row_labels:
            return
        width = min(
            max(label.sizeHint().width() for label in self._row_labels),
            self.LABEL_COLUMN_MAX,
        )
        for label in self._row_labels:
            label.setFixedWidth(width)

    @staticmethod
    def _subheading(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("subheading")
        return label

    def _create_model_group(self) -> CollapsibleSection:
        section = CollapsibleSection("Modelo atual", self, expanded=False)
        form = QFormLayout()
        self._configure_form(form)
        self.model_name = QLabel("—")
        self.model_kind = QLabel("Gerado no Odisseu")
        self.model_geometry = QLabel("—")
        self.model_geometry.setWordWrap(True)
        self._add_row(form, "Nome", self.model_name)
        self._add_row(form, "Origem", self.model_kind)
        self._add_row(form, "Geometria", self.model_geometry)

        self.mesh_quality = QComboBox()
        self.mesh_quality.addItems(list(MESH_QUALITIES))
        self.mesh_quality.setCurrentText("Média")
        self.mesh_quality.currentIndexChanged.connect(self.mesh_options_changed)
        self._add_row(
            form,
            "Qualidade da malha",
            self.mesh_quality,
            "Quantidade de subdivisões dos patches de Coons. Malhas mais finas "
            "são mais suaves e mais lentas de desenhar.",
        )
        section.add_layout(form)

        self.closed_deck = QCheckBox("Fechar convés")
        self.closed_deck.setToolTip(
            "Fecha o topo do casco. Marque para exportar uma malha estanque, "
            "necessária para calcular volume, CFD ou impressão 3D."
        )
        self.closed_deck.setAccessibleName("Fechar convés")
        self.closed_deck.toggled.connect(self.mesh_options_changed)
        section.add_widget(self.closed_deck)
        return section

    def _spin_box(
        self, value: float, minimum: float, maximum: float, suffix: str = "", step: float = 0.1
    ) -> RangedSpinBox:
        field = RangedSpinBox()
        field.setRange(minimum, maximum)
        field.setSuffix(suffix)
        field.setValue(value)
        field.setDecimals(2)
        field.setSingleStep(step)
        field.setAccelerated(True)
        field.setMinimumHeight(32)
        field.setKeyboardTracking(False)
        return field

    def _parameter_field(self, name: str, label: str, form: QFormLayout) -> None:
        description, unit = PARAMETER_INFO[name]
        low, high, step = PARAMETER_RANGES[name]
        field = self._spin_box(0.0, low, high, "°" if unit == "°" else f" {unit}", step)
        field.setValue(getattr(HullParameters(), name))
        self._register_field(name, field)
        self._add_row(
            form,
            label,
            field,
            f"{description}. Intervalo: {field.range_description()}.",
        )

    def _register_field(self, name: str, field: RangedSpinBox) -> None:
        self._fields[name] = field
        field.valueChanged.connect(lambda _value, key=name: self._on_edited(key))
        field.input_rejected.connect(self._on_input_rejected)
        field.lineEdit().returnPressed.connect(self._request_draw)

    def _create_group_1(self) -> CollapsibleSection:
        section = CollapsibleSection("Grupo 1 · Operadores de forma", self, expanded=True)
        for title, entries in GROUP_1_LAYOUT:
            section.add_widget(self._subheading(title))
            form = QFormLayout()
            self._configure_form(form)
            for name, label in entries:
                self._parameter_field(name, label, form)
            section.add_layout(form)

        section.add_widget(self._subheading("Tipo de quina (inserir / remover)"))
        self._chine_group = QButtonGroup(self)
        chine_row = QVBoxLayout()
        self._chine_buttons: dict[str, QRadioButton] = {}
        for kind in (DOUBLE_CHINE, SINGLE_CHINE, NO_CHINE):
            button = QRadioButton(CHINE_LABELS[kind])
            button.setToolTip(
                {
                    DOUBLE_CHINE: "Insere a quina dupla usando as espessuras Cₑ, Cₘ e Cᵣ.",
                    SINGLE_CHINE: "Remove a espessura da quina e mantém a aresta viva.",
                    NO_CHINE: "Remove a quina: as linhas superior e inferior ficam tangentes (G1).",
                }[kind]
            )
            self._chine_group.addButton(button)
            self._chine_buttons[kind] = button
            chine_row.addWidget(button)
            button.toggled.connect(self._on_chine_toggled)
        self._chine_buttons[DOUBLE_CHINE].setChecked(True)
        wrapper = QWidget()
        wrapper.setLayout(chine_row)
        section.add_widget(wrapper)
        return section

    def _create_group_2(self) -> CollapsibleSection:
        section = CollapsibleSection("Grupo 2 · Restrições das curvas", self, expanded=True)

        section.add_widget(self._subheading("Concavidade das estações"))
        form = QFormLayout()
        self._configure_form(form)
        for station, line, label in CONCAVITY_LINES:
            box = QComboBox()
            box.addItem("Convexa", CONVEX)
            box.addItem("Côncava", CONCAVE)
            box.currentIndexChanged.connect(self._on_edited_concavity)
            self._concavity_boxes[(station, line)] = box
            self._concavity_current[(station, line)] = CONVEX
            self._add_row(
                form,
                label,
                box,
                "Troca a concavidade da linha espelhando seus pontos internos "
                "em torno da corda. Combine com o raio mínimo para ajustar o grau.",
            )
        section.add_layout(form)

        section.add_widget(self._subheading("Raio mínimo de curvatura"))
        form = QFormLayout()
        self._configure_form(form)
        for name, label in RADIUS_FIELDS:
            field = RadiusSpinBox()
            field.setRange(0.0, 1000.0)
            field.setSuffix(" m")
            field.setDecimals(2)
            field.setSingleStep(0.1)
            field.setAccelerated(True)
            field.setMinimumHeight(32)
            field.setKeyboardTracking(False)
            self._register_field(name, field)
            description, _ = PARAMETER_INFO[name]
            self._add_row(
                form,
                label,
                field,
                f"{description}. Zero deixa a curva praticamente reta; valores "
                "acima do máximo alcançável são recusados com o limite da curva.",
            )
        section.add_layout(form)
        return section

    def _create_transform_group(self) -> CollapsibleSection:
        section = CollapsibleSection("Transformar objeto", self, expanded=False)

        description = QLabel(
            "Aplique deslocamento, rotação ou escala ao modelo inteiro. "
            "As rotações usam o centro do objeto como pivô."
        )
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        section.add_widget(description)

        form = QFormLayout()
        self._configure_form(form)
        self.translation_x = self._spin_box(0.0, -10000.0, 10000.0, " m")
        self.translation_y = self._spin_box(0.0, -10000.0, 10000.0, " m")
        self.translation_z = self._spin_box(0.0, -10000.0, 10000.0, " m")
        self.rotation_x = self._spin_box(0.0, -360.0, 360.0, "°")
        self.rotation_y = self._spin_box(0.0, -360.0, 360.0, "°")
        self.rotation_z = self._spin_box(0.0, -360.0, 360.0, "°")
        self.uniform_scale = self._spin_box(1.0, 0.01, 100.0, " ×")
        self.uniform_scale.setDecimals(3)
        self.uniform_scale.setSingleStep(0.05)

        # Os textos de deslocamento ganham a unidade em set_length_unit().
        self._translation_rows = [
            (
                self.translation_x,
                self._add_row(form, "Deslocamento X", self.translation_x),
                "Move o objeto ao longo do eixo X (comprimento, no casco gerado)",
            ),
            (
                self.translation_y,
                self._add_row(form, "Deslocamento Y", self.translation_y),
                "Move o objeto ao longo do eixo Y (boca, no casco gerado)",
            ),
            (
                self.translation_z,
                self._add_row(form, "Deslocamento Z", self.translation_z),
                "Move o objeto ao longo do eixo Z (vertical)",
            ),
        ]
        self._add_row(
            form, "Rotação X", self.rotation_x,
            "Gira o objeto em torno do eixo X (comprimento, no casco gerado).",
        )
        self._add_row(
            form, "Rotação Y", self.rotation_y,
            "Gira o objeto em torno do eixo Y (boca, no casco gerado).",
        )
        self._add_row(
            form, "Rotação Z", self.rotation_z,
            "Gira o objeto em torno do eixo Z (vertical).",
        )
        self._add_row(
            form, "Escala uniforme", self.uniform_scale,
            "Multiplica todas as dimensões do objeto pelo mesmo fator.",
        )
        section.add_layout(form)
        self.set_length_unit("m")

        self.clear_transform_button = QPushButton("Limpar campos")
        self.clear_transform_button.setToolTip(
            "Zera os campos desta seção sem alterar a geometria."
        )
        self.clear_transform_button.setAccessibleName("Limpar campos de transformação")
        self.clear_transform_button.clicked.connect(self.clear_transform_fields)

        self.apply_transform_button = QPushButton("Aplicar transformação")
        self.apply_transform_button.setObjectName("secondaryButton")
        self.apply_transform_button.setToolTip(
            "Aplica os valores acima ao objeto. A operação pode ser desfeita com Ctrl+Z."
        )
        self.apply_transform_button.setAccessibleName("Aplicar transformação")
        self.apply_transform_button.clicked.connect(self._request_transform)

        buttons = QHBoxLayout()
        buttons.addWidget(self.clear_transform_button)
        buttons.addWidget(self.apply_transform_button, 1)
        section.add_layout(buttons)
        return section

    # ------------------------------------------------------------------
    # Transformações
    # ------------------------------------------------------------------
    def _request_transform(self) -> None:
        parameters = TransformParameters(
            translation=(
                self.translation_x.value(),
                self.translation_y.value(),
                self.translation_z.value(),
            ),
            rotation_degrees=(
                self.rotation_x.value(),
                self.rotation_y.value(),
                self.rotation_z.value(),
            ),
            uniform_scale=self.uniform_scale.value(),
        )
        if parameters.is_identity:
            self._show_feedback(
                "Informe um deslocamento, uma rotação ou uma escala antes de aplicar.",
                "warning",
            )
            return
        self._show_feedback("", "")
        self.transform_requested.emit(parameters)
        self.clear_transform_fields()

    def set_length_unit(self, unit: str | None) -> None:
        """Mostra os deslocamentos na unidade do modelo exibido."""
        if unit == "m":
            unit_text = "em metros"
        elif unit:
            unit_text = f"em {unit}"
        else:
            unit_text = "nas unidades do arquivo"
        for field, label, text in self._translation_rows:
            field.setSuffix(f" {unit}" if unit else "")
            tooltip = f"{text}, {unit_text}."
            field.setToolTip(tooltip)
            label.setToolTip(tooltip)

    def set_transform_enabled(self, enabled: bool) -> None:
        """Liga ou desliga o grupo “Transformar objeto”, mantendo o aviso coerente."""
        self._transform_enabled = enabled
        self.transform_group.setEnabled(enabled)
        self._refresh_mode_hint()

    def clear_transform_fields(self) -> None:
        """Restaura os campos incrementais sem alterar a geometria."""
        for field in (
            self.translation_x,
            self.translation_y,
            self.translation_z,
            self.rotation_x,
            self.rotation_y,
            self.rotation_z,
        ):
            field.setValue(0.0)
        self.uniform_scale.setValue(1.0)

    # ------------------------------------------------------------------
    # Estado dos campos
    # ------------------------------------------------------------------
    def field(self, name: str) -> RangedSpinBox:
        return self._fields[name]

    def value(self, name: str) -> float:
        return self._fields[name].value()

    def mesh_resolution(self) -> MeshResolution:
        return MESH_QUALITIES[self.mesh_quality.currentText()]

    def sync_from(
        self,
        parameters: HullParameters,
        chine_kind: str = DOUBLE_CHINE,
        concavities: dict[tuple[int, str], str] | None = None,
    ) -> None:
        """Preenche o formulário com os valores medidos e limpa as alterações."""
        self._cancel_rejection_feedback()
        values = parameters.as_dict()
        for name, field in self._fields.items():
            field.blockSignals(True)
            if isinstance(field, RadiusSpinBox):
                field.set_radius(values[name])
            else:
                field.setValue(values[name])
            field.blockSignals(False)
        self._dirty.clear()

        self._chine_current = chine_kind
        for kind, button in self._chine_buttons.items():
            button.blockSignals(True)
            button.setChecked(kind == chine_kind)
            button.blockSignals(False)

        for key, box in self._concavity_boxes.items():
            current = (concavities or {}).get(key, CONVEX)
            self._concavity_current[key] = current
            box.blockSignals(True)
            box.setCurrentIndex(box.findData(current))
            box.blockSignals(False)
        self._refresh_draw_state()

    def _on_edited(self, name: str) -> None:
        self._clear_field_highlight()
        self._dirty.add(name)
        self._refresh_draw_state()
        self.parameters_changed.emit()

    def _on_chine_toggled(self, _checked: bool) -> None:
        if not self._built:
            return
        self._refresh_draw_state()
        self.parameters_changed.emit()

    def _on_edited_concavity(self, _index: int) -> None:
        self._refresh_draw_state()
        self.parameters_changed.emit()

    def pending_parameters(self) -> dict[str, float]:
        """Parâmetros alterados pelo usuário (valor desejado de cada um)."""
        targets: dict[str, float] = {}
        for name in self._dirty:
            field = self._fields[name]
            if isinstance(field, RadiusSpinBox) and field.value() >= field.maximum() - 1e-9:
                continue  # "reta" não é um pedido de raio
            targets[name] = field.value()
        return targets

    def pending_chine_type(self) -> str | None:
        for kind, button in self._chine_buttons.items():
            if button.isChecked() and kind != self._chine_current:
                return kind
        return None

    def pending_concavities(self) -> dict[tuple[int, str], str]:
        pending = {}
        for key, box in self._concavity_boxes.items():
            wanted = box.currentData()
            if wanted != self._concavity_current[key]:
                pending[key] = wanted
        return pending

    def has_pending_changes(self) -> bool:
        return bool(
            self.pending_parameters() or self.pending_chine_type() or self.pending_concavities()
        )

    def _refresh_draw_state(self) -> None:
        if not self._built:
            return
        pending = self.has_pending_changes()
        if not self._parametric_enabled:
            self._show_feedback("", "")
            self._set_draw_enabled(False)
            return
        if pending:
            self._show_feedback(
                "Parâmetros alterados. Aplique os operadores para ver o resultado.",
                "warning",
            )
        elif not self._rejection_timer.isActive():
            self._show_feedback("Casco em dia com o formulário.", "valid")
        self._set_draw_enabled(not self._busy)

    def _set_draw_enabled(self, enabled: bool) -> None:
        """Mantém botão e ação de menu com a mesma disponibilidade."""
        if self.draw_button.isEnabled() != enabled:
            self.draw_button.setEnabled(enabled)
            self.draw_availability_changed.emit(enabled)

    def _request_draw(self) -> None:
        """Dispara a aplicação apenas quando ela é possível."""
        if self.draw_button.isEnabled():
            self.draw_requested.emit()

    # ------------------------------------------------------------------
    # Mensagens
    # ------------------------------------------------------------------
    def _on_input_rejected(self) -> None:
        """Explica a tecla recusada em vez de absorvê-la em silêncio."""
        field = self.sender()
        if not isinstance(field, (RangedSpinBox, RangedIntSpinBox)):
            return
        self._set_field_error(field, True)
        self._rejected_field = field
        self._show_feedback(
            f"“{field.accessibleName()}” aceita apenas {field.range_description()}. "
            "O valor digitado foi recusado.",
            "error",
        )
        self._rejection_timer.start()

    def _clear_field_highlight(self) -> None:
        if self._rejected_field is not None:
            self._set_field_error(self._rejected_field, False)
            self._rejected_field = None

    def _cancel_rejection_feedback(self) -> None:
        self._rejection_timer.stop()
        self._clear_field_highlight()

    def _clear_rejection_feedback(self) -> None:
        self._cancel_rejection_feedback()
        self._refresh_draw_state()

    @staticmethod
    def _set_field_error(field: QWidget, active: bool) -> None:
        field.setProperty("state", "error" if active else "")
        field.style().unpolish(field)
        field.style().polish(field)

    def _show_feedback(self, message: str, state: str) -> None:
        self.validation_label.setText(message)
        self.validation_label.setProperty("state", state)
        self.validation_label.style().unpolish(self.validation_label)
        self.validation_label.style().polish(self.validation_label)

    def show_message(self, message: str, state: str = "") -> None:
        """Mostra uma mensagem de resultado (sucesso ou erro) abaixo dos campos."""
        self._show_feedback(message, state)

    # ------------------------------------------------------------------
    # Modo paramétrico
    # ------------------------------------------------------------------
    def is_parametric_enabled(self) -> bool:
        """Informa se o fluxo paramétrico está ativo."""
        return self._parametric_enabled

    def set_busy(self, busy: bool) -> None:
        """Bloqueia a ação principal enquanto um cálculo está em curso."""
        self._busy = busy
        self.draw_button.setText("Aplicando..." if busy else "Aplicar operadores")
        self._refresh_draw_state()

    def set_parametric_enabled(self, enabled: bool) -> None:
        """Evita que parâmetros do gerador sejam confundidos com malhas importadas."""
        changed = enabled != self._parametric_enabled
        self._parametric_enabled = enabled
        self.group_1.setEnabled(enabled)
        self.group_2.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)
        self._refresh_mode_hint()
        self._refresh_draw_state()
        if changed:
            self.parametric_mode_changed.emit(enabled)

    def _refresh_mode_hint(self) -> None:
        """Explica por que os parâmetros (e talvez a transformação) estão inativos."""
        if self._parametric_enabled:
            self.mode_hint.hide()
            return
        if self._transform_enabled:
            text = (
                "Este é um modelo importado. Os parâmetros do casco não se aplicam a "
                "ele, mas você pode usar “Transformar objeto” abaixo. Carregue um casco "
                "inicial (SD, P ou D) para voltar à edição paramétrica."
            )
        else:
            text = (
                "Superfície NURBS em edição. Arraste as esferas na cena 3D para mover "
                "os pontos de controle. Use “Concluir edição de superfície”, no menu "
                "Arquivo, para voltar a transformar o objeto."
            )
        self.mode_hint.setText(text)
        self.mode_hint.show()

    def set_model_info(
        self,
        name: str,
        kind: str,
        points: int,
        cells: int,
        dimensions: tuple[float, float, float],
        dimension_unit: str,
    ) -> None:
        """Atualiza o resumo do objeto que está no visualizador."""
        self.model_name.setText(name)
        self.model_kind.setText(kind)
        formatted_points = f"{points:,}".replace(",", ".")
        formatted_cells = f"{cells:,}".replace(",", ".")
        self.model_geometry.setText(
            f"{formatted_points} pontos · {formatted_cells} faces/células\n"
            f"{dimensions[0]:.2f} × {dimensions[1]:.2f} × {dimensions[2]:.2f} "
            f"{dimension_unit}"
        )
