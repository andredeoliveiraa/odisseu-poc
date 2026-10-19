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

from app.models.mesh import HullMesh
from app.rhino_import import is_reference_image, unit_label

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
    #: Abreviação da unidade do arquivo, ou ``None`` se ele não a define.
    unit: str | None = None

    @property
    def control_point_count(self) -> int:
        return self.control_grid[0] * self.control_grid[1]

    def describe(self) -> str:
        u, v = self.control_grid
        du, dv = self.degree
        x, y, z = self.dimensions
        unit = f" {self.unit}" if self.unit else ""
        return (
            f"Face {self.face_index} · camada “{self.layer_name}” · "
            f"grade {u}×{v} ({self.control_point_count} pontos) · "
            f"grau {du}×{dv} · {x:.2f}×{y:.2f}×{z:.2f}{unit}"
        )


def _read_model(file_path: str | Path) -> "rhino3dm.File3dm":
    _require_rhino3dm()
    model = rhino3dm.File3dm.Read(str(file_path))
    if model is None:
        raise NurbsSurfaceError("O arquivo não pôde ser lido como um .3dm válido.")
    return model


def _surface_items(model):
    """Percorre as superfícies candidatas, na ordem que define o índice de face.

    Cada face de cada ``Brep`` visível é uma candidata própria, porque um
    casco normalmente é modelado como várias superfícies (costado, fundo,
    espelho de popa). Uma superfície solta, como a que :meth:`save_to_3dm`
    grava, também entra. Imagens de referência coladas no Rhino ficam de
    fora, como na importação de malha.
    """
    for obj in model.Objects:
        if not obj.Attributes.Visible or is_reference_image(obj):
            continue
        geometry = obj.Geometry
        type_name = type(geometry).__name__
        if type_name == "Brep":
            for face in geometry.Faces:
                yield obj, face
        elif type_name in ("NurbsSurface", "Surface", "Extrusion"):
            yield obj, geometry


def _to_nurbs(item):
    return item.ToNurbsSurface() if hasattr(item, "ToNurbsSurface") else item


def list_editable_surfaces(file_path: str | Path) -> list[NurbsFaceInfo]:
    """Lista as faces de superfície de um .3dm que podem virar NURBS editável.

    Objetos que só existem como curva, ponto ou malha pura não entram nesta
    lista — eles não têm uma superfície NURBS para editar por ponto de
    controle.
    """
    model = _read_model(file_path)
    layer_names = {layer.Index: layer.Name for layer in model.Layers}
    unit = unit_label(model.Settings.ModelUnitSystem)
    infos: list[NurbsFaceInfo] = []
    for face_index, (obj, item) in enumerate(_surface_items(model)):
        nurbs = _to_nurbs(item)
        if nurbs is None:
            continue
        bbox = item.GetBoundingBox()
        infos.append(
            NurbsFaceInfo(
                face_index=face_index,
                layer_name=layer_names.get(obj.Attributes.LayerIndex, ""),
                control_grid=(nurbs.Points.CountU, nurbs.Points.CountV),
                degree=(nurbs.Degree(0), nurbs.Degree(1)),
                dimensions=(
                    bbox.Max.X - bbox.Min.X,
                    bbox.Max.Y - bbox.Min.Y,
                    bbox.Max.Z - bbox.Min.Z,
                ),
                unit=unit,
            )
        )
    return infos


def _nurbs_surface_by_face_index(model, face_index: int):
    """Localiza a face pedida pelo mesmo percurso de :func:`list_editable_surfaces`."""
    for current, (_obj, item) in enumerate(_surface_items(model)):
        if current == face_index:
            nurbs = _to_nurbs(item)
            if nurbs is None:
                raise NurbsSurfaceError(
                    "Esta face não pôde ser convertida em superfície NURBS."
                )
            return nurbs
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

    def __init__(
        self,
        surface: "rhino3dm.NurbsSurface",
        unit_system: "rhino3dm.UnitSystem | None" = None,
    ) -> None:
        _require_rhino3dm()
        self._surface = surface
        self._unit_system = unit_system

    @classmethod
    def from_3dm_face(cls, file_path: str | Path, face_index: int) -> "EditableNurbsSurface":
        """Carrega uma face específica de um .3dm pelo índice dado por
        :func:`list_editable_surfaces`."""
        model = _read_model(file_path)
        return cls(
            _nurbs_surface_by_face_index(model, face_index),
            model.Settings.ModelUnitSystem,
        )

    @property
    def unit(self) -> str | None:
        """Abreviação da unidade do arquivo de origem, ou ``None``."""
        return unit_label(self._unit_system)

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
        arquivo original de onde a superfície veio. A unidade do arquivo de
        origem é mantida, para a superfície reabrir no Rhino na mesma escala.
        """
        model = rhino3dm.File3dm()
        if self._unit_system is not None:
            model.Settings.ModelUnitSystem = self._unit_system
        model.Objects.AddSurface(self._surface)
        model.Write(str(file_path), 7)
