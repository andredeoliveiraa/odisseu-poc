"""Exportação do casco paramétrico como curvas NURBS em .3dm (Rhino).

Cada Bézier cúbico é um caso especial de NURBS: grau 3, 4 pontos de controle e
vetor de nós ``[0, 0, 0, 1, 1, 1]``. A conversão é exata e sem perda.

O arquivo exportado contém as curvas características organizadas em camadas:
- Convés (deck): 3 curvas longitudinais (entrada, meio, popa)
- Quilha (keel): 3 curvas longitudinais
- Quina (chine): 3 curvas longitudinais + espelho para bombordo
- Estações (stations): 3 estações × 2 linhas (superior e inferior), ambos os bordos
- Proa (bow): linha de roda de proa

A convenção de coordenadas é mantida: x = comprimento, y = boca, z = vertical.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import rhino3dm
except ImportError as _err:  # pragma: no cover
    rhino3dm = None
    _IMPORT_ERROR = _err
else:
    _IMPORT_ERROR = None


class RhinoExportError(ValueError):
    """Erro ao exportar para .3dm."""


def require_rhino3dm() -> None:
    if rhino3dm is None:
        raise RhinoExportError(
            'A exportação .3dm depende do pacote "rhino3dm". '
            'Instale com "pip install rhino3dm" e tente novamente.'
        ) from _IMPORT_ERROR


def _bezier_to_nurbs(control: np.ndarray) -> "rhino3dm.NurbsCurve":
    """Converte um Bézier cúbico ``(4, 3)`` em NurbsCurve exata."""
    control = np.asarray(control, float)
    if control.shape[1] == 2:
        control = np.column_stack([control, np.zeros(4)])
    curve = rhino3dm.NurbsCurve(3, 4)
    for i, (x, y, z) in enumerate(control):
        curve.Points[i] = rhino3dm.Point4d(x, y, z, 1.0)
    # Nós de um Bézier cúbico: [0, 0, 0, 1, 1, 1] (grau+pontos-1 = 6 valores)
    for i in range(6):
        curve.Knots[i] = 0.0 if i < 3 else 1.0
    return curve


def _mirror_y(control: np.ndarray) -> np.ndarray:
    """Espelha uma curva 3D em torno do plano y = 0 (bombordo)."""
    mirrored = control.copy()
    mirrored[:, 1] = -mirrored[:, 1]
    return mirrored


def _add_layer(file3dm: "rhino3dm.File3dm", name: str, r: int, g: int, b: int) -> int:
    layer = rhino3dm.Layer()
    layer.Name = name
    layer.Color = (r, g, b, 255)
    return file3dm.Layers.Add(layer)


def _add_curve(
    file3dm: "rhino3dm.File3dm",
    control: np.ndarray,
    layer_index: int,
) -> None:
    curve = _bezier_to_nurbs(control)
    attrs = rhino3dm.ObjectAttributes()
    attrs.LayerIndex = layer_index
    file3dm.Objects.AddCurve(curve, attrs)


def export_hull_as_3dm(model, path: Path | str, version: int = 7) -> None:
    """Exporta as curvas características do casco como NURBS em ``path``.

    Args:
        model: instância de :class:`~app.models.hull_model.HullModel`.
        path: caminho do arquivo de saída (extensão ``.3dm``).
        version: versão do formato Rhino (padrão: 7).
    """
    require_rhino3dm()
    file3dm = rhino3dm.File3dm()

    deck_layer = _add_layer(file3dm, "Convés",   200,  80,  40)
    keel_layer = _add_layer(file3dm, "Quilha",     40,  80, 200)
    chine_layer = _add_layer(file3dm, "Quina",     40, 160,  80)
    station_layer = _add_layer(file3dm, "Estações", 160, 80, 200)
    bow_layer = _add_layer(file3dm, "Proa",        200, 160,  40)

    # Curvas longitudinais (3D: x, y, z)
    for curve3d in model.deck:
        _add_curve(file3dm, curve3d, deck_layer)

    for curve3d in model.keel:
        _add_curve(file3dm, curve3d, keel_layer)

    for curve3d in model.chine:
        _add_curve(file3dm, curve3d, chine_layer)
        _add_curve(file3dm, _mirror_y(curve3d), chine_layer)

    # Estações: linhas superior e inferior (2D → 3D adicionando x da estação)
    for station in model.stations:
        x = station.x
        for curve2d in (station.upper, station.lower):
            ctrl3d = np.column_stack([np.full(4, x), curve2d])
            _add_curve(file3dm, ctrl3d, station_layer)
            _add_curve(file3dm, _mirror_y(ctrl3d), station_layer)

    # Linha de roda de proa (reta de bow_top até bow_low)
    top = np.array([model.bow_top[0], 0.0, model.bow_top[1]])
    low = np.array([model.bow_low[0], 0.0, model.bow_low[1]])
    chord = low - top
    bow_ctrl = np.array([top, top + chord / 3.0, low - chord / 3.0, low])
    _add_curve(file3dm, bow_ctrl, bow_layer)

    file3dm.Write(str(path), version)
