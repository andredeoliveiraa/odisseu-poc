"""Comandos de edição reversível da malha exibida."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from PySide6.QtGui import QUndoCommand


class TransformMeshCommand(QUndoCommand):
    """Aplica uma transformação preservando estados exatos para undo/redo."""

    def __init__(
        self,
        viewer,
        matrix: np.ndarray,
        on_changed: Callable[[str], None],
    ) -> None:
        super().__init__("Transformar objeto")
        self._viewer = viewer
        self._on_changed = on_changed
        self._before = viewer.mesh_copy()
        self._after = self._before.copy(deep=True)
        self._after.transform(matrix, inplace=True)

    def redo(self) -> None:
        self._viewer.set_mesh(self._after)
        self._on_changed("Transformação aplicada")

    def undo(self) -> None:
        self._viewer.set_mesh(self._before)
        self._on_changed("Transformação desfeita")
