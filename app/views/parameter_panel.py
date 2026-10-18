"""Painel Qt para os parâmetros de geração do casco."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.hull_generator import ChineOptions, HullGenerator, StepOptions
from app.models.attributes import HullDesign
from app.models.profiles import HullProfile
from app.models.transforms import TransformParameters
from app.views.controls import Section, SliderField

LIVE_UPDATE_DELAY_MS = 80
"""Espera após o último ajuste antes de redesenhar no modo ao vivo."""

STEP_DEFAULTS = (
    # posição (% do comprimento a partir da proa), altura na quilha (mm),
    # altura na quina (mm), ângulo (°), arco (cm)
    (40.0, 30.0, 50.0, 10.0, 0.0),
    (60.0, 30.0, 50.0, 10.0, 0.0),
    (75.0, 25.0, 40.0, 10.0, 0.0),
)


class StepControls:
    """Campos de um redan, agrupados numa seção com interruptor."""

    def __init__(self, number: int, defaults: tuple[float, ...], parent: QWidget) -> None:
        position, keel, chine, sweep, curve = defaults
        note = " · recomendado para L > 15 m" if number == 2 else ""
        note = " · uso excepcional" if number == 3 else note
        self.section = Section(
            f"Redan {number}{note}",
            parent,
            expanded=number == 1,
            switchable=True,
            switched_on=False,
        )
        self.position = SliderField(position, 15.0, 85.0, 1, " %", 1.0)
        self.height_keel = SliderField(keel, 0.0, 300.0, 0, " mm", 1.0)
        self.height_chine = SliderField(chine, 0.0, 300.0, 0, " mm", 1.0)
        self.sweep = SliderField(sweep, -45.0, 45.0, 1, "°", 0.5)
        self.curve = SliderField(curve, -50.0, 50.0, 1, " cm", 0.5)
        self.defaults = defaults
        self.section.add_row(
            "% do comprimento a partir da proa", self.position,
            "Posição do redan na quilha, medida da proa para ré.",
        )
        self.section.add_row(
            "Altura na quilha", self.height_keel,
            "Quanto o fundo sobe, na linha de centro, logo atrás do redan.",
        )
        self.section.add_row(
            "Altura na quina", self.height_chine,
            "Quanto o fundo sobe, junto à quina, logo atrás do redan.",
        )
        self.section.add_row(
            "Ângulo com a estação", self.sweep,
            "Inclinação da linha do redan em planta. Positivo: a ponta na quina fica mais a ré.",
        )
        self.section.add_row(
            "Arco para vante/ré", self.curve,
            "Curvatura da linha do redan no meio da meia-boca. Positivo: arco para vante.",
        )

    def fields(self) -> tuple[SliderField, ...]:
        return (self.position, self.height_keel, self.height_chine, self.sweep, self.curve)

    def options(self) -> StepOptions:
        return StepOptions(
            position=self.position.value() / 100.0,
            height_keel=self.height_keel.value() / 1000.0,
            height_chine=self.height_chine.value() / 1000.0,
            sweep=self.sweep.value(),
            curve=self.curve.value() / 100.0,
        )

    def reset(self) -> None:
        for field, value in zip(self.fields(), self.defaults):
            field.setValue(value)
        self.section.set_on(False)


class ParameterPanel(QWidget):
    """Formulário com abas para dimensões, ajuste, quina, redans e objeto."""

    draw_requested = Signal()
    live_update_requested = Signal()
    transform_requested = Signal(object)
    parameters_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._parametric_enabled = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Modelagem do casco")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        layout.addWidget(self._create_model_group())

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("parameterTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._create_hull_tab(), "Casco")
        self.tabs.addTab(self._create_fairing_tab(), "Ajuste")
        self.tabs.addTab(self._create_chine_tab(), "Quina")
        self.tabs.addTab(self._create_steps_tab(), "Redans")
        self.tabs.addTab(self._create_transform_tab(), "Objeto")
        layout.addWidget(self.tabs)

        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        layout.addWidget(self.validation_label)

        self.live_update = QCheckBox("Atualizar ao vivo")
        self.live_update.setChecked(True)
        self.live_update.setToolTip(
            "Redesenha o casco enquanto os controles são ajustados, sem reposicionar a câmera."
        )
        layout.addWidget(self.live_update)

        self.draw_button = QPushButton("Atualizar modelo 3D")
        self.draw_button.setObjectName("primaryButton")
        self.draw_button.setMinimumHeight(40)
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
        layout.addStretch()

        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(LIVE_UPDATE_DELAY_MS)
        self._live_timer.timeout.connect(self._emit_live_update)

        for field in self._all_shape_fields():
            field.valueChanged.connect(self._on_parameter_edited)
        for section in (self.chine_section, *(step.section for step in self.step_controls)):
            section.switched.connect(self._on_parameter_edited)
        self.closed_deck.toggled.connect(self._on_parameter_edited)
        self._validate_inputs()

    # ------------------------------------------------------------------ abas

    def _create_model_group(self) -> Section:
        section = Section("Modelo atual", self, expanded=False)
        self.model_name = QLabel("Casco paramétrico")
        self.model_kind = QLabel("Gerado no Odisseu")
        self.model_geometry = QLabel("—")
        self.model_geometry.setWordWrap(True)
        section.add_row("Nome", self.model_name)
        section.add_row("Origem", self.model_kind)
        section.add_row("Geometria", self.model_geometry)
        return section

    @staticmethod
    def _tab_page(*sections: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)
        for section in sections:
            layout.addWidget(section)
        layout.addStretch()
        return page

    def _create_hull_tab(self) -> QWidget:
        self.dimension_group = Section("Dimensões", self)
        self.total_length = SliderField(12.0, 2.0, 60.0, 2, " m", 0.1)
        self.midship_length = SliderField(6.0, 0.5, 40.0, 2, " m", 0.1)
        self.beam = SliderField(4.0, 0.5, 15.0, 2, " m", 0.05)
        self.draft = SliderField(1.8, 0.1, 6.0, 2, " m", 0.05)
        self.bow_angle = SliderField(32.0, 1.0, 89.0, 1, "°", 0.5)
        self.dimension_group.add_row(
            "Comprimento total", self.total_length, "Comprimento do casco entre proa e popa."
        )
        self.dimension_group.add_row(
            "Seção média", self.midship_length, "Extensão aproximada da região de boca máxima."
        )
        self.dimension_group.add_row("Boca", self.beam, "Largura máxima do casco, no convés.")
        self.dimension_group.add_row(
            "Calado", self.draft, "Distância vertical entre a linha d'água e a quilha."
        )
        self.dimension_group.add_row(
            "Ângulo de proa", self.bow_angle,
            "Ângulo de entrada da proa; valores menores deixam a proa mais afiada.",
        )

        self.shape_group = Section("Forma do casco", self)
        self.freeboard = SliderField(1.0, 0.1, 5.0, 2, " m", 0.05)
        self.transom_ratio = SliderField(0.65, 0.0, 0.95, 2, "", 0.05)
        self.deadrise = SliderField(12.0, 0.0, 35.0, 1, "°", 0.5)
        self.concavity = SliderField(0.0, 0.0, 1.0, 2, "", 0.05)
        self.shape_group.add_row(
            "Borda livre", self.freeboard, "Altura do convés acima da linha d'água na seção média."
        )
        self.shape_group.add_row(
            "Espelho de popa", self.transom_ratio,
            "Largura do espelho de popa como fração da boca. Zero gera popa em ponta.",
        )
        self.shape_group.add_row(
            "Pé de caverna", self.deadrise,
            "Ângulo do fundo junto à quilha. Valores maiores formam um fundo em V.",
        )
        self.shape_group.add_row(
            "Concavidade das estações", self.concavity, "Quão cheio é o bojo (0 a 1)."
        )

        self.mesh_group = Section("Malha", self, expanded=False)
        self.stations = SliderField(64, 4, 512, 0, "", 4)
        self.section_points = SliderField(33, 5, 257, 0, "", 2)
        self.mesh_group.add_row(
            "Linhas longitudinais", self.stations,
            "Quantidade de seções ao longo do comprimento. Mais linhas aumentam a suavidade.",
        )
        self.mesh_group.add_row(
            "Pontos por seção", self.section_points,
            "Pontos na parte submersa de cada seção. Use valores ímpares para manter um ponto na quilha.",
        )

        self.constraint_group = Section("Restrições", self, expanded=False)
        self.minimum_radius = SliderField(2.0, 0.01, 20.0, 2, " m", 0.1)
        self.constraint_group.add_row(
            "Raio mínimo", self.minimum_radius, "Limite usado para validar a curvatura atual."
        )
        return self._tab_page(
            self.dimension_group, self.shape_group, self.mesh_group, self.constraint_group
        )

    def _create_fairing_tab(self) -> QWidget:
        self.fairing_group = Section("Convés e espelho", self)
        self.deck_camber = SliderField(2.0, 0.0, 10.0, 1, " %", 0.5)
        self.transom_camber = SliderField(0.0, 0.0, 30.0, 1, " %", 0.5)
        self.closed_deck = QCheckBox("Fechar convés")
        self.closed_deck.setToolTip(
            "Fecha o topo do casco. Marque para exportar uma malha estanque, "
            "necessária para calcular volume, CFD ou impressão 3D."
        )
        self.fairing_group.add_row(
            "Abaulamento do convés", self.deck_camber,
            "Altura do convés na linha de centro acima da borda, em % da boca local.",
        )
        self.fairing_group.add_row(
            "Curvatura do espelho", self.transom_camber,
            "Quanto o centro do espelho avança para ré, em % da boca do espelho.",
        )
        self.fairing_group.add_widget(self.closed_deck)

        self.topsides_group = Section("Obras mortas", self)
        self.bow_flare = SliderField(8.0, 0.0, 50.0, 1, " %", 0.5)
        self.sheer_bow = SliderField(15.0, 0.0, 100.0, 0, " %", 1)
        self.stern_flare = SliderField(8.0, 0.0, 50.0, 1, " %", 0.5)
        self.sheer_stern = SliderField(0.0, 0.0, 100.0, 0, " %", 1)
        self.topsides_group.add_row(
            "Abertura na proa", self.bow_flare,
            "Quanto a boca no convés supera a da linha d'água, na proa.",
        )
        self.topsides_group.add_row(
            "Altura na proa", self.sheer_bow,
            "Elevação do convés na proa (tosamento), em % da borda livre.",
        )
        self.topsides_group.add_row(
            "Abertura na popa", self.stern_flare,
            "Quanto a boca no convés supera a da linha d'água, na popa.",
        )
        self.topsides_group.add_row(
            "Altura na popa", self.sheer_stern,
            "Elevação do convés na popa, em % da borda livre.",
        )
        return self._tab_page(self.fairing_group, self.topsides_group)

    def _create_chine_tab(self) -> QWidget:
        self.chine_section = Section("Quina viva", self, switchable=True, switched_on=False)
        self.chine_height_bow = SliderField(55.0, 5.0, 95.0, 0, " %", 1)
        self.chine_height_stern = SliderField(35.0, 5.0, 95.0, 0, " %", 1)
        self.chine_width = SliderField(50.0, 0.0, 500.0, 0, " mm", 5)
        self.chine_angle = SliderField(0.0, -30.0, 30.0, 1, "°", 0.5)
        self.chine_section.add_row(
            "Altura na proa", self.chine_height_bow,
            "Altura da quina na proa, em % do pontal (da quilha ao convés).",
        )
        self.chine_section.add_row(
            "Altura na popa", self.chine_height_stern,
            "Altura da quina na popa, em % do pontal.",
        )
        self.chine_section.add_row(
            "Largura do flat", self.chine_width,
            "Faixa quase horizontal na quina, que desvia o spray.",
        )
        self.chine_section.add_row(
            "Ângulo do flat", self.chine_angle,
            "Inclinação do flat. Positivo: desce para fora.",
        )
        hint = QLabel(
            "A quina substitui o bojo arredondado por uma aresta viva entre o fundo "
            "e o costado, típica de cascos de planeio."
        )
        hint.setObjectName("secondaryText")
        hint.setWordWrap(True)
        return self._tab_page(self.chine_section, hint)

    def _create_steps_tab(self) -> QWidget:
        self.step_controls = [
            StepControls(number, defaults, self)
            for number, defaults in enumerate(STEP_DEFAULTS, start=1)
        ]
        self.steps_hint = QLabel()
        self.steps_hint.setObjectName("secondaryText")
        self.steps_hint.setWordWrap(True)
        return self._tab_page(
            self.steps_hint, *(step.section for step in self.step_controls)
        )

    def _create_transform_tab(self) -> QWidget:
        self.transform_group = Section("Transformar objeto", self)
        description = QLabel(
            "Aplique deslocamento, rotação ou escala ao modelo inteiro. "
            "As rotações usam o centro do objeto como pivô."
        )
        description.setObjectName("secondaryText")
        description.setWordWrap(True)
        self.transform_group.add_widget(description)

        form_holder = QWidget()
        form = QFormLayout(form_holder)
        form.setContentsMargins(0, 0, 0, 0)
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
        self.transform_group.add_widget(form_holder)

        self.clear_transform_button = QPushButton("Limpar campos")
        self.clear_transform_button.clicked.connect(self.clear_transform_fields)
        self.apply_transform_button = QPushButton("Aplicar transformação")
        self.apply_transform_button.setObjectName("secondaryButton")
        self.apply_transform_button.clicked.connect(self._request_transform)
        buttons_holder = QWidget()
        buttons = QHBoxLayout(buttons_holder)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.clear_transform_button)
        buttons.addWidget(self.apply_transform_button, 1)
        self.transform_group.add_widget(buttons_holder)
        return self._tab_page(self.transform_group)

    @staticmethod
    def _spin_box(value: float, minimum: float, maximum: float) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(minimum, maximum)
        field.setValue(value)
        field.setDecimals(2)
        field.setSingleStep(0.1)
        field.setAccelerated(True)
        field.setMinimumHeight(30)
        return field

    # ------------------------------------------------------- transformações

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

    # ------------------------------------------------------------ parâmetros

    def _parameter_fields(self) -> tuple[SliderField, ...]:
        """Campos definidos pelos perfis, na ordem de ``set_profile_values``."""
        return (
            self.total_length,
            self.midship_length,
            self.beam,
            self.draft,
            self.bow_angle,
            self.stations,
            self.concavity,
            self.minimum_radius,
            self.freeboard,
            self.transom_ratio,
            self.deadrise,
        )

    def _fairing_fields(self) -> tuple[SliderField, ...]:
        return (
            self.deck_camber,
            self.transom_camber,
            self.bow_flare,
            self.sheer_bow,
            self.stern_flare,
            self.sheer_stern,
        )

    def _chine_fields(self) -> tuple[SliderField, ...]:
        return (
            self.chine_height_bow,
            self.chine_height_stern,
            self.chine_width,
            self.chine_angle,
        )

    def _all_shape_fields(self) -> tuple[SliderField, ...]:
        step_fields = tuple(field for step in self.step_controls for field in step.fields())
        return (
            *self._parameter_fields(),
            self.section_points,
            *self._fairing_fields(),
            *self._chine_fields(),
            *step_fields,
        )

    def generator_options(self) -> dict[str, Any]:
        """Argumentos de ``HullGenerator`` correspondentes ao formulário."""
        chine = None
        if self.chine_section.is_on():
            chine = ChineOptions(
                height_bow=self.chine_height_bow.value() / 100.0,
                height_stern=self.chine_height_stern.value() / 100.0,
                flat_width=self.chine_width.value() / 1000.0,
                flat_angle=self.chine_angle.value(),
            )
        steps = tuple(
            step.options() for step in self.step_controls if step.section.is_on()
        )
        return {
            "total_length": self.total_length.value(),
            "midship_length": self.midship_length.value(),
            "beam": self.beam.value(),
            "draft": self.draft.value(),
            "bow_angle": self.bow_angle.value(),
            "station_concavity": self.concavity.value(),
            "stations": self.stations.value(),
            "section_points": self.section_points.value(),
            "freeboard": self.freeboard.value(),
            "transom_ratio": self.transom_ratio.value(),
            "deadrise": self.deadrise.value(),
            "closed_deck": self.closed_deck.isChecked(),
            "sheer_bow": self.sheer_bow.value() / 100.0,
            "sheer_stern": self.sheer_stern.value() / 100.0,
            "bow_flare": self.bow_flare.value() / 100.0,
            "stern_flare": self.stern_flare.value() / 100.0,
            "deck_camber": self.deck_camber.value() / 100.0,
            "transom_camber": self.transom_camber.value() / 100.0,
            "chine": chine,
            "steps": steps if chine is not None else (),
        }

    def _on_parameter_edited(self, _value: object = None) -> None:
        if self._validate_inputs() and self.live_update.isChecked() and self._parametric_enabled:
            self._live_timer.start()

    def _emit_live_update(self) -> None:
        if self._parametric_enabled and self._validate_inputs():
            self.live_update_requested.emit()

    def _evaluate(self) -> tuple[bool, str]:
        """Valida o formulário e devolve (válido, mensagem)."""
        if self.section_points.value() % 2 == 0:
            return False, "Use um número ímpar de pontos por seção para incluir a quilha."
        if self.midship_length.value() > self.total_length.value():
            return False, "A seção média não pode ser maior que o comprimento total."
        maximum_radius = 0.5 * self.midship_length.value() + self.draft.value()
        if self.minimum_radius.value() > maximum_radius:
            return False, (
                "O raio mínimo excede o limite estimado de "
                f"{maximum_radius:.2f} m para estas dimensões."
            )
        try:
            HullGenerator(**self.generator_options())
        except ValueError as error:
            return False, str(error)
        return True, f"Parâmetros válidos · raio máximo estimado: {maximum_radius:.2f} m"

    def _validate_inputs(self, _value: object = None) -> bool:
        """Oferece feedback imediato sobre relações entre os parâmetros."""
        valid, message = self._evaluate()
        self.validation_label.setText(message)
        self.validation_label.setProperty("state", "valid" if valid else "error")
        self.validation_label.style().unpolish(self.validation_label)
        self.validation_label.style().polish(self.validation_label)
        self.draw_button.setEnabled(valid and self._parametric_enabled)

        chine_on = self.chine_section.is_on()
        for step in self.step_controls:
            step.section.setEnabled(chine_on)
        self.steps_hint.setText(
            "Os redans são degraus transversais no fundo: atrás de cada um o fundo sobe, "
            "reduzindo a área molhada em planeio."
            if chine_on
            else "Os redans exigem quina viva. Ligue a quina na aba “Quina” para usá-los."
        )
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

    def _set_silently(self, action) -> None:
        """Aplica vários valores sem disparar um redesenho ao vivo para cada um."""
        live = self.live_update.isChecked()
        self.live_update.setChecked(False)
        try:
            action()
        finally:
            self.live_update.setChecked(live)
            self._live_timer.stop()

    def reset_defaults(self) -> None:
        """Restaura o conjunto inicial de parâmetros do casco."""

        def reset() -> None:
            defaults = (12.0, 6.0, 4.0, 1.8, 32.0, 64, 0.0, 2.0, 1.0, 0.65, 12.0)
            for field, value in zip(self._parameter_fields(), defaults):
                field.setValue(value)
            self.section_points.setValue(33)
            for field, value in zip(self._fairing_fields(), (2.0, 0.0, 8.0, 15.0, 8.0, 0.0)):
                field.setValue(value)
            for field, value in zip(self._chine_fields(), (55.0, 35.0, 50.0, 0.0)):
                field.setValue(value)
            self.chine_section.set_on(False)
            for step in self.step_controls:
                step.reset()
            self.closed_deck.setChecked(False)

        self._set_silently(reset)
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
            profile.freeboard,
            profile.transom_ratio,
            profile.deadrise,
        )

        def apply() -> None:
            for field, value in zip(self._parameter_fields(), values):
                field.setValue(value)

        self._set_silently(apply)
        self._validate_inputs()

    def set_parametric_enabled(self, enabled: bool) -> None:
        """Evita que parâmetros do gerador sejam confundidos com malhas importadas."""
        self._parametric_enabled = enabled
        for index in range(4):
            self.tabs.widget(index).setEnabled(enabled)
        self.reset_button.setEnabled(enabled)
        if enabled:
            self.mode_hint.hide()
        else:
            self.mode_hint.setText(
                "Este é um modelo importado. Os parâmetros do casco não se aplicam a "
                "ele, mas você pode usar a aba “Objeto”. Use “Novo casco” para voltar "
                "à edição paramétrica."
            )
            self.mode_hint.show()
            self.tabs.setCurrentIndex(4)
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
