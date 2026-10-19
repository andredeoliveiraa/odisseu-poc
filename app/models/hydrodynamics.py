"""Hidrostática e resistência ao avanço do casco.

A resistência segue o método do conjunto ShipD (Bagazinski e Ahmed, 2023):

* resistência de ondas pela integral de Michell (teoria do navio delgado);
* resistência friccional pela linha de correlação ITTC-57;
* resistência total ``Rt = Rw + Rf``, desprezando a resistência viscosa de
  pressão, como no artigo.

A integral de Michell supõe casco delgado (L/B grande) em regime de
deslocamento. Para cascos largos ou de planeio o valor é apenas indicativo,
útil para comparar formas entre si; ``validity_notes`` explica cada caso.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

GRAVITY = 9.81
SEAWATER_DENSITY = 1025.0
SEAWATER_VISCOSITY = 1.19e-6
"""Viscosidade cinemática da água do mar a 15 °C (m²/s)."""

KNOT = 0.514444


@dataclass(frozen=True)
class Hydrostatics:
    """Grandezas hidrostáticas na linha d'água z = 0."""

    volume: float
    displacement: float
    wetted_area: float
    waterplane_area: float
    waterline_length: float
    waterline_beam: float
    draft: float
    midship_area: float
    block_coefficient: float
    prismatic_coefficient: float
    midship_coefficient: float
    waterplane_coefficient: float
    lcb: float
    vcb: float
    lcf: float
    bm: float
    km: float


@dataclass(frozen=True)
class ResistancePoint:
    """Resistência a uma velocidade."""

    speed: float
    froude: float
    wave: float
    friction: float
    total: float
    wave_coefficient: float
    friction_coefficient: float
    effective_power: float


@dataclass(frozen=True)
class OffsetGrid:
    """Meias-bocas submersas ``f(x, z)`` numa grade regular."""

    x: np.ndarray
    z: np.ndarray
    half_breadth: np.ndarray


# --------------------------------------------------------------- hidrostática


def _clip_below_waterline(points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Recorta triângulos em z = 0 e devolve só a parte submersa.

    Retorna um arranjo ``(n, 3, 3)`` de triângulos que preservam a orientação
    original (normais para fora).
    """
    corners = points[triangles]
    below = corners[:, :, 2] <= 0.0
    count = below.sum(axis=1)
    pieces = [corners[count == 3]]

    def edge_point(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        t = a[:, 2] / (a[:, 2] - b[:, 2])
        return a + t[:, None] * (b - a)

    for kept in (1, 2):
        selected = corners[count == kept]
        if not len(selected):
            continue
        flags = below[count == kept]
        # Gira os vértices (mantendo a orientação) para que o vértice
        # "diferente" fique na posição 0.
        odd = flags if kept == 1 else ~flags
        shift = np.argmax(odd, axis=1)
        order = (np.arange(3)[None, :] + shift[:, None]) % 3
        rotated = np.take_along_axis(selected, order[:, :, None], axis=1)
        a, b, c = rotated[:, 0], rotated[:, 1], rotated[:, 2]
        ab, ac = edge_point(a, b), edge_point(a, c)
        if kept == 1:
            pieces.append(np.stack((a, ab, ac), axis=1))
        else:
            # a fica acima; b e c abaixo: quadrilátero (ab, b, c, ac).
            pieces.append(np.stack((ab, b, c), axis=1))
            pieces.append(np.stack((ab, c, ac), axis=1))
    return np.concatenate(pieces) if pieces else np.empty((0, 3, 3))


def _quadratic_integral(triangles: np.ndarray, values) -> np.ndarray:
    """Integra uma função quadrática em cada triângulo (regra dos pontos médios)."""
    midpoints = 0.5 * (triangles + np.roll(triangles, -1, axis=1))
    return values(midpoints).mean(axis=1)


def compute_hydrostatics(
    points: np.ndarray,
    triangles: np.ndarray,
    midship_area: float,
    density: float = SEAWATER_DENSITY,
) -> Hydrostatics:
    """Hidrostática exata de uma malha poliédrica fechada abaixo de z = 0.

    Usa o teorema da divergência sobre a superfície molhada: a tampa na linha
    d'água (z = 0) não contribui para as integrais de volume escolhidas, e
    suas propriedades saem da identidade ``∮ n dA = 0``.
    """
    wet = _clip_below_waterline(points, triangles)
    normal = 0.5 * np.cross(wet[:, 1] - wet[:, 0], wet[:, 2] - wet[:, 0])
    normal_z = normal[:, 2]
    centroid = wet.mean(axis=1)

    volume = float(np.sum(normal_z * centroid[:, 2]))
    if volume <= 0:
        raise ValueError("O casco não tem volume submerso.")
    moment_x = float(np.sum(normal_z * _quadratic_integral(wet, lambda p: p[..., 0] * p[..., 2])))
    moment_z = float(np.sum(normal_z * _quadratic_integral(wet, lambda p: 0.5 * p[..., 2] ** 2)))

    waterplane_area = float(-np.sum(normal_z))
    lcf = float(-np.sum(normal_z * centroid[:, 0]) / waterplane_area)
    inertia_t = float(-np.sum(normal_z * _quadratic_integral(wet, lambda p: p[..., 1] ** 2)))

    surface = wet.reshape(-1, 3)
    at_waterline = surface[np.abs(surface[:, 2]) < 1e-9]
    waterline_length = float(np.ptp(at_waterline[:, 0]))
    waterline_beam = float(np.ptp(at_waterline[:, 1]))
    draft = float(-surface[:, 2].min())

    vcb = moment_z / volume
    bm = inertia_t / volume
    return Hydrostatics(
        volume=volume,
        displacement=density * volume / 1000.0,
        wetted_area=float(np.linalg.norm(normal, axis=1).sum()),
        waterplane_area=waterplane_area,
        waterline_length=waterline_length,
        waterline_beam=waterline_beam,
        draft=draft,
        midship_area=midship_area,
        block_coefficient=volume / (waterline_length * waterline_beam * draft),
        prismatic_coefficient=volume / (midship_area * waterline_length),
        midship_coefficient=midship_area / (waterline_beam * draft),
        waterplane_coefficient=waterplane_area / (waterline_length * waterline_beam),
        lcb=moment_x / volume,
        vcb=vcb,
        lcf=lcf,
        bm=bm,
        km=vcb + draft + bm,
    )


# ------------------------------------------------------------------ offsets


def underwater_offsets(
    half_x: np.ndarray,
    half_y: np.ndarray,
    half_z: np.ndarray,
    length_points: int = 201,
    depth_points: int = 41,
) -> OffsetGrid:
    """Converte meias-seções (convés → quilha) em ``f(x, z)`` numa grade regular."""
    x_rows = half_x[:, -1]
    draft = float(-half_z.min())
    z_nodes = np.linspace(-draft, 0.0, depth_points)
    rows = np.empty((len(x_rows), depth_points))
    for row, (y_section, z_section) in enumerate(zip(half_y, half_z)):
        # Da quilha para cima; pequenas inversões (flat da quina) são achatadas.
        z_up = np.maximum.accumulate(z_section[::-1])
        y_up = y_section[::-1]
        rows[row] = np.interp(z_nodes, z_up, y_up, left=0.0, right=np.interp(0.0, z_up, y_up))
    x_nodes = np.linspace(x_rows.min(), x_rows.max(), length_points)
    grid = np.empty((length_points, depth_points))
    for column in range(depth_points):
        grid[:, column] = np.interp(x_nodes, x_rows, rows[:, column])
    return OffsetGrid(x=x_nodes, z=z_nodes, half_breadth=grid)


def midship_area(offsets: OffsetGrid) -> float:
    """Maior área seccional submersa."""
    areas = 2.0 * np.trapz(offsets.half_breadth, offsets.z, axis=1)
    return float(areas.max())


# ---------------------------------------------------------- integral de Michell


def _linear_exponential_weights(nodes: np.ndarray, rates: np.ndarray) -> np.ndarray:
    """Pesos de ``∫ φ(t) e^{s t} dt`` para φ linear por partes (Filon).

    Retorna ``(len(rates), len(nodes))``: o produto pelos valores nodais dá a
    integral exata da interpolação linear multiplicada pela exponencial,
    mesmo quando a exponencial oscila ou decai rápido dentro de um intervalo.
    """
    s = rates[:, None]
    a, b = nodes[None, :-1], nodes[None, 1:]
    h = b - a
    z = s * h
    exp_a, exp_b = np.exp(s * a), np.exp(s * b)
    small = np.abs(z) < 1e-4
    safe = np.where(small, 1.0, z)
    left = np.where(
        small,
        exp_a * h * (0.5 + z / 6.0 + z**2 / 24.0),
        (exp_b - exp_a - safe * exp_a) * h / safe**2,
    )
    right = np.where(
        small,
        exp_a * h * (0.5 + z / 3.0 + z**2 / 8.0),
        (exp_b * (safe - 1.0) + exp_a) * h / safe**2,
    )
    weights = np.zeros((len(rates), len(nodes)), dtype=np.result_type(left, right))
    weights[:, :-1] += left
    weights[:, 1:] += right
    return weights


def _lambda_grid(froude_length: float, maximum: float) -> tuple[np.ndarray, np.ndarray]:
    """Nós e pesos da integral em λ, já com o fator 1/√(λ²−1).

    Perto de λ = 1 usa λ = cosh(u), que remove a singularidade; depois, uma
    grade uniforme fina o bastante para a oscilação entre ondas de proa e popa
    (período 2π/(k₀L) em λ).
    """
    joint = 1.5
    u = np.linspace(0.0, np.arccosh(joint), 200)
    near = np.cosh(u)
    near_weight = np.gradient(u)  # dλ/√(λ²−1) = du
    near_weight[[0, -1]] *= 0.5
    step = min(0.05, 2 * np.pi / froude_length / 12.0)
    far = np.arange(joint, maximum + step, step)[1:]
    far_weight = np.full(far.shape, step) / np.sqrt(far**2 - 1.0)
    far_weight[-1] *= 0.5
    near_weight[-1] += 0.5 * step / np.sqrt(joint**2 - 1.0)
    return np.concatenate((near, far)), np.concatenate((near_weight, far_weight))


def michell_wave_resistance(
    offsets: OffsetGrid,
    speed: float,
    density: float = SEAWATER_DENSITY,
    gravity: float = GRAVITY,
    lambda_max: float = 40.0,
) -> float:
    """Resistência de ondas (N) pela integral de Michell.

    ``R = (4ρg²/πU²) ∫₁^∞ |P(λ)|² λ²/√(λ²−1) dλ``, com
    ``P = ∫∫ f_x e^{λ²k₀z} e^{iλk₀x} dx dz`` e ``k₀ = g/U²``. Integrando por
    partes em x, ``P = [f e^{iλk₀x}] − iλk₀ ∫∫ f e^{…}``, o que trata o
    espelho de popa (salto de f) sem derivar numericamente.
    """
    k0 = gravity / speed**2
    length = float(np.ptp(offsets.x))
    lam, lam_weight = _lambda_grid(k0 * length, lambda_max)

    wx = _linear_exponential_weights(offsets.x, 1j * lam * k0)
    wz = _linear_exponential_weights(offsets.z, lam**2 * k0)
    f = offsets.half_breadth
    interior = -1j * lam * k0 * np.einsum("lx,xz,lz->l", wx, f, wz)
    # Termos de contorno: f na popa (espelho) e na proa, ponderados em z.
    stern = (wz @ f[0]) * np.exp(1j * lam * k0 * offsets.x[0])
    bow = (wz @ f[-1]) * np.exp(1j * lam * k0 * offsets.x[-1])
    p = bow - stern + interior
    integral = np.sum(np.abs(p) ** 2 * lam**2 * lam_weight)
    return float(4.0 * density * gravity**2 / (np.pi * speed**2) * integral)


def ittc57_friction_coefficient(reynolds: float) -> float:
    """Linha de correlação ITTC-57: ``Cf = 0,075 / (log10 Re − 2)²``."""
    return 0.075 / (np.log10(reynolds) - 2.0) ** 2


def resistance_curve(
    offsets: OffsetGrid,
    hydrostatics: Hydrostatics,
    speeds: np.ndarray,
    density: float = SEAWATER_DENSITY,
    viscosity: float = SEAWATER_VISCOSITY,
) -> list[ResistancePoint]:
    """Resistência total ``Rt = Rw + Rf`` para cada velocidade (m/s)."""
    length = hydrostatics.waterline_length
    area = hydrostatics.wetted_area
    points = []
    for speed in np.asarray(speeds, dtype=float):
        dynamic = 0.5 * density * speed**2 * area
        wave = michell_wave_resistance(offsets, speed, density)
        friction_coefficient = ittc57_friction_coefficient(speed * length / viscosity)
        friction = friction_coefficient * dynamic
        total = wave + friction
        points.append(
            ResistancePoint(
                speed=float(speed),
                froude=float(speed / np.sqrt(GRAVITY * length)),
                wave=wave,
                friction=friction,
                total=total,
                wave_coefficient=wave / dynamic,
                friction_coefficient=friction_coefficient,
                effective_power=total * speed,
            )
        )
    return points


def validity_notes(hydrostatics: Hydrostatics, maximum_froude: float) -> list[str]:
    """Explica quando a integral de Michell deixa de ser confiável."""
    notes = []
    slenderness = hydrostatics.waterline_length / hydrostatics.waterline_beam
    if slenderness < 6.0:
        notes.append(
            f"L/B = {slenderness:.1f}: a integral de Michell supõe casco delgado "
            "(L/B ≳ 6). Para cascos largos ela superestima a resistência de ondas; "
            "use o valor para comparar formas, não como previsão absoluta."
        )
    if maximum_froude > 0.5:
        notes.append(
            f"Fn até {maximum_froude:.2f}: acima de ≈0,5 o casco entra em "
            "semiplaneio e acima de ≈1 em planeio, fora da teoria de deslocamento. "
            "Para planeio, métodos como o de Savitsky são mais adequados."
        )
    return notes
