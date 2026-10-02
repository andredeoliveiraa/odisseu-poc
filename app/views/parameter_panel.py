"""Painel Qt para os parâmetros de geração do casco."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.hull_generator import HullGenerator
from app.models.constraints import HullConstraintValidator
from app.models.transforms import TransformParameters
from app.models.profiles import DEFAULT_PROFILE, HullProfile
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


class ParameterPanel(QWidget):
    """Formulário dos parâmetros dos Grupos 1 e 2."""

    draw_requested = Signal()
    transform_requested = Signal(object)
    parameters_changed = Signal()
    draw_availability_changed = Signal(bool)

    #: Tempo que um aviso de entrada recusada permanece visível.
    REJECTION_FEEDBACK_MS = 5000
    #: Largura máxima da coluna de rótulos, em pixels.
    LABEL_COLUMN_MAX = 210

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._parametric_enabled = True
        self._model_is_current = True
        self._busy = False
        self._validator = HullConstraintValidator()
        self._row_labels: list[QLabel] = []
        self._rejection_timer = QTimer(self)
        self._rejection_timer.setSingleShot(True)
        self._rejection_timer.setInterval(self.REJECTION_FEEDBACK_MS)
        self._rejection_timer.timeout.connect(self._clear_rejection_feedback)
        self._rejected_field: RangedSpinBox | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Modelagem do casco")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        description = QLabel(
            "Ajuste as dimensões e atualize o modelo. As medidas são exibidas em metros."
        )
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        layout.addWidget(description)

        layout.addWidget(self._create_model_group())
        self.dimension_group = self._create_group_1()
        self.constraint_group = self._create_group_2()
        layout.addWidget(self.dimension_group)
        layout.addWidget(self.constraint_group)

        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        self.validation_label.setObjectName("validationLabel")
        layout.addWidget(self.validation_label)

        self.draw_button = QPushButton("Atualizar modelo 3D")
        self.draw_button.setObjectName("primaryButton")
        self.draw_button.setMinimumHeight(42)
        self.draw_button.setToolTip(
            "Recalcula a malha com os valores atuais. Atalho: Enter em qualquer campo."
        )
        self.draw_button.setAccessibleName("Atualizar modelo 3D")
        self.draw_button.clicked.connect(self._request_draw)

        self.reset_button = QPushButton("Restaurar valores")
        self.reset_button.setMinimumHeight(36)
        self.reset_button.setToolTip(
            f"Volta aos valores do perfil {DEFAULT_PROFILE.name}."
        )
        self.reset_button.setAccessibleName("Restaurar valores padrão")
        self.reset_button.clicked.connect(self.reset_defaults)

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

        for field in self._parameter_fields():
            field.valueChanged.connect(self._on_parameter_edited)
            field.input_rejected.connect(self._on_input_rejected)
            field.lineEdit().returnPressed.connect(self._request_draw)
        self._align_label_columns()
        self._validate_inputs()

    # ------------------------------------------------------------------
    # Construção do formulário
    # ------------------------------------------------------------------
    def _add_row(
        self,
        form: QFormLayout,
        text: str,
        widget: QWidget,
        tooltip: str = "",
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
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

    def _align_label_columns(self) -> None:
        """Dá a todos os formulários a mesma coluna de rótulos.

        Cada ``QFormLayout`` calcula a largura da sua coluna isoladamente, o
        que desalinha os campos de um grupo para o outro. Fixar a maior
        largura necessária em todos os rótulos mantém uma coluna só.
        """
        if not self._row_labels:
            return
        width = min(
            max(label.sizeHint().width() for label in self._row_labels),
            self.LABEL_COLUMN_MAX,
        )
        for label in self._row_labels:
            label.setFixedWidth(width)

    def _create_model_group(self) -> CollapsibleSection:
        section = CollapsibleSection("Modelo atual", self, expanded=False)
        form = QFormLayout()
        self._configure_form(form)
        self.model_name = QLabel(DEFAULT_PROFILE.name)
        self.model_kind = QLabel("Gerado no Odisseu")
        self.model_geometry = QLabel("—")
        self.model_geometry.setWordWrap(True)
        self._add_row(form, "Nome", self.model_name)
        self._add_row(form, "Origem", self.model_kind)
        self._add_row(form, "Geometria", self.model_geometry)
        section.add_layout(form)
        return section

    def _spin_box(
        self,
        value: float,
        minimum: float,
        maximum: float,
        suffix: str = "",
    ) -> RangedSpinBox:
        field = RangedSpinBox()
        field.setRange(minimum, maximum)
        field.setSuffix(suffix)
        field.setValue(value)
        field.setDecimals(2)
        field.setSingleStep(0.1)
        field.setAccelerated(True)
        field.setMinimumHeight(32)
        field.setKeyboardTracking(False)
        return field

    def _create_group_1(self) -> CollapsibleSection:
        section = CollapsibleSection("Grupo 1 - Dimensões", self, expanded=True)
        form = QFormLayout()
        self._configure_form(form)
        profile = DEFAULT_PROFILE
        self.total_length = self._spin_box(profile.total_length, 0.1, 1000.0, " m")
        self.midship_length = self._spin_box(profile.midship_length, 0.1, 1000.0, " m")
        self.beam = self._spin_box(profile.beam, 0.1, 1000.0, " m")
        self.draft = self._spin_box(profile.draft, 0.1, 1000.0, " m")
        self.bow_angle = self._spin_box(profile.bow_angle, 1.0, 89.0, "°")

        self._add_row(
            form,
            "Comprimento total",
            self.total_length,
            "Comprimento do casco entre proa e popa. "
            f"Intervalo: {self.total_length.range_description()}.",
        )
        self._add_row(
            form,
            "Seção média",
            self.midship_length,
            "Extensão da região de boca máxima. Nunca maior que o comprimento "
            f"total. Intervalo: {self.midship_length.range_description()}.",
        )
        self._add_row(
            form,
            "Boca",
            self.beam,
            f"Largura máxima do casco. Intervalo: {self.beam.range_description()}.",
        )
        self._add_row(
            form,
            "Calado",
            self.draft,
            "Distância vertical entre a linha d'água e a quilha. "
            f"Intervalo: {self.draft.range_description()}.",
        )
        self._add_row(
            form,
            "Ângulo de proa",
            self.bow_angle,
            "Afilamento da entrada de proa; valores menores deixam a proa mais "
            f"afiada. Não altera a popa. Intervalo: {self.bow_angle.range_description()}.",
        )
        section.add_layout(form)
        return section

    def _create_group_2(self) -> CollapsibleSection:
        section = CollapsibleSection("Grupo 2 - Restrições", self, expanded=True)
        form = QFormLayout()
        self._configure_form(form)
        profile = DEFAULT_PROFILE
        self.concavity = self._spin_box(profile.concavity, 0.0, 1.0)
        self.concavity.setSingleStep(0.05)
        self.minimum_radius = self._spin_box(profile.minimum_radius, 0.01, 1000.0, " m")

        self._add_row(
            form,
            "Concavidade",
            self.concavity,
            "Quanto o costado é puxado para dentro entre o bojo e a borda. "
            "Adimensional, de 0 (cheio) a 1 (bem côncavo).",
        )
        self._add_row(
            form,
            "Raio mínimo",
            self.minimum_radius,
            "Raio de curvatura da quilha na seção mestra. Valores maiores "
            "achatam o fundo; valores menores deixam a quilha mais viva.",
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

        self._add_row(
            form, "Deslocamento X", self.translation_x,
            "Move o objeto ao longo do comprimento, em metros.",
        )
        self._add_row(
            form, "Deslocamento Y", self.translation_y,
            "Move o objeto ao longo da boca, em metros.",
        )
        self._add_row(
            form, "Deslocamento Z", self.translation_z,
            "Move o objeto na vertical, em metros.",
        )
        self._add_row(
            form, "Rotação X", self.rotation_x,
            "Gira o objeto em torno do eixo do comprimento.",
        )
        self._add_row(
            form, "Rotação Y", self.rotation_y,
            "Gira o objeto em torno do eixo da boca.",
        )
        self._add_row(
            form, "Rotação Z", self.rotation_z,
            "Gira o objeto em torno do eixo vertical.",
        )
        self._add_row(
            form, "Escala uniforme", self.uniform_scale,
            "Multiplica todas as dimensões do objeto pelo mesmo fator.",
        )
        section.add_layout(form)

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
    # Validação e estado
    # ------------------------------------------------------------------
    def _parameter_fields(self) -> tuple[RangedSpinBox, ...]:
        return (
            self.total_length,
            self.midship_length,
            self.beam,
            self.draft,
            self.bow_angle,
            self.concavity,
            self.minimum_radius,
        )

    def _request_draw(self) -> None:
        """Dispara o recálculo apenas quando ele é possível."""
        if self.draw_button.isEnabled():
            self.draw_requested.emit()

    def _on_parameter_edited(self, _value: float) -> None:
        """Marca o modelo como desatualizado e revalida o formulário."""
        # O campo deixa de parecer quebrado ao aceitar um valor, mas a
        # explicação da tecla recusada continua legível até expirar.
        self._clear_field_highlight()
        if self._parametric_enabled and self._model_is_current:
            self._model_is_current = False
        self._validate_inputs()
        self.parameters_changed.emit()

    def _on_input_rejected(self) -> None:
        """Explica a tecla recusada em vez de absorvê-la em silêncio."""
        field = self.sender()
        if not isinstance(field, RangedSpinBox):
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
        """Retira a borda de erro assim que o campo aceita um valor."""
        if self._rejected_field is not None:
            self._set_field_error(self._rejected_field, False)
            self._rejected_field = None

    def _cancel_rejection_feedback(self) -> None:
        """Encerra o aviso por inteiro, para um contexto novo."""
        self._rejection_timer.stop()
        self._clear_field_highlight()

    def _clear_rejection_feedback(self) -> None:
        self._cancel_rejection_feedback()
        self._validate_inputs()

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

    def current_generator(self) -> HullGenerator:
        """Monta um gerador com os valores do formulário."""
        return HullGenerator(
            total_length=self.total_length.value(),
            midship_length=self.midship_length.value(),
            beam=self.beam.value(),
            draft=self.draft.value(),
            bow_angle=self.bow_angle.value(),
            station_concavity=self.concavity.value(),
            minimum_radius=self.minimum_radius.value(),
        )

    def _evaluate(self) -> tuple[bool, str, str]:
        """Aplica as mesmas regras do desenho e devolve o parecer do formulário."""
        if not self._parametric_enabled:
            return False, "", ""

        try:
            generator = self.current_generator()
        except ValueError as error:
            return False, str(error), "error"

        result = self._validator.validate(
            generator,
            self.concavity.value(),
            self.minimum_radius.value(),
        )
        if not result.valid:
            return False, result.message, "error"
        if self._model_is_current:
            return (
                True,
                "Modelo em dia com o formulário · raio máximo desta seção: "
                f"{result.maximum_radius:.2f} m",
                "valid",
            )
        return (
            True,
            "Parâmetros alterados. Atualize o modelo 3D para ver o resultado.",
            "warning",
        )

    def _validate_inputs(self) -> bool:
        """Oferece feedback imediato usando as mesmas regras do desenho.

        O aviso de tecla recusada ocupa o rótulo por alguns segundos, mas nunca
        interfere na decisão de habilitar ou não a ação principal.
        """
        valid, message, state = self._evaluate()
        self._set_draw_enabled(valid and not self._busy)
        # Um parâmetro inválido tem prioridade sobre o aviso de tecla recusada.
        if state == "error" or not self._rejection_timer.isActive():
            self._show_feedback(message, state)
        return valid

    def _set_draw_enabled(self, enabled: bool) -> None:
        """Mantém botão e ação de menu com a mesma disponibilidade."""
        if self.draw_button.isEnabled() != enabled:
            self.draw_button.setEnabled(enabled)
            self.draw_availability_changed.emit(enabled)

    def mark_synced(self) -> None:
        """Registra que a malha exibida corresponde ao formulário."""
        self._model_is_current = True
        self._validate_inputs()

    def is_parametric_enabled(self) -> bool:
        """Informa se o fluxo paramétrico está ativo."""
        return self._parametric_enabled

    def set_busy(self, busy: bool) -> None:
        """Bloqueia a ação principal enquanto um recálculo está em curso."""
        self._busy = busy
        self.draw_button.setText(
            "Atualizando..." if busy else "Atualizar modelo 3D"
        )
        self._validate_inputs()

    def reset_defaults(self) -> None:
        """Restaura o conjunto inicial de parâmetros do casco."""
        self.set_profile_values(DEFAULT_PROFILE)

    def set_profile_values(self, profile: HullProfile) -> None:
        """Carrega um preset sem bloquear a edição manual dos campos."""
        self._cancel_rejection_feedback()
        for field, value in zip(self._parameter_fields(), profile.values):
            field.blockSignals(True)
            field.setValue(value)
            field.blockSignals(False)
        self._model_is_current = False
        self._validate_inputs()
        # Os campos passaram a corresponder a um preset: o seletor precisa saber.
        self.parameters_changed.emit()

    def matches_profile(self, profile: HullProfile) -> bool:
        """Verifica se os campos ainda correspondem a um preset."""
        return all(
            abs(field.value() - value) < 1e-9
            for field, value in zip(self._parameter_fields(), profile.values)
        )

    def set_parametric_enabled(self, enabled: bool) -> None:
        """Evita que parâmetros do gerador sejam confundidos com malhas importadas."""
        self._parametric_enabled = enabled
        self.dimension_group.setEnabled(enabled)
        self.constraint_group.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)
        # O rótulo continua no lugar: além da validação paramétrica, ele
        # responde pelo grupo de transformação, que segue ativo aqui.
        if enabled:
            self.mode_hint.hide()
        else:
            self.mode_hint.setText(
                "Este é um modelo importado. Os parâmetros do casco não se aplicam a "
                "ele, mas você pode usar “Transformar objeto” abaixo. Use “Novo casco” "
                "para voltar à edição paramétrica."
            )
            self.mode_hint.show()
        self._validate_inputs()

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
