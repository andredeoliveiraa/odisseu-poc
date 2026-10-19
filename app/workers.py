"""Tarefas demoradas executadas fora da thread da interface."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.models.sampling import PARTICIPANT_CONSTRAINTS, AttributeSampler


class SamplingWorker(QThread):
    """Executa o S-TLBO sem congelar a janela, com progresso e cancelamento."""

    progress = Signal(int, float)
    sampled = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        attributes: list[str],
        count: int,
        preference: str,
        population: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._attributes = attributes
        self._count = count
        self._preference = preference
        self._population = population
        self._cancelled = False

    def cancel(self) -> None:
        """Interrompe na próxima iteração e entrega o resultado parcial."""
        self._cancelled = True

    def run(self) -> None:
        sampler = AttributeSampler(population_size=self._population)
        extra = PARTICIPANT_CONSTRAINTS.get(self._preference, ())

        def on_progress(iteration: int, cost: float) -> bool:
            self.progress.emit(iteration, cost)
            return not self._cancelled

        try:
            samples = sampler.sample(self._attributes, self._count, extra, on_progress)
        except ValueError as error:
            self.failed.emit(str(error))
            return
        self.sampled.emit(samples)
