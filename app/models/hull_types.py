"""Cascos iniciais (planeio, semi-deslocamento e deslocamento) e seu construtor.

Na tese, o projetista parte de um casco inicial obtido a partir de vistas
ortogonais 2D (seção 3.2.3) e guardado no banco do ModiYacht. Aqui o casco
inicial é construído a partir de um conjunto de parâmetros e de um *estilo*
(ângulos das tangentes das curvas), o que também permite gerar cascos
completos para a amostragem de projetos.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.models import bezier as bz
from app.models.hull_model import HullModel, HullParameters, Station

PLANING = "P"
SEMI_DISPLACEMENT = "SD"
DISPLACEMENT = "D"

HULL_TYPE_NAMES = {
    PLANING: "Planeio",
    SEMI_DISPLACEMENT: "Semi-deslocamento",
    DISPLACEMENT: "Deslocamento",
}


@dataclass(frozen=True)
class HullStyle:
    """Ângulos (em graus) que dão a cada tipo de casco o seu caráter.

    Os ângulos das estações valem para as estações 1, 2 e 3. ``None`` em um
    ângulo das linhas inferiores significa "ao longo da corda" (linha reta).
    """

    #: Razão (meia-boca da quina) / (meia-boca do convés) em cada estação.
    chine_ratio: tuple[float, float, float]
    #: Ângulo da linha superior com a vertical, no convés (abertura das obras mortas).
    flare: tuple[float, float, float]
    #: Ângulo da linha superior com a vertical, na quina.
    side: tuple[float, float, float]
    #: Ângulo da linha inferior com a horizontal, na quina (``None``: corda).
    lower_start: tuple[float | None, float | None, float | None]
    #: Ângulo da linha inferior com a horizontal, na quilha (``None``: corda).
    lower_end: tuple[float | None, float | None, float | None]
    #: Inclinação da quilha na proa (para baixo, em direção à popa).
    forefoot: float
    #: Rumo (em relação ao eixo) da linha de quina na proa, como fração de ``theta``.
    chine_heading: float
    #: Em casco sem quina, a linha inferior continua a tangente da superior.
    smooth_chine: bool = False


STYLES: dict[str, HullStyle] = {
    # Calibrado para reproduzir os 28 parâmetros da Tabela 3.4, a hidrostática
    # da Tabela 3.6 (erros típicos de até 5 %) e o alcance dos raios da Figura 3.16(b).
    SEMI_DISPLACEMENT: HullStyle(
        chine_ratio=(0.72, 0.58, 0.50),
        flare=(0.04, 0.08, 14.38),
        side=(44.92, 63.68, 51.36),
        lower_start=(34.10, 25.92, 31.76),
        lower_end=(15.52, 31.24, 10.88),
        forefoot=3.0,
        chine_heading=0.10,
    ),
    PLANING: HullStyle(
        chine_ratio=(0.93, 0.93, 0.90),
        flare=(12.0, 6.0, 2.0),
        side=(12.0, 6.0, 2.0),
        lower_start=(None, None, None),
        lower_end=(None, None, None),
        forefoot=22.0,
        chine_heading=0.75,
    ),
    DISPLACEMENT: HullStyle(
        chine_ratio=(0.90, 0.90, 0.85),
        flare=(3.0, 1.0, 0.0),
        side=(22.0, 20.0, 16.0),
        lower_start=(None, None, None),
        lower_end=(0.0, 0.0, 0.0),
        forefoot=18.0,
        chine_heading=0.6,
        smooth_chine=True,
    ),
}


#: Parâmetros dos três cascos iniciais. O semi-deslocamento usa a Tabela 3.4.
INITIAL_PARAMETERS: dict[str, HullParameters] = {
    SEMI_DISPLACEMENT: HullParameters(),
    PLANING: HullParameters(
        Le=6.0, Lm=7.0, Lr=3.0,
        Be=4.8, Bm=4.8, Br=4.4,
        De=2.4, Dm=2.0, Dr=1.7,
        Fe=1.4, Fm=1.1, Fr=0.9, Fb=1.1,
        Ce=0.15, Cm=0.15, Cr=0.10,
        Rek=4.0, Res1=0.0, Res2=0.0, Rms1=0.0, Rms2=0.0, Rrs1=0.0, Rrs2=0.0,
        H=1.3, K=0.0, beta=65.0, alpha=0.0, theta=24.0,
    ),
    DISPLACEMENT: HullParameters(
        Le=7.0, Lm=9.0, Lr=4.0,
        Be=5.2, Bm=5.2, Br=4.0,
        De=3.2, Dm=3.2, Dr=2.4,
        Fe=1.4, Fm=1.4, Fr=1.1, Fb=1.0,
        Ce=0.0, Cm=0.0, Cr=0.0,
        Rek=6.0, Res1=50.0, Res2=2.0, Rms1=50.0, Rms2=2.0, Rrs1=50.0, Rrs2=1.5,
        H=1.8, K=0.0, beta=75.0, alpha=0.0, theta=22.0,
    ),
}

HULL_DESCRIPTIONS = {
    SEMI_DISPLACEMENT: "Quinas suaves, fundo em V raso e bojo arredondado.",
    PLANING: "Fundo em V profundo, quinas duplas e linhas retas.",
    DISPLACEMENT: "Casco redondo, sem quina, de bojo arredondado.",
}


def _pchip_slopes(a: np.ndarray, values: np.ndarray, start: float | None = None) -> np.ndarray:
    """Inclinações ``dv/da`` monotônicas (Fritsch-Carlson) nos nós ``a``.

    ``start`` impõe a inclinação do primeiro nó (por exemplo, o ângulo de
    entrada na proa). A inclinação do último nó usa a fórmula de extremidade
    de três pontos, limitada para não ultrapassar a monotonicidade.
    """
    h = np.diff(a)
    delta = np.diff(values) / h
    slopes = np.zeros(len(a))
    for i in range(1, len(a) - 1):
        if delta[i - 1] * delta[i] > 0:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            slopes[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])

    def end_slope(h0, h1, d0, d1):
        slope = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if np.sign(slope) != np.sign(d0):
            return 0.0
        if np.sign(d0) != np.sign(d1) and abs(slope) > 3 * abs(d0):
            return 3 * d0
        return slope

    slopes[0] = end_slope(h[0], h[1], delta[0], delta[1]) if start is None else start
    slopes[-1] = end_slope(h[-1], h[-2], delta[-1], delta[-2])
    return slopes


def _longitudinal_curves(points: np.ndarray, slopes_yz: np.ndarray) -> list[np.ndarray]:
    """Béziers entre âncoras, com tangente ``(−1, dy/da, dz/da)`` em cada âncora."""
    directions = np.column_stack(
        (-np.ones(len(points)), slopes_yz[:, 0], slopes_yz[:, 1])
    )
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    curves = []
    for i in range(len(points) - 1):
        chord = np.linalg.norm(points[i + 1] - points[i])
        curves.append(
            np.array(
                [
                    points[i],
                    points[i] + directions[i] * chord / 3.0,
                    points[i + 1] - directions[i + 1] * chord / 3.0,
                    points[i + 1],
                ]
            )
        )
    return curves


def _station_curve(
    start: np.ndarray,
    end: np.ndarray,
    start_dir: np.ndarray | None,
    end_dir: np.ndarray | None,
) -> np.ndarray:
    """Bézier 2D entre dois pontos, com tangentes de partida e chegada."""
    chord = end - start
    length = float(np.linalg.norm(chord))
    chord_dir = chord / max(length, 1e-12)
    start_dir = chord_dir if start_dir is None else start_dir
    end_dir = chord_dir if end_dir is None else end_dir
    return np.array(
        [start, start + start_dir * length / 3.0, end - end_dir * length / 3.0, end]
    )


def _direction(angle_degrees: float, from_vertical: bool) -> np.ndarray:
    """Direção (y, z) que desce para dentro do casco.

    ``from_vertical``: ângulo medido a partir da vertical (linha superior);
    caso contrário, a partir da horizontal (linha inferior).
    """
    angle = np.radians(angle_degrees)
    if from_vertical:
        return np.array([-np.sin(angle), -np.cos(angle)])
    return np.array([-np.cos(angle), -np.sin(angle)])


def build_hull(
    parameters: HullParameters,
    hull_type: str = SEMI_DISPLACEMENT,
    name: str | None = None,
) -> HullModel:
    """Constrói um casco com os ``parameters`` dados no estilo de ``hull_type``."""
    validate_parameters(parameters)
    style = STYLES[hull_type]
    p = parameters
    tan_alpha = np.tan(np.radians(p.alpha))

    def deck_z(x: float) -> float:
        return float(tan_alpha * x)

    x3 = 0.0
    x2 = p.Lr
    x1 = p.Lr + p.Lm
    x_bow = p.Lr + p.Lm + p.Le

    widths = (p.Be, p.Bm, p.Br)
    depths = (p.De, p.Dm, p.Dr)
    chine_drops = (p.Fe, p.Fm, p.Fr)
    thickness = (p.Ce, p.Cm, p.Cr)
    x_stations = (x1, x2, x3)
    radii_upper = (p.Res1, p.Rms1, p.Rrs1)
    radii_lower = (p.Res2, p.Rms2, p.Rrs2)

    stations: list[Station] = []
    for index in range(3):
        x = x_stations[index]
        z_deck = deck_z(x)
        half = 0.5 * widths[index]
        center_y = style.chine_ratio[index] * half
        chine_z = z_deck - chine_drops[index]
        keel_z = z_deck - depths[index]
        outer = center_y + 0.5 * thickness[index]
        inner = center_y - 0.5 * thickness[index]

        s0 = np.array([half, z_deck])
        s3 = np.array([outer, chine_z])
        s4 = np.array([inner, chine_z])
        s7 = np.array([p.K, keel_z])

        upper_start = _direction(style.flare[index], True)
        upper_end = _direction(style.side[index], True)
        upper = _station_curve(s0, s3, upper_start, upper_end)
        upper, _ = bz.set_minimum_radius(upper, radii_upper[index])

        lower_start_angle = style.lower_start[index]
        lower_end_angle = style.lower_end[index]
        if style.smooth_chine:
            lower_start = upper_end
        else:
            lower_start = (
                None if lower_start_angle is None else _direction(lower_start_angle, False)
            )
        lower_end = None if lower_end_angle is None else _direction(lower_end_angle, False)
        lower = _station_curve(s4, s7, lower_start, lower_end)
        lower, _ = bz.set_minimum_radius(lower, radii_lower[index])
        stations.append(Station(x, upper, lower))

    height = p.H
    rake = height / np.tan(np.radians(p.beta))
    bow_top = np.array([x_bow, deck_z(x_bow)])
    bow_low = np.array([x_bow - rake, bow_top[1] - height])
    chine_fraction = p.Fb / height
    bow_chine = bow_top + (bow_low - bow_top) * chine_fraction

    def anchors(rows: list[tuple[float, float, float]]) -> np.ndarray:
        return np.array(rows, dtype=float)

    # Âncoras (x, y, z) ao longo do comprimento, da proa à popa.
    deck_points = anchors(
        [(x_bow, 0.0, bow_top[1])]
        + [(s.x, s.upper[0, 0], s.upper[0, 1]) for s in stations]
    )
    chine_points = anchors(
        [(bow_chine[0], 0.0, bow_chine[1])]
        + [(s.x, *s.chine_center) for s in stations]
    )
    keel_points = anchors(
        [(bow_low[0], 0.0, bow_low[1])] + [(s.x, 0.0, s.keel_z) for s in stations]
    )

    def aft_distance(points: np.ndarray) -> np.ndarray:
        return points[0, 0] - points[:, 0]

    # Convés: ângulo de entrada na proa; z segue o plano do tosamento.
    a = aft_distance(deck_points)
    deck_y = _pchip_slopes(a, deck_points[:, 1], start=float(np.tan(np.radians(p.theta))))
    deck_z_slope = np.full(len(a), -tan_alpha)
    deck = _longitudinal_curves(deck_points, np.column_stack((deck_y, deck_z_slope)))

    a = aft_distance(chine_points)
    chine_y = _pchip_slopes(
        a, chine_points[:, 1], start=float(np.tan(np.radians(style.chine_heading * p.theta)))
    )
    chine_z = _pchip_slopes(a, chine_points[:, 2])
    chine = _longitudinal_curves(chine_points, np.column_stack((chine_y, chine_z)))

    a = aft_distance(keel_points)
    keel_z_slopes = _pchip_slopes(
        a, keel_points[:, 2], start=-float(np.tan(np.radians(style.forefoot)))
    )
    keel = _longitudinal_curves(
        keel_points, np.column_stack((np.zeros(len(a)), keel_z_slopes))
    )
    keel[0], _ = bz.set_minimum_radius(keel[0], p.Rek)

    return HullModel(
        name=name or HULL_TYPE_NAMES[hull_type],
        hull_type=hull_type,
        bow_top=bow_top,
        bow_low=bow_low,
        chine_depth=p.Fb,
        stations=stations,
        deck=deck,
        keel=keel,
        chine=chine,
    )


def validate_parameters(p: HullParameters) -> None:
    """Rejeita combinações que não formam um casco."""
    if min(p.Le, p.Lm, p.Lr) <= 0:
        raise ValueError("Os comprimentos das regiões devem ser positivos.")
    if min(p.Be, p.Bm, p.Br) <= 0:
        raise ValueError("A boca em cada estação deve ser positiva.")
    for depth, drop, label in ((p.De, p.Fe, "1"), (p.Dm, p.Fm, "2"), (p.Dr, p.Fr, "3")):
        if depth <= 0:
            raise ValueError(f"O pontal da estação {label} deve ser positivo.")
        if not 0 < drop < depth:
            raise ValueError(
                f"A quina da estação {label} deve ficar entre o convés e a quilha."
            )
    if min(p.Ce, p.Cm, p.Cr) < 0 or p.K < 0:
        raise ValueError("As espessuras de quina e de quilha não podem ser negativas.")
    if not 1.0 <= p.beta <= 179.0:
        raise ValueError("O ângulo de proa deve estar entre 1° e 179°.")
    if not 1.0 <= p.theta <= 89.0:
        raise ValueError("O ângulo de entrada deve estar entre 1° e 89°.")
    if not -45.0 <= p.alpha <= 45.0:
        raise ValueError("O ângulo de tosamento deve estar entre -45° e 45°.")
    if p.H <= 0:
        raise ValueError("O comprimento vertical da roda de proa deve ser positivo.")
    if not 0 <= p.Fb <= p.H:
        raise ValueError("A quina na proa deve ficar sobre a roda de proa (0 ≤ Fb ≤ H).")


def initial_hull(hull_type: str) -> HullModel:
    """Casco inicial do tipo pedido, com os parâmetros de ``INITIAL_PARAMETERS``."""
    return build_hull(INITIAL_PARAMETERS[hull_type], hull_type)
