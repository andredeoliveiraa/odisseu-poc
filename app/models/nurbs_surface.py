"""Superfícies NURBS editáveis por ponto de controle, lidas de um .3dm.

Diferente da importação de malha em :mod:`app.rhino_import` — que só exibe o
resultado já pronto —, este módulo mantém a superfície na sua representação
matemática original (pontos de controle, grau, nós). Isso permite mover um
ponto de controle e recalcular a forma da superfície ao vivo, e depois salvar
o resultado de volta como um .3dm que o Rhino sabe reabrir.

O ``rhino3dm`` só fornece os dados: não há solver de edição, nem aparo de
superfície, nem histórico. Este módulo cobre o caso simples e mais útil para
remodelar um casco — uma superfície não aparada por vez.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.hull_generator import HullMesh

try:
    import rhino3dm
except ImportError as error:  # pragma: no cover - depende do ambiente
    rhino3dm = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


class NurbsSurfaceError(ValueError):
    """Erro ao localizar, ler ou converter uma superfície NURBS."""


def _require_rhino3dm() -> None:
    if rhino3dm is None:
        raise NurbsSurfaceError(
            "A edição de superfícies NURBS depende do pacote \"rhino3dm\", que "
            "não está instalado neste ambiente. Instale com "
            "\"pip install rhino3dm\" e tente novamente."
        ) from _IMPORT_ERROR


@dataclass(frozen=True)
class NurbsFaceInfo:
    """Descrição de uma superfície candidata, para o usuário escolher qual editar."""

    face_index: int
    layer_name: str
    control_grid: tuple[int, int]
    degree: tuple[int, int]
    dimensions: tuple[float, float, float]

    @property
    def control_point_count(self) -> int:
        return self.control_grid[0] * self.control_grid[1]

    def describe(self) -> str:
        u, v = self.control_grid
        du, dv = self.degree
        x, y, z = self.dimensions
        return (
            f"Face {self.face_index} · camada “{self.layer_name}” · "
            f"grade {u}×{v} ({self.control_point_count} pontos) · "
            f"grau {du}×{dv} · {x:.2f}×{y:.2f}×{z:.2f} m"
        )


def list_editable_surfaces(file_path: str | Path) -> list[NurbsFaceInfo]:
    """Lista as faces de superfície de um .3dm que podem virar NURBS editável.

    Objetos que só existem como curva, ponto ou malha pura não entram nesta
    lista — eles não têm uma superfície NURBS para editar por ponto de
    controle. Cada face de cada ``Brep`` visível é uma candidata própria,
    porque um casco normalmente é modelado como várias superfícies (costado,
    fundo, espelho de popa) e não como uma peça única.
    """
    _require_rhino3dm()
    model = rhino3dm.File3dm.Read(str(file_path))
    if model is None:
        raise NurbsSurfaceError(
            "O arquivo não pôde ser lido como um .3dm válido."
        )

    layer_names = {i: layer.Name for i, layer in enumerate(model.Layers)}
    infos: list[NurbsFaceInfo] = []
    face_index = 0
    for obj in model.Objects:
        if not obj.Attributes.Visible:
            continue
        geometry = obj.Geometry
        layer_name = layer_names.get(obj.Attributes.LayerIndex, "")
        type_name = type(geometry).__name__

        if type_name == "Brep":
            candidates = [
                (face.ToNurbsSurface(), face.GetBoundingBox()) for face in geometry.Faces
            ]
        elif type_name in ("NurbsSurface", "Surface", "Extrusion"):
            # Um arquivo salvo por este próprio módulo guarda a superfície
            # solta, sem um Brep em volta — precisa do mesmo tratamento.
            nurbs = geometry.ToNurbsSurface() if hasattr(geometry, "ToNurbsSurface") else geometry
            candidates = [(nurbs, geometry.GetBoundingBox())]
        else:
            continue

        for nurbs, bbox in candidates:
            if nurbs is None:
                face_index += 1
                continue
            infos.append(
                NurbsFaceInfo(
                    face_index=face_index,
                    layer_name=layer_name,
                    control_grid=(nurbs.Points.CountU, nurbs.Points.CountV),
                    degree=(nurbs.Degree(0), nurbs.Degree(1)),
                    dimensions=(
                        bbox.Max.X - bbox.Min.X,
                        bbox.Max.Y - bbox.Min.Y,
                        bbox.Max.Z - bbox.Min.Z,
                    ),
                )
            )
            face_index += 1
    return infos


def _nurbs_surface_by_face_index(model, face_index: int):
    """Percorre o mesmo caminho de :func:`list_editable_surfaces` até a face pedida."""
    current = 0
    for obj in model.Objects:
        if not obj.Attributes.Visible:
            continue
        geometry = obj.Geometry
        type_name = type(geometry).__name__

        if type_name == "Brep":
            surfaces = list(geometry.Faces)
            to_nurbs = lambda item: item.ToNurbsSurface()
        elif type_name in ("NurbsSurface", "Surface", "Extrusion"):
            surfaces = [geometry]
            to_nurbs = lambda item: (
                item.ToNurbsSurface() if hasattr(item, "ToNurbsSurface") else item
            )
        else:
            continue

        for item in surfaces:
            if current == face_index:
                nurbs = to_nurbs(item)
                if nurbs is None:
                    raise NurbsSurfaceError(
                        "Esta face não pôde ser convertida em superfície NURBS."
                    )
                return nurbs
            current += 1
    raise NurbsSurfaceError(f"Não existe face de índice {face_index} neste arquivo.")


class EditableNurbsSurface:
    """Uma superfície NURBS com pontos de controle que podem ser movidos.

    A malha exibida na tela nunca é editada diretamente: ela é sempre
    recalculada a partir dos pontos de controle atuais, chamando
    :meth:`tessellate`. Isso garante que a forma exibida corresponde sempre
    a uma superfície matemática válida, nunca a uma malha remendada à mão.
    """

    #: Resolução padrão da malha de exibição, em pontos por direção.
    DEFAULT_RESOLUTION = 28

    def __init__(self, surface: "rhino3dm.NurbsSurface") -> None:
        _require_rhino3dm()
        self._surface = surface

    @classmethod
    def from_3dm_face(cls, file_path: str | Path, face_index: int) -> "EditableNurbsSurface":
        """Carrega uma face específica de um .3dm pelo índice dado por
        :func:`list_editable_surfaces`."""
        _require_rhino3dm()
        model = rhino3dm.File3dm.Read(str(file_path))
        if model is None:
            raise NurbsSurfaceError("O arquivo não pôde ser lido como um .3dm válido.")
        return cls(_nurbs_surface_by_face_index(model, face_index))

    @property
    def control_grid_shape(self) -> tuple[int, int]:
        points = self._surface.Points
        return points.CountU, points.CountV

    @property
    def degree(self) -> tuple[int, int]:
        return self._surface.Degree(0), self._surface.Degree(1)

    def control_points(self) -> np.ndarray:
        """Grade de pontos de controle, com forma ``(CountU, CountV, 3)``."""
        points = self._surface.Points
        count_u, count_v = points.CountU, points.CountV
        grid = np.empty((count_u, count_v, 3), dtype=np.float64)
        for i in range(count_u):
            for j in range(count_v):
                point = points.GetPoint(i, j)
                grid[i, j] = (point.X, point.Y, point.Z)
        return grid

    def move_control_point(
        self, i: int, j: int, new_position: tuple[float, float, float]
    ) -> None:
        """Move um ponto de controle para uma posição absoluta em coordenadas do mundo.

        Preserva o peso do ponto (relevante para NURBS racionais, como
        superfícies exatas de cone ou esfera); a maioria das superfícies de
        casco não é racional e tem peso 1, mas a conta é feita corretamente
        nos dois casos.
        """
        points = self._surface.Points
        count_u, count_v = points.CountU, points.CountV
        if not (0 <= i < count_u and 0 <= j < count_v):
            raise IndexError(
                f"Ponto de controle ({i}, {j}) fora da grade {count_u}×{count_v}."
            )
        current = points.GetControlPoint(i, j)
        weight = current.W
        x, y, z = new_position
        points[i, j] = rhino3dm.Point4d(x * weight, y * weight, z * weight, weight)

    def move_control_point_flat(self, index: int, new_position: tuple[float, float, float]) -> None:
        """Move um ponto de controle pelo índice linear usado na malha de alças.

        A ordem é a mesma de ``control_points().reshape(-1, 3)``: linha a
        linha em ``V`` dentro de cada ``U``.
        """
        _, count_v = self.control_grid_shape
        i, j = divmod(index, count_v)
        self.move_control_point(i, j, new_position)

    def tessellate(self, resolution: int | None = None) -> HullMesh:
        """Reavalia a superfície numa grade regular e devolve uma malha de quadriláteros."""
        resolution_u = resolution_v = resolution or self.DEFAULT_RESOLUTION
        domain_u, domain_v = self._surface.Domain(0), self._surface.Domain(1)
        us = np.linspace(domain_u.T0, domain_u.T1, resolution_u)
        vs = np.linspace(domain_v.T0, domain_v.T1, resolution_v)

        vertices = np.empty((resolution_u * resolution_v, 3), dtype=np.float64)
        for i, u in enumerate(us):
            for j, v in enumerate(vs):
                point = self._surface.PointAt(u, v)
                vertices[i * resolution_v + j] = (point.X, point.Y, point.Z)

        faces = []
        for i in range(resolution_u - 1):
            for j in range(resolution_v - 1):
                a = i * resolution_v + j
                b = a + 1
                c = (i + 1) * resolution_v + j + 1
                d = (i + 1) * resolution_v + j
                faces.append((a, b, c, d))

        return HullMesh(vertices=vertices, faces=np.array(faces, dtype=np.int64))

    def save_to_3dm(self, file_path: str | Path) -> None:
        """Salva esta superfície sozinha como um novo arquivo .3dm.

        Este é um arquivo novo, com só a superfície editada dentro — ele não
        recupera as outras camadas, curvas ou imagens de referência do
        arquivo original de onde a superfície veio.
        """
        model = rhino3dm.File3dm()
        model.Objects.AddSurface(self._surface)
        model.Write(str(file_path), 7)
