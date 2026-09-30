"""Painel Qt para os parâmetros de geração do casco."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.models.attributes import HullDesign
from app.models.transforms import TransformParameters
from app.models.profiles import HullProfile


class ParameterPanel(QWidget):
    """Formulário dos parâmetros dos Grupos 1 e 2."""

    draw_requested = Signal()
    transform_requested = Signal(object)
    parameters_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._parametric_enabled = True
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
        layout.addWidget(self.validation_label)

        self.draw_button = QPushButton("Atualizar modelo 3D")
        self.draw_button.setObjectName("primaryButton")
        self.draw_button.setMinimumHeight(42)
        self.draw_button.clicked.connect(self.draw_requested)

        self.reset_button = QPushButton("Restaurar valores")
        self.reset_button.setMinimumHeight(36)
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

        for field in (*self._parameter_fields(), self.section_points):
            field.valueChanged.connect(self._validate_inputs)
        self._validate_inputs()

    def _create_model_group(self) -> QGroupBox:
        group = QGroupBox("Modelo atual")
        form = QFormLayout(group)
        self.model_name = QLabel("Casco paramétrico")
        self.model_kind = QLabel("Gerado no Odisseu")
        self.model_geometry = QLabel("—")
        self.model_geometry.setWordWrap(True)
        form.addRow("Nome", self.model_name)
        form.addRow("Origem", self.model_kind)
        form.addRow("Geometria", self.model_geometry)
        return group

    def _spin_box(self, value: float, minimum: float, maximum: float) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(minimum, maximum)
        field.setValue(value)
        field.setDecimals(2)
        field.setSingleStep(0.1)
        field.setAccelerated(True)
        field.setMinimumHeight(32)
        return field

    def _create_group_1(self) -> QGroupBox:
        group = QGroupBox("Grupo 1 - Dimensões")
        form = QFormLayout(group)
        self.total_length = self._spin_box(12.0, 0.1, 1000.0)
        self.midship_length = self._spin_box(6.0, 0.1, 1000.0)
        self.beam = self._spin_box(4.0, 0.1, 1000.0)
        self.draft = self._spin_box(1.8, 0.1, 1000.0)
        self.bow_angle = self._spin_box(32.0, 1.0, 89.0)
        self.stations = QSpinBox()
        self.stations.setRange(4, 512)
        self.stations.setValue(64)
        self.stations.setSingleStep(4)
        self.stations.setAccelerated(True)
        self.stations.setMinimumHeight(32)
        self.section_points = QSpinBox()
        self.section_points.setRange(5, 257)
        self.section_points.setValue(33)
        self.section_points.setSingleStep(2)
        self.section_points.setAccelerated(True)
        self.section_points.setMinimumHeight(32)
        for field in (
            self.total_length,
            self.midship_length,
            self.beam,
            self.draft,
        ):
            field.setSuffix(" m")
        self.total_length.setToolTip("Comprimento do casco entre proa e popa.")
        self.midship_length.setToolTip("Extensão aproximada da região de boca máxima.")
        self.beam.setToolTip("Largura máxima do casco.")
        self.draft.setToolTip("Distância vertical entre a linha d'água e a quilha.")
        self.bow_angle.setSuffix("°")
        self.bow_angle.setToolTip("Ângulo de entrada da proa; valores menores deixam a proa mais afiada.")
        self.stations.setToolTip(
            "Quantidade de seções ao longo do comprimento. Mais linhas aumentam a suavidade e o custo de geração."
        )
        self.section_points.setToolTip(
            "Pontos em cada seção transversal, de borda livre a borda livre. "
            "Use valores ímpares para manter um ponto sobre a quilha."
        )
        form.addRow("Comprimento total", self.total_length)
        form.addRow("Seção média", self.midship_length)
        form.addRow("Boca", self.beam)
        form.addRow("Calado", self.draft)
        form.addRow("Ângulo de proa", self.bow_angle)
        form.addRow("Linhas longitudinais", self.stations)
        form.addRow("Pontos por seção", self.section_points)
        return group

    def _create_group_2(self) -> QGroupBox:
        group = QGroupBox("Grupo 2 - Restrições")
        form = QFormLayout(group)
        self.concavity = self._spin_box(0.0, 0.0, 1.0)
        self.minimum_radius = self._spin_box(2.0, 0.01, 1000.0)
        self.concavity.setSingleStep(0.05)
        self.minimum_radius.setSuffix(" m")
        self.concavity.setToolTip("Controla o formato transversal das estações.")
        self.minimum_radius.setToolTip("Limite usado para validar a curvatura atual.")
        form.addRow("Concavidade das estações", self.concavity)
        form.addRow("Raio mínimo", self.minimum_radius)
        return group

    def _create_transform_group(self) -> QGroupBox:
        group = QGroupBox("Transformar objeto")
        layout = QVBoxLayout(group)

        description = QLabel(
            "Aplique deslocamento, rotação ou escala ao modelo inteiro. "
            "As rotações usam o centro do objeto como pivô."
        )
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        self.translation_x = self._spin_box(0.0, -10000.0, 10000.0)
        self.translation_y = self._spin_box(0.0, -10000.0, 10000.0)
        self.translation_z = self._spin_box(0.0, -10000.0, 10000.0)
        self.rotation_x = self._spin_box(0.0, -360.0, 360.0)
        self.rotation_y = self._spin_box(0.0, -360.0, 360.0)
        self.rotation_z = self._spin_box(0.0, -360.0, 360.0)
        self.uniform_scale = self._spin_box(1.0, 0.01, 100.0)
        self.uniform_scale.setDecimals(3)
        self.uniform_scale.setSingleStep(0.05)
        for field in (self.rotation_x, self.rotation_y, self.rotation_z):
            field.setSuffix("°")

        form.addRow("Deslocamento X", self.translation_x)
        form.addRow("Deslocamento Y", self.translation_y)
        form.addRow("Deslocamento Z", self.translation_z)
        form.addRow("Rotação X", self.rotation_x)
        form.addRow("Rotação Y", self.rotation_y)
        form.addRow("Rotação Z", self.rotation_z)
        form.addRow("Escala uniforme", self.uniform_scale)
        layout.addLayout(form)

        self.clear_transform_button = QPushButton("Limpar campos")
        self.clear_transform_button.clicked.connect(self.clear_transform_fields)
        self.apply_transform_button = QPushButton("Aplicar transformação")
        self.apply_transform_button.setObjectName("secondaryButton")
        self.apply_transform_button.clicked.connect(self._request_transform)

        buttons = QHBoxLayout()
        buttons.addWidget(self.clear_transform_button)
        buttons.addWidget(self.apply_transform_button, 1)
        layout.addLayout(buttons)
        return group

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
            return
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

    def _parameter_fields(self) -> tuple[QDoubleSpinBox | QSpinBox, ...]:
        return (
            self.total_length,
            self.midship_length,
            self.beam,
            self.draft,
            self.bow_angle,
            self.stations,
            self.concavity,
            self.minimum_radius,
        )

    def _validate_inputs(self, _value: float | None = None) -> bool:
        """Oferece feedback imediato sobre relações entre os parâmetros."""
        if self.section_points.value() % 2 == 0:
            self.validation_label.setText(
                "Use um número ímpar de pontos por seção para incluir a quilha."
            )
            self.validation_label.setProperty("state", "error")
            valid = False
        elif self.midship_length.value() > self.total_length.value():
            self.validation_label.setText(
                "A seção média não pode ser maior que o comprimento total."
            )
            self.validation_label.setProperty("state", "error")
            valid = False
        else:
            maximum_radius = 0.5 * self.midship_length.value() + self.draft.value()
            if self.minimum_radius.value() > maximum_radius:
                self.validation_label.setText(
                    "O raio mínimo excede o limite estimado de "
                    f"{maximum_radius:.2f} m para estas dimensões."
                )
                self.validation_label.setProperty("state", "error")
                valid = False
            else:
                self.validation_label.setText(
                    f"Parâmetros válidos · raio máximo estimado: {maximum_radius:.2f} m"
                )
                self.validation_label.setProperty("state", "valid")
                valid = True

        self.validation_label.style().unpolish(self.validation_label)
        self.validation_label.style().polish(self.validation_label)
        self.draw_button.setEnabled(valid and self._parametric_enabled)
        self.parameters_changed.emit()
        return valid

    def current_design(self) -> HullDesign:
        """Retorna as variáveis de projeto digitadas no formulário."""
        return HullDesign(
            total_length=self.total_length.value(),
            midship_length=self.midship_length.value(),
            beam=self.beam.value(),
            draft=self.draft.value(),
            bow_angle=self.bow_angle.value(),
            concavity=self.concavity.value(),
        )

    def is_parametric_enabled(self) -> bool:
        return self._parametric_enabled

    def reset_defaults(self) -> None:
        """Restaura o conjunto inicial de parâmetros do casco."""
        defaults = (12.0, 6.0, 4.0, 1.8, 32.0, 64, 0.0, 2.0)
        for field, value in zip(self._parameter_fields(), defaults):
            field.setValue(value)
        self.section_points.setValue(33)
        self._validate_inputs()

    def set_profile_values(self, profile: HullProfile, stations: int = 64) -> None:
        """Carrega um preset sem bloquear a edição manual dos campos."""
        values = (
            profile.total_length,
            profile.midship_length,
            profile.beam,
            profile.draft,
            profile.bow_angle,
            stations,
            profile.concavity,
            profile.minimum_radius,
        )
        for field, value in zip(self._parameter_fields(), values):
            field.setValue(value)
        self._validate_inputs()

    def set_parametric_enabled(self, enabled: bool) -> None:
        """Evita que parâmetros do gerador sejam confundidos com malhas importadas."""
        self._parametric_enabled = enabled
        self.dimension_group.setEnabled(enabled)
        self.constraint_group.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)
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
