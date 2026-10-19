"""Widget de visualização 3D baseado em PyVista e Qt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Signal

from app.models.mesh import HullMesh


#: Faixas de zebra por unidade da coordenada refletida, suas cores e a resolução do mapa.
ZEBRA_DENSITY = 7.0
ZEBRA_COLORS = ("#12161b", "#f2f5f8")
ZEBRA_STEPS_PER_BAND = 12


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
    OVERLAY_PREFIX = "overlay-"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_mesh: pv.DataSet | None = None
        self._show_edges = False
        self._is_hull = False
        self._zebra = False
        self._overlays: set[str] = set()
        self._control_point_widgets: list = []
        self._axis_titles: tuple[str, str, str] | None = None
        self.set_background("#20252b")
        # A cena começa vazia: o primeiro casco vem da janela principal, com o
        # perfil escolhido, para não existirem dois valores iniciais diferentes.
        self.add_axes()

    def set_axis_titles(self, unit: str | None, *, hull_axes: bool) -> None:
        """Rotula a grade cotada com a unidade do modelo exibido.

        Os nomes navais (comprimento, boca, altura) só valem para o casco
        gerado aqui, cuja orientação é conhecida; para malhas importadas a
        grade usa os eixos X, Y e Z. Sem unidade conhecida, o título fica
        sem ela em vez de afirmar metros.
        """
        names = ("Comprimento", "Boca", "Altura") if hull_axes else ("X", "Y", "Z")
        suffix = f" ({unit})" if unit else ""
        titles = tuple(name + suffix for name in names)
        if titles == self._axis_titles:
            return
        self._axis_titles = titles
        self._show_measurement_grid(*titles)

    def _show_measurement_grid(self, xtitle: str, ytitle: str, ztitle: str) -> None:
        """Desenha a grade cotada com rótulos legíveis sobre o fundo escuro.

        A grade acompanha sozinha os limites da cena a cada troca de malha.
        """
        self.show_grid(
            xtitle=xtitle,
            ytitle=ytitle,
            ztitle=ztitle,
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
        # A malha dos patches de Coons já vem com os vértices fundidos.
        self.set_mesh(
            pv.PolyData(generated_mesh.vertices, generated_mesh.pyvista_faces), hull=True
        )

    @staticmethod
    def displayable(mesh: pv.DataSet | pv.MultiBlock) -> pv.DataSet:
        """Normaliza uma malha para exibição, sem tocar na cena.

        Raises:
            ValueError: se a malha não tiver pontos para mostrar.
        """
        if isinstance(mesh, pv.MultiBlock):
            mesh = mesh.combine()
        if int(getattr(mesh, "n_points", 0)) == 0:
            raise ValueError("O arquivo não contém pontos que possam ser exibidos.")
        return mesh

    @classmethod
    def read_mesh_file(cls, file_path: str | Path) -> pv.DataSet:
        """Lê uma malha compatível com VTK/PyVista sem alterar a cena.

        Separar a leitura da exibição permite validar o arquivo antes de
        descartar o modelo atual.
        """
        return cls.displayable(pv.read(str(file_path)))

    def set_mesh(
        self, mesh: pv.DataSet | pv.MultiBlock, hull: bool | None = None
    ) -> None:
        """Exibe uma malha lida de arquivo ou criada pelo gerador.

        ``hull`` indica se é o casco paramétrico (malha densa, cujas arestas
        ficam ocultas por padrão); ``None`` mantém a classificação anterior,
        como numa transformação do objeto.
        """
        mesh = self.displayable(mesh)
        if hull is not None:
            self._is_hull = hull
        self._current_mesh = mesh.copy(deep=True)
        self._draw_current_mesh()

    def _draw_current_mesh(self) -> None:
        """Desenha ``_current_mesh`` com as opções de exibição atuais."""
        self.remove_actor(self.ACTOR_NAME, reset_camera=False)
        mesh = self._current_mesh
        if mesh is None:
            return
        if self._zebra and isinstance(mesh, pv.PolyData):
            zebra = self._zebra_mesh(mesh)
            bands = self._zebra_colors(zebra)
            self.add_mesh(
                zebra,
                scalars="Zebra",
                cmap=bands[0],
                clim=bands[1],
                n_colors=len(bands[0]),
                show_scalar_bar=False,
                name=self.ACTOR_NAME,
                smooth_shading=False,
                show_edges=False,
            )
            return
        options = {"split_sharp_edges": True} if isinstance(mesh, pv.PolyData) else {}
        self.add_mesh(
            mesh,
            color="#4ea5d9",
            show_edges=self._show_edges if self._is_hull else True,
            edge_color="#dcebf5",
            line_width=1,
            name=self.ACTOR_NAME,
            smooth_shading=True,
            **options,
        )

    def set_show_edges(self, enabled: bool) -> None:
        """Mostra ou esconde as arestas da malha."""
        self._show_edges = enabled
        self._draw_current_mesh()
        self.render()

    @staticmethod
    def _zebra_mesh(mesh: pv.PolyData) -> pv.PolyData:
        """Malha com a faixa de zebra: reflexo de uma direção fixa nas normais.

        Faixas que atravessam as regiões do casco sem quebras indicam
        continuidade G1 e superfície sem ondulações (Figura 3.14).
        """
        shaded = mesh.triangulate().compute_normals(
            point_normals=True,
            cell_normals=False,
            split_vertices=True,
            feature_angle=35.0,
            auto_orient_normals=False,
        )
        normals = np.asarray(shaded.point_data["Normals"], dtype=float)
        view = np.array([0.35, -1.0, 0.45])
        view /= np.linalg.norm(view)
        reflected = view - 2.0 * (normals @ view)[:, None] * normals
        coordinate = reflected @ np.array([0.8, 0.1, 0.6])
        # Valor contínuo: as faixas saem do mapa de cores (por pixel), sem blocos.
        shaded.point_data["Zebra"] = coordinate * ZEBRA_DENSITY
        return shaded

    @staticmethod
    def _zebra_colors(mesh: pv.PolyData) -> tuple[list[str], tuple[float, float]]:
        """Mapa de cores com faixas alternadas, uma por unidade do valor ``Zebra``."""
        values = np.asarray(mesh.point_data["Zebra"], dtype=float)
        first = int(np.floor(values.min()))
        last = int(np.floor(values.max())) + 1
        colors: list[str] = []
        for band in range(first, last):
            colors += [ZEBRA_COLORS[band % 2]] * ZEBRA_STEPS_PER_BAND
        return colors, (float(first), float(last))

    def set_zebra(self, enabled: bool) -> None:
        """Liga ou desliga a inspeção por listras de zebra."""
        self._zebra = enabled
        self._draw_current_mesh()
        self.render()

    def set_overlay(
        self,
        name: str,
        polylines: list[np.ndarray] | None,
        color: str = "#ffd166",
        width: float = 2.0,
    ) -> None:
        """Mostra (ou remove, com ``None``) um conjunto de polilinhas sobre o casco."""
        actor_name = self.OVERLAY_PREFIX + name
        if actor_name in self._overlays:
            self.remove_actor(actor_name, reset_camera=False)
            self._overlays.discard(actor_name)
        if polylines:
            points, cells, base = [], [], 0
            for array in polylines:
                array = np.asarray(array, dtype=float)
                if array.ndim == 3:  # (n, 2, 3): segmentos soltos
                    count = len(array)
                    points.append(array.reshape(-1, 3))
                    index = base + np.arange(2 * count).reshape(count, 2)
                    cells.append(np.column_stack((np.full(count, 2), index)).ravel())
                    base += 2 * count
                elif len(array) >= 2:  # (m, 3): polilinha
                    points.append(array)
                    cells.append(
                        np.concatenate(([len(array)], base + np.arange(len(array))))
                    )
                    base += len(array)
            if points:
                lines = pv.PolyData(np.vstack(points), lines=np.concatenate(cells))
                self.add_mesh(
                    lines,
                    color=color,
                    line_width=width,
                    name=actor_name,
                    reset_camera=False,
                    pickable=False,
                )
                self._overlays.add(actor_name)
        self.render()

    def overlay_names(self) -> set[str]:
        return {name[len(self.OVERLAY_PREFIX):] for name in self._overlays}

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
