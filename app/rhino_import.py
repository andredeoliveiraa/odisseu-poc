"""Leitura de arquivos .3dm (Rhino) e conversão para malha compatível com PyVista.

O ``rhino3dm`` é a biblioteca de dados do OpenNURBS, mantida pela McNeel: ela
lê a estrutura do arquivo, mas — ao contrário do Rhino completo — não sabe
tesselar superfícies NURBS por conta própria. Cada face de um ``Brep`` só
pode ser exibida aqui quando o Rhino já gravou uma malha de exibição junto
com ela ao salvar o arquivo, o que é o caso comum para qualquer objeto que já
tenha sido visualizado ou renderizado no Rhino.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyvista as pv

try:
    import rhino3dm
except ImportError as error:  # pragma: no cover - depende do ambiente
    rhino3dm = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


class RhinoImportError(ValueError):
    """Erro ao importar um arquivo .3dm."""


#: Extensões que identificam uma superfície como imagem de referência colada
#: no Rhino (comando "Picture"/colar imagem), e não como geometria do casco.
#: Esse é o próprio padrão de nomeação do Rhino para essas superfícies,
#: então a checagem vale para qualquer arquivo, não só para este.
_REFERENCE_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


@dataclass(frozen=True)
class RhinoImportReport:
    """Resumo do que foi e do que não foi possível trazer do arquivo.

    Nem todo objeto de um .3dm vira geometria visível: curvas de construção
    não têm superfície, imagens de referência coladas no Rhino são planas e
    não fazem parte do casco, e uma superfície sem malha de exibição cacheada
    não pode ser tesselada por esta biblioteca. Nenhum desses casos é um
    erro — o resumo existe para que o chamador possa avisar o usuário do que
    ficou de fora, sem impedir o que pôde ser mostrado.
    """

    objects_total: int
    surfaces_shown: int
    surfaces_without_cached_mesh: int
    reference_images_skipped: int
    non_surface_objects_skipped: int

    @property
    def has_omissions(self) -> bool:
        return self.surfaces_without_cached_mesh > 0

    def describe_omissions(self) -> str:
        if not self.has_omissions:
            return ""
        plural = "s" if self.surfaces_without_cached_mesh != 1 else ""
        return (
            f"{self.surfaces_without_cached_mesh} superfície{plural} do arquivo "
            "não tinha malha de exibição salva pelo Rhino e não pôde ser "
            "convertida. Abra e salve o arquivo no Rhino com as superfícies "
            "visíveis para gerar essa malha, depois importe de novo."
        )


def _is_available() -> bool:
    return rhino3dm is not None


def require_rhino3dm() -> None:
    """Levanta um erro claro quando a dependência opcional não está instalada."""
    if not _is_available():
        raise RhinoImportError(
            "A leitura de arquivos .3dm depende do pacote \"rhino3dm\", que não "
            "está instalado neste ambiente. Instale com "
            "\"pip install rhino3dm\" e tente novamente."
        ) from _IMPORT_ERROR


def _mesh_to_arrays(
    mesh: "rhino3dm.Mesh", vertex_offset: int
) -> tuple[np.ndarray, list[tuple[int, ...]]]:
    """Converte uma malha do rhino3dm em vértices e faces (índices já deslocados)."""
    points = mesh.Vertices.ToPoint3dArray()
    vertices = np.array([(p.X, p.Y, p.Z) for p in points], dtype=np.float64)

    faces: list[tuple[int, ...]] = []
    for index in range(mesh.Faces.Count):
        a, b, c, d = mesh.Faces[index]
        if c == d:
            faces.append((3, vertex_offset + a, vertex_offset + b, vertex_offset + c))
        else:
            faces.append(
                (4, vertex_offset + a, vertex_offset + b, vertex_offset + c, vertex_offset + d)
            )
    return vertices, faces


def _collect_face_meshes(geometry) -> list["rhino3dm.Mesh"]:
    """Extrai as malhas de exibição já cacheadas de um objeto geométrico."""
    type_name = type(geometry).__name__
    if type_name == "Mesh":
        return [geometry]
    if type_name == "Brep":
        meshes = []
        for face in geometry.Faces:
            mesh = face.GetMesh(rhino3dm.MeshType.Any)
            if mesh is not None:
                meshes.append(mesh)
        return meshes
    if type_name == "Extrusion":
        mesh = geometry.GetMesh(rhino3dm.MeshType.Any)
        return [mesh] if mesh is not None else []
    return []


def _is_reference_image(obj) -> bool:
    """Reconhece uma superfície criada pelo comando "Picture" do Rhino.

    Ao colar ou inserir uma imagem no Rhino, ele cria uma superfície plana
    com o nome do próprio arquivo de imagem, usada só como referência visual
    para desenhar por cima. Ela nunca é geometria do casco.
    """
    name = (obj.Attributes.Name or "").strip().lower()
    return name.endswith(_REFERENCE_IMAGE_EXTENSIONS)


def _face_count_for(geometry) -> int:
    """Quantas superfícies um objeto representa, para contabilizar omissões."""
    type_name = type(geometry).__name__
    if type_name == "Brep":
        return sum(1 for _ in geometry.Faces)
    if type_name in ("Mesh", "Extrusion"):
        return 1
    return 0


def read_3dm_as_polydata(file_path: str | Path) -> tuple[pv.PolyData, RhinoImportReport]:
    """Lê um arquivo .3dm e devolve uma malha combinada, mais um resumo da leitura.

    Só objetos visíveis entram na malha resultante, e só superfícies (Brep,
    Extrusion ou Mesh) contribuem geometria — curvas de construção e outras
    entidades sem volume são contadas, mas não aparecem.
    """
    require_rhino3dm()

    model = rhino3dm.File3dm.Read(str(file_path))
    if model is None:
        raise RhinoImportError(
            "O arquivo não pôde ser lido como um .3dm válido. Ele pode estar "
            "corrompido ou não ser, de fato, um arquivo do Rhino."
        )

    all_vertices: list[np.ndarray] = []
    all_faces: list[tuple[int, ...]] = []
    vertex_count = 0
    objects_total = 0
    surface_faces_total = 0
    surface_faces_shown = 0
    non_surface_objects_skipped = 0
    reference_images_skipped = 0

    for obj in model.Objects:
        objects_total += 1
        if not obj.Attributes.Visible:
            continue
        if _is_reference_image(obj):
            reference_images_skipped += 1
            continue

        geometry = obj.Geometry
        expected = _face_count_for(geometry)
        if expected == 0:
            non_surface_objects_skipped += 1
            continue
        surface_faces_total += expected

        for mesh in _collect_face_meshes(geometry):
            vertices, faces = _mesh_to_arrays(mesh, vertex_count)
            if len(vertices) == 0:
                continue
            all_vertices.append(vertices)
            all_faces.extend(faces)
            vertex_count += len(vertices)
            surface_faces_shown += 1

    if not all_vertices:
        raise RhinoImportError(
            "Nenhuma superfície com malha de exibição foi encontrada neste "
            "arquivo. Abra-o no Rhino, confirme que as superfícies aparecem "
            "sombreadas na viewport, salve e importe de novo."
        )

    combined_vertices = np.vstack(all_vertices)
    flat_faces = np.concatenate([np.array(face, dtype=np.int64) for face in all_faces])
    polydata = pv.PolyData(combined_vertices, flat_faces)

    report = RhinoImportReport(
        objects_total=objects_total,
        surfaces_shown=surface_faces_shown,
        surfaces_without_cached_mesh=max(0, surface_faces_total - surface_faces_shown),
        reference_images_skipped=reference_images_skipped,
        non_surface_objects_skipped=non_surface_objects_skipped,
    )
    return polydata, report
