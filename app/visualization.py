"""Widget de visualização 3D baseado em PyVista e Qt."""

from __future__ import annotations

import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Signal

from app.hull_generator import HullGenerator, HullMesh


class HullViewer(QtInteractor):
    """Visualizador 3D reutilizável para geometrias do casco.

    O ``QtInteractor`` conecta o renderizador VTK ao ciclo de eventos Qt e
    fornece, por padrão, rotação, pan e zoom com mouse.
    """

    status_message = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.set_background("#20252b")
        self._add_sample_geometry()

    def _add_sample_geometry(self) -> None:
        """Adiciona um casco paramétrico inicial para validar a renderização."""
        self.set_hull(HullGenerator().generate_mesh())
        self.add_axes()
        self.show_grid(
            xtitle="Comprimento",
            ytitle="Boca",
            ztitle="Calado",
            color="#8b949e",
        )
        self.reset_camera()

    def set_hull(self, generated_mesh: HullMesh) -> None:
        """Substitui a malha exibida pelo resultado do gerador."""
        self.remove_actor("sample-hull", reset_camera=False)
        sample_hull = pv.PolyData(generated_mesh.vertices, generated_mesh.pyvista_faces)
        self.add_mesh(
            sample_hull,
            color="#4ea5d9",
            show_edges=True,
            edge_color="#dcebf5",
            line_width=1,
            name="sample-hull",
        )

    def clear_model(self) -> None:
        """Remove a geometria carregada, preservando a cena de visualização."""
        self.remove_actor("sample-hull")
