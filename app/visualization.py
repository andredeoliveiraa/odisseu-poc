"""Widget de visualização 3D baseado em PyVista e Qt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Signal

from app.hull_generator import HullGenerator, HullMesh


@dataclass(frozen=True)
class MeshSummary:
    """Informações compactas apresentadas na interface."""

    points: int
    cells: int
    dimensions: tuple[float, float, float]


class HullViewer(QtInteractor):
    """Visualizador 3D reutilizável para geometrias do casco.

    O ``QtInteractor`` conecta o renderizador VTK ao ciclo de eventos Qt e
    fornece, por padrão, rotação, pan e zoom com mouse.
    """

    status_message = Signal(str)

    #: Nome do ator usado para o modelo exibido no momento.
    ACTOR_NAME = "current-hull"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_mesh: pv.DataSet | None = None
        self._control_point_widgets: list = []
        self.set_background("#20252b")
        self._build_initial_scene()

    def _build_initial_scene(self) -> None:
        """Monta a cena inicial com o casco padrão e os eixos cotados."""
        self.set_hull(HullGenerator().generate_mesh())
        self.add_axes()
        self._show_measurement_grid()
        self.reset_view()

    def _show_measurement_grid(self) -> None:
        """Desenha a grade cotada com rótulos legíveis sobre o fundo escuro."""
        self.show_grid(
            xtitle="Comprimento (m)",
            ytitle="Boca (m)",
            ztitle="Calado (m)",
            color="#c7d2dd",
            font_size=11,
            font_family="arial",
            n_xlabels=4,
            n_ylabels=4,
            n_zlabels=4,
            fmt="%.1f",
            padding=0.08,
            use_3d_text=False,
        )

    def set_hull(self, generated_mesh: HullMesh) -> None:
        """Substitui a malha exibida pelo resultado do gerador."""
        sample_hull = pv.PolyData(generated_mesh.vertices, generated_mesh.pyvista_faces)
        self.set_mesh(sample_hull)

    def set_mesh(self, mesh: pv.DataSet | pv.MultiBlock) -> None:
        """Exibe uma malha lida de arquivo ou criada pelo gerador."""
        if isinstance(mesh, pv.MultiBlock):
            mesh = mesh.combine()
        if int(getattr(mesh, "n_points", 0)) == 0:
            raise ValueError("O arquivo não contém pontos que possam ser exibidos.")

        self.remove_actor(self.ACTOR_NAME, reset_camera=False)
        self._current_mesh = mesh.copy(deep=True)
        self.add_mesh(
            self._current_mesh,
            color="#4ea5d9",
            show_edges=True,
            edge_color="#dcebf5",
            line_width=1,
            name=self.ACTOR_NAME,
            smooth_shading=False,
        )

    def load_mesh(self, file_path: str | Path) -> None:
        """Lê uma malha compatível com VTK/PyVista e a exibe."""
        mesh = pv.read(str(file_path))
        self.set_mesh(mesh)

    def save_mesh(self, file_path: str | Path) -> None:
        """Exporta a geometria visível para um formato de malha suportado."""
        if self._current_mesh is None:
            raise ValueError("Não existe um modelo para exportar.")

        suffix = Path(file_path).suffix.lower()
        mesh = self._surface_mesh()
        if suffix in {".stl", ".ply"}:
            mesh = mesh.triangulate()
        mesh.save(str(file_path))

    def mesh_summary(self) -> MeshSummary | None:
        """Retorna contagens e dimensões do modelo exibido."""
        if self._current_mesh is None:
            return None

        bounds = np.asarray(self._current_mesh.bounds, dtype=float).reshape(3, 2)
        dimensions = tuple(float(value) for value in (bounds[:, 1] - bounds[:, 0]))
        return MeshSummary(
            points=int(self._current_mesh.n_points),
            cells=int(self._current_mesh.n_cells),
            dimensions=dimensions,
        )

    def mesh_copy(self) -> pv.DataSet:
        """Fornece uma cópia segura para comandos de edição e histórico."""
        if self._current_mesh is None:
            raise ValueError("Não existe um modelo para editar.")
        return self._current_mesh.copy(deep=True)

    def mesh_center(self) -> tuple[float, float, float]:
        """Retorna o centro dos limites usado como pivô de transformação."""
        if self._current_mesh is None:
            raise ValueError("Não existe um modelo para editar.")
        return tuple(float(value) for value in self._current_mesh.center)

    def reset_view(self) -> None:
        """Devolve a câmera à orientação isométrica inicial."""
        self.view_isometric()
        self.reset_camera()
        self.render()

    def fit_view(self) -> None:
        """Enquadra o modelo preservando a orientação escolhida pelo usuário."""
        self.reset_camera()
        self.render()

    def update_current_mesh_points(self, vertices: np.ndarray) -> None:
        """Atualiza só as posições dos pontos da malha atual, sem recriar o ator.

        Usado durante a edição de pontos de controle: a topologia (quantidade
        de pontos e faces) não muda a cada arraste, só a posição deles, então
        atualizar em lugar de remontar o ator mantém a edição fluida.
        """
        if self._current_mesh is None or len(vertices) != self._current_mesh.n_points:
            raise ValueError(
                "A nova malha precisa ter a mesma quantidade de pontos da atual."
            )
        self._current_mesh.points = vertices
        self.render()

    def show_control_point_handles(self, points: np.ndarray, on_move) -> None:
        """Mostra pontos de controle como alças 3D arrastáveis.

        ``points`` é uma lista ou array de coordenadas ``(N, 3)``; a ordem é
        preservada, então o índice recebido em ``on_move(index, nova_posicao)``
        corresponde diretamente à posição em ``points``. O raio das esferas é
        proporcional ao tamanho da própria superfície, para ficar visível sem
        dominar a cena em cascos grandes ou pequenos.
        """
        self.clear_control_point_handles()
        points = np.asarray(points, dtype=np.float64)
        if len(points) == 0:
            return

        spread = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
        radius = max(spread * 0.012, 1e-3)

        def _dispatch(point, index):
            on_move(index, tuple(point))

        widgets = self.add_sphere_widget(
            _dispatch,
            center=[tuple(p) for p in points],
            radius=radius,
            color="#ffb454",
            selected_color="#ff5f56",
            indices=list(range(len(points))),
            interaction_event="always",
        )
        # add_sphere_widget devolve um único widget quando só um centro é
        # passado; normalizamos para lista para o resto do código não
        # precisar distinguir os dois casos.
        self._control_point_widgets = list(widgets) if len(points) > 1 else [widgets]

    def clear_control_point_handles(self) -> None:
        """Remove as alças de ponto de controle, se houver alguma na cena."""
        if self._control_point_widgets:
            self.clear_sphere_widgets()
            self._control_point_widgets = []

    def _surface_mesh(self) -> pv.PolyData:
        """Converte o objeto atual em superfície adequada para exportação."""
        if self._current_mesh is None:
            raise ValueError("Não existe um modelo para exportar.")
        if isinstance(self._current_mesh, pv.PolyData):
            return self._current_mesh.copy(deep=True)
        return self._current_mesh.extract_surface()
