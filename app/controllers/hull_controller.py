"""Coordenação entre o painel, os operadores de forma e o visualizador."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox

from app.models.hull_model import HullModel
from app.models.hull_types import HULL_TYPE_NAMES, initial_hull
from app.models.shape_operators import (
    DEFAULT_CHINE_THICKNESS,
    DOUBLE_CHINE,
    GROUP_1,
    GROUP_2,
    OperatorError,
    RadiusNotAchievable,
    apply_parameters,
    chine_type,
    set_chine_type,
    set_station_concavity,
    station_concavity,
)


class HullController(QObject):
    """Guarda o casco paramétrico atual e aplica os operadores pedidos no painel."""

    hull_generated = Signal()

    #: Acrescentado ao nome do casco depois que operadores são aplicados.
    MODIFIED_SUFFIX = " (modificado)"

    def __init__(self, viewer, parameter_view) -> None:
        super().__init__(parameter_view)
        self.viewer = viewer
        self.parameter_view = parameter_view
        #: Casco paramétrico exibido (``None`` enquanto o modelo é importado).
        self.model: HullModel | None = None
        #: Casco antes da última aplicação de operadores (entrada da comparação).
        self.previous: HullModel | None = None
        self.parameter_view.draw_requested.connect(self.draw)
        self.parameter_view.mesh_options_changed.connect(self.refresh_mesh)

    def _dialog_parent(self):
        """Usa a janela principal como pai, e não o painel lateral."""
        return self.parameter_view.window()

    # ------------------------------------------------------------------
    # Carga de modelos
    # ------------------------------------------------------------------
    def load_initial(self, hull_type: str) -> None:
        """Carrega um dos cascos iniciais (planeio, semi-deslocamento ou deslocamento)."""
        self.set_model(initial_hull(hull_type), fit=True)
        self.viewer.status_message.emit(
            f"Casco inicial criado: {HULL_TYPE_NAMES[hull_type]}"
        )

    def set_model(self, model: HullModel, fit: bool = True, previous: HullModel | None = None) -> None:
        """Torna ``model`` o casco atual e o exibe."""
        self.previous = previous if previous is not None else model
        self.model = model
        self._show(model)
        self.parameter_view.sync_from(*self._form_state(model))
        if fit:
            self.viewer.fit_view()
        self.hull_generated.emit()

    def refresh_mesh(self) -> None:
        """Redesenha o casco atual (mudou a qualidade da malha ou o convés)."""
        if self.model is None or not self.parameter_view.is_parametric_enabled():
            return
        self._show(self.model)
        self.hull_generated.emit()

    def _show(self, model: HullModel) -> None:
        panel = self.parameter_view
        mesh = model.build_mesh(
            panel.mesh_resolution(), closed_deck=panel.closed_deck.isChecked()
        )
        self.viewer.set_hull(mesh)

    @staticmethod
    def _form_state(model: HullModel):
        concavities = {
            (station, line): station_concavity(model, station, line)
            for station in range(3)
            for line in ("upper", "lower")
        }
        return model.parameters(), chine_type(model), concavities

    # ------------------------------------------------------------------
    # Aplicação dos operadores
    # ------------------------------------------------------------------
    def draw(self) -> None:
        """Aplica ao casco os operadores dos campos alterados no painel."""
        panel = self.parameter_view
        if not panel.is_parametric_enabled() or self.model is None:
            return
        if not panel.has_pending_changes():
            panel.show_message(
                "Nenhum parâmetro foi alterado; o casco permanece como está.", "warning"
            )
            self.viewer.status_message.emit("Nenhuma modificação aplicada")
            return

        panel.set_busy(True)
        QGuiApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        try:
            try:
                result = self._apply(self.model)
            except RadiusNotAchievable as error:
                QMessageBox.warning(
                    self._dialog_parent(),
                    "Raio de curvatura inalcançável",
                    f"Informe outro valor para o parâmetro {error.parameter}.\n"
                    "O valor de entrada excedeu o limite máximo alcançável de "
                    f"{error.maximum:.6g} m.",
                )
                return
            except (OperatorError, ValueError) as error:
                QMessageBox.warning(
                    self._dialog_parent(), "Operador não aplicado", str(error)
                )
                return

            previous = self.model
            if not result.name.endswith(self.MODIFIED_SUFFIX):
                result.name += self.MODIFIED_SUFFIX
            self.model = result
            self.previous = previous
            self._show(result)
        finally:
            QGuiApplication.restoreOverrideCursor()
            panel.set_busy(False)

        panel.sync_from(*self._form_state(result))
        panel.show_message("Operadores aplicados com sucesso.", "valid")
        self.hull_generated.emit()
        self.viewer.status_message.emit("Casco modificado com sucesso")

    def _apply(self, model: HullModel) -> HullModel:
        """Chine → Grupo-1 → concavidade → Grupo-2, nesta ordem."""
        panel = self.parameter_view
        result = model

        kind = panel.pending_chine_type()
        if kind is not None:
            thickness = None
            if kind == DOUBLE_CHINE:
                thickness = tuple(
                    panel.value(name) if panel.value(name) > 1e-6 else default
                    for name, default in zip(("Ce", "Cm", "Cr"), DEFAULT_CHINE_THICKNESS)
                )
            result = set_chine_type(result, kind, thickness)

        pending = panel.pending_parameters()
        group_1 = {name: value for name, value in pending.items() if name in GROUP_1}
        group_2 = {name: value for name, value in pending.items() if name in GROUP_2}
        if kind not in (None, DOUBLE_CHINE):
            # Sem espessura de quina: o tipo escolhido já zerou Cₑ, Cₘ e Cᵣ.
            for name in ("Ce", "Cm", "Cr"):
                group_1.pop(name, None)
        result = apply_parameters(result, group_1)

        for (station, line), wanted in panel.pending_concavities().items():
            result = set_station_concavity(result, station, line, wanted)

        return apply_parameters(result, group_2)
