"""Propriedades hidrostáticas do casco (Tabela 3.6 da referência).

O casco é cortado na linha d'água ``z = T`` (``T`` medido a partir da linha de
base). O volume e seus momentos saem do teorema da divergência sobre a parte
submersa da malha; as propriedades do plano de flutuação saem do teorema de
Green sobre o contorno do corte. A área da seção mestra vem de cortes
transversais.

Convenção de KB e KM: medidos a partir da linha de base (quilha), como é padrão
em arquitetura naval, com ``KM = KB + BM``. A Tabela 3.6 da tese traz KB ≈ T/3,
valor que só faz sentido contado a partir da linha d'água (``T − KB``); com essa
conversão os valores deste módulo ficam na mesma ordem dos da tabela.

A malha precisa ser fechada abaixo da linha d'água (``HullModel.build_mesh``
tampa o espelho de popa) e orientada com as normais para fora.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np

from app.models import bezier as bz
from app.models.hull_model import HullModel
from app.models.mesh import HullMesh


@dataclass(frozen=True)
class HydrostaticResult:
    """Colunas da Tabela 3.6, para um calado ``T`` (metros, m², m³, m⁴)."""

    T: float
    LWL: float
    BWL: float
    V: float
    Aw: float
    LCB: float
    KB: float
    LCF: float
    IL: float
    IT: float
    Ax: float
    BM: float
    KM: float
    Cp: float
    Cm: float
    Cw: float
    Cb: float

    @classmethod
    def columns(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls))


#: Rótulo e unidade de cada coluna.
COLUMN_INFO: dict[str, tuple[str, str]] = {
    "T": ("Calado", "m"),
    "LWL": ("Comprimento na linha d'água", "m"),
    "BWL": ("Boca na linha d'água", "m"),
    "V": ("Volume deslocado", "m³"),
    "Aw": ("Área do plano de flutuação", "m²"),
    "LCB": ("Centro de carena longitudinal (do espelho)", "m"),
    "KB": ("Centro de carena vertical (da quilha)", "m"),
    "LCF": ("Centro de flutuação longitudinal (do espelho)", "m"),
    "IL": ("Momento de inércia longitudinal", "m⁴"),
    "IT": ("Momento de inércia transversal", "m⁴"),
    "Ax": ("Área da seção mestra", "m²"),
    "BM": ("Raio metacêntrico", "m"),
    "KM": ("Altura do metacentro (da quilha)", "m"),
    "Cp": ("Coeficiente prismático", ""),
    "Cm": ("Coeficiente da seção mestra", ""),
    "Cw": ("Coeficiente do plano de flutuação", ""),
    "Cb": ("Coeficiente de bloco", ""),
}


def _clip_below(
    triangles: np.ndarray, level: float
) -> tuple[np.ndarray, np.ndarray]:
    """Recorta triângulos ``(n, 3, 3)`` em ``z ≤ level``.

    Returns:
        ``(abaixo, corte)``: os triângulos resultantes (orientação mantida) e
        os segmentos ``(m, 2, 3)`` do corte na linha d'água, orientados pelo
        sentido de percurso das faces.
    """
    height = triangles[:, :, 2] - level
    inside = height <= 0.0
    count = inside.sum(axis=1)
    pieces = [triangles[count == 3]]
    cuts = []

    def crossing(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        za, zb = a[:, 2] - level, b[:, 2] - level
        t = za / (za - zb)
        return a + t[:, None] * (b - a)

    one = np.nonzero(count == 1)[0]
    if len(one):
        rotated = _rotate(triangles[one], inside[one].argmax(axis=1))
        a, b, c = rotated[:, 0], rotated[:, 1], rotated[:, 2]
        ab, ca = crossing(a, b), crossing(c, a)
        pieces.append(np.stack((a, ab, ca), axis=1))
        cuts.append(np.stack((ab, ca), axis=1))

    two = np.nonzero(count == 2)[0]
    if len(two):
        outside = (~inside[two]).argmax(axis=1)
        rotated = _rotate(triangles[two], (outside + 1) % 3)
        a, b, c = rotated[:, 0], rotated[:, 1], rotated[:, 2]
        bc, ca = crossing(b, c), crossing(c, a)
        pieces.append(np.stack((a, b, bc), axis=1))
        pieces.append(np.stack((a, bc, ca), axis=1))
        cuts.append(np.stack((bc, ca), axis=1))

    below = np.concatenate(pieces) if pieces else np.empty((0, 3, 3))
    segments = np.concatenate(cuts) if cuts else np.empty((0, 2, 3))
    return below, segments


def _rotate(triangles: np.ndarray, start: np.ndarray) -> np.ndarray:
    """Gira cada triângulo para que o vértice ``start`` venha primeiro."""
    order = (start[:, None] + np.arange(3)[None, :]) % 3
    return np.take_along_axis(triangles, order[:, :, None], axis=1)


def _section_area(triangles: np.ndarray, x: float) -> float:
    """Área da seção ``x = const`` da parte submersa (contorno + linha d'água).

    O contorno vai de uma borda da linha d'água à outra; o fecho pela própria
    linha d'água é horizontal e não contribui para ``∮ y dz``.
    """
    side = triangles[:, :, 0] - x
    positive = side > 0
    mixed = positive.any(axis=1) & ~positive.all(axis=1)
    selected, side = triangles[mixed], side[mixed]
    if not len(selected):
        return 0.0
    starts = np.full((len(selected), 3), np.nan)
    ends = np.full((len(selected), 3), np.nan)
    for first in range(3):
        second = (first + 1) % 3
        pos_to_neg = (side[:, first] > 0) & (side[:, second] <= 0)
        neg_to_pos = (side[:, first] <= 0) & (side[:, second] > 0)
        for mask, target in ((pos_to_neg, starts), (neg_to_pos, ends)):
            a, b = selected[mask, first], selected[mask, second]
            t = (a[:, 0] - x) / (a[:, 0] - b[:, 0])
            target[mask] = a + t[:, None] * (b - a)
    y1, z1 = starts[:, 1], starts[:, 2]
    y2, z2 = ends[:, 1], ends[:, 2]
    return abs(float(np.nansum(0.5 * (y1 + y2) * (z2 - z1))))


def compute_hydrostatics(
    mesh: HullMesh, draft: float, sections: int = 120
) -> HydrostaticResult:
    """Hidrostática da malha ``mesh`` no calado ``draft`` (a partir de z = 0)."""
    if draft <= 0:
        raise ValueError("O calado deve ser positivo.")
    triangles = mesh.vertices[mesh.triangulated()]
    if draft >= float(triangles[:, :, 2].max()):
        raise ValueError("O calado excede a altura do casco.")
    below, segments = _clip_below(triangles, draft)
    if not len(segments):
        raise ValueError("O calado informado não corta o casco.")

    a, b, c = below[:, 0], below[:, 1], below[:, 2]
    tetra = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    centroid_x = (a[:, 0] + b[:, 0] + c[:, 0]) / 4.0
    centroid_z = (a[:, 2] + b[:, 2] + c[:, 2]) / 4.0

    x1, y1 = segments[:, 0, 0], segments[:, 0, 1]
    x2, y2 = segments[:, 1, 0], segments[:, 1, 1]
    cross = x1 * y2 - x2 * y1
    sign = 1.0 if cross.sum() >= 0 else -1.0
    plane_area = sign * 0.5 * cross.sum()
    moment_x = sign * np.sum((x1 + x2) * cross) / 6.0
    inertia_x = sign * np.sum((x1**2 + x1 * x2 + x2**2) * cross) / 12.0
    inertia_y = sign * np.sum((y1**2 + y1 * y2 + y2**2) * cross) / 12.0
    if plane_area <= 0:
        raise ValueError("O plano de flutuação não tem área.")

    volume = tetra.sum() + draft * plane_area / 3.0
    volume_moment_x = (tetra * centroid_x).sum() + draft * moment_x / 4.0
    volume_moment_z = (tetra * centroid_z).sum() + draft**2 * plane_area / 4.0
    if volume <= 0:
        raise ValueError("Volume deslocado não positivo: a malha não está fechada.")

    lcb = volume_moment_x / volume
    kb = volume_moment_z / volume
    lcf = moment_x / plane_area
    il = inertia_x - plane_area * lcf**2
    it = inertia_y

    xs = segments[:, :, 0]
    lwl = float(xs.max() - xs.min())
    bwl = float(2.0 * np.abs(segments[:, :, 1]).max())

    stations = np.linspace(xs.min(), xs.max(), sections + 2)[1:-1]
    section_area = max(_section_area(below, float(x)) for x in stations)

    bm = it / volume
    return HydrostaticResult(
        T=float(draft),
        LWL=lwl,
        BWL=bwl,
        V=float(volume),
        Aw=float(plane_area),
        LCB=float(lcb),
        KB=float(kb),
        LCF=float(lcf),
        IL=float(il),
        IT=float(it),
        Ax=float(section_area),
        BM=float(bm),
        KM=float(kb + bm),
        Cp=float(volume / (section_area * lwl)),
        Cm=float(section_area / (bwl * draft)),
        Cw=float(plane_area / (lwl * bwl)),
        Cb=float(volume / (lwl * bwl * draft)),
    )


def maximum_draft(model: HullModel) -> float:
    """Calado máximo utilizável: a menor altura da linha de convés sobre a quilha."""
    offset = model.baseline_offset()
    u = np.linspace(0.0, 1.0, 100)
    heights = [
        float(bz.evaluate(curve, u)[:, 2].min() + offset[2]) for curve in model.deck
    ]
    return min(heights)


#: Calados da Tabela 3.6 em fração do pontal do casco de entrada (3,34 m).
DEFAULT_DRAFT_FRACTIONS = (0.74 / 3.34, 1.24 / 3.34, 1.74 / 3.34)


def default_drafts(model: HullModel) -> tuple[float, float, float]:
    """Três calados em fração do pontal; no casco SD são os da Tabela 3.6 (0,74, 1,24 e 1,74 m)."""
    limit = maximum_draft(model)
    return tuple(round(limit * fraction, 2) for fraction in DEFAULT_DRAFT_FRACTIONS)


def hydrostatic_table(
    model: HullModel, drafts: tuple[float, ...] | list[float]
) -> list[HydrostaticResult]:
    """Hidrostática do ``model`` para cada calado de ``drafts``."""
    limit = maximum_draft(model)
    mesh = model.build_mesh()
    results = []
    for draft in drafts:
        if draft >= limit:
            raise ValueError(
                f"O calado {draft:g} m excede o limite de {limit:.2f} m para este casco."
            )
        results.append(compute_hydrostatics(mesh, draft))
    return results
