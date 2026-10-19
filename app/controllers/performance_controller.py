"""Calcula hidrostática e resistência do casco gerado, sem travar a interface."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from app.hull_generator import HullGenerator
from app.models import hydrodynamics as hd

FROUDE_RANGE = np.arange(0.15, 0.4501, 0.025)
"""Faixa de Froude da curva, a mesma do conjunto ShipD (0,15 a 0,45)."""

RESISTANCE_DELAY_MS = 150
"""Espera após a última mudança antes de iniciar o cálculo da curva."""


class _ResistanceSignals(QObject):
    finished = Signal(int, object)


class _ResistanceJob(QRunnable):
    """Calcula a curva numa thread do pool; o resultado volta por sinal.

    ``latest`` devolve o token mais recente: se outro casco já foi pedido
    quando a tarefa começa, ela pula o cálculo e só avisa que terminou.
    """

    def __init__(self, token: int, latest, offsets, hydrostatics, design_speed: float) -> None:
        super().__init__()
        self.token = token
        self.latest = latest
        self.offsets = offsets
        self.hydrostatics = hydrostatics
        self.design_speed = design_speed
        self.signals = _ResistanceSignals()
        # O controlador guarda a referência até o resultado chegar.
        self.setAutoDelete(False)

    def run(self) -> None:
        if self.token != self.latest():
            self.signals.finished.emit(self.token, None)
            return
        length = self.hydrostatics.waterline_length
        speeds = FROUDE_RANGE * np.sqrt(hd.GRAVITY * length)
        curve = hd.resistance_curve(self.offsets, self.hydrostatics, speeds)
        design = hd.resistance_curve(self.offsets, self.hydrostatics, [self.design_speed])[0]
        notes = hd.validity_notes(self.hydrostatics, max(curve[-1].froude, design.froude))
        self.signals.finished.emit(self.token, (curve, design, notes))


class PerformanceController(QObject):
    """Mantém o painel de desempenho em dia com o casco paramétrico."""

    def __init__(self, panel) -> None:
        super().__init__(panel)
        self.panel = panel
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._token = 0
        self._jobs: dict[int, _ResistanceJob] = {}
        self._generator: HullGenerator | None = None
        self._offsets = None
        self._hydrostatics = None
        self._design_speed = panel.design_speed.value() * hd.KNOT
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(RESISTANCE_DELAY_MS)
        self._timer.timeout.connect(self._start_resistance)
        panel.design_speed_changed.connect(self._on_design_speed_changed)

    def update_hull(self, generator: HullGenerator) -> None:
        """Recalcula para um novo casco: hidrostática já, resistência em segundo plano."""
        try:
            half_x, half_y, half_z = generator.half_sections()
            offsets = hd.underwater_offsets(half_x, half_y, half_z)
            mesh = generator.generate_mesh()
            hydrostatics = hd.compute_hydrostatics(
                mesh.vertices, mesh.triangulated(), hd.midship_area(offsets)
            )
        except ValueError as error:
            self.clear(str(error))
            return
        self._generator = generator
        self._offsets = offsets
        self._hydrostatics = hydrostatics
        self._token += 1
        self.panel.set_hydrostatics(hydrostatics)
        self._timer.start()

    def clear(self, message: str) -> None:
        self._token += 1
        self._timer.stop()
        self._generator = None
        self.panel.set_unavailable(message)

    def wait_for_idle(self, timeout_ms: int = 30000) -> bool:
        """Espera o cálculo pendente terminar (útil em testes e ao fechar)."""
        if self._timer.isActive():
            self._timer.stop()
            self._start_resistance()
        return self._pool.waitForDone(timeout_ms)

    def _on_design_speed_changed(self, speed: float) -> None:
        self._design_speed = speed
        if self._generator is not None:
            self._token += 1
            self._timer.start()

    def _start_resistance(self) -> None:
        if self._generator is None:
            return
        job = _ResistanceJob(
            self._token,
            lambda: self._token,
            self._offsets,
            self._hydrostatics,
            self._design_speed,
        )
        job.signals.finished.connect(self._on_finished)
        self._jobs[self._token] = job
        self._pool.start(job)

    def _on_finished(self, token: int, result) -> None:
        self._jobs.pop(token, None)
        # Resultados de um casco antigo (o usuário continuou ajustando) são descartados.
        if result is not None and token == self._token:
            self.panel.set_resistance(*result)
