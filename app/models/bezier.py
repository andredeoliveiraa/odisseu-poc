"""Curvas de Bézier cúbicas e a abordagem iterativa (IA) da seção 3.3.2.

Cada curva característica do casco é uma Bézier cúbica (equações 3.1 e 3.2).
Ao modificar o casco, os pontos de controle internos ``P1`` e ``P2`` são
recalculados mantendo as tangentes das extremidades; a escolha é a que
maximiza a função objetivo ``F`` (equação 3.3), a similaridade entre as
distribuições de curvatura da curva de entrada e da modificada.
"""

from __future__ import annotations

import numpy as np

#: Divisões da curva para a distribuição de curvatura (ξ), Grupo-1.
CURVATURE_SAMPLES = 1000
#: Constante de divisão (µ) das posições candidatas, Grupo-1.
DIVISION_CONSTANT = 15
#: Valores usados pelo operador de raio mínimo de curvatura (Grupo-2).
RADIUS_CURVATURE_SAMPLES = 10000
RADIUS_DIVISION_CONSTANT = 350

_EPSILON = 1e-12


def evaluate(control: np.ndarray, u: np.ndarray | float) -> np.ndarray:
    """Avalia a cúbica ``P(u)`` (equação 3.2); ``u`` pode ser escalar ou vetor."""
    control = np.asarray(control, dtype=float)
    u = np.atleast_1d(np.asarray(u, dtype=float))[:, None]
    v = 1.0 - u
    return (
        control[0] * v**3
        + control[1] * 3.0 * u * v**2
        + control[2] * 3.0 * u**2 * v
        + control[3] * u**3
    )


def first_derivative(control: np.ndarray, u: np.ndarray) -> np.ndarray:
    control = np.asarray(control, dtype=float)
    u = np.atleast_1d(np.asarray(u, dtype=float))[:, None]
    v = 1.0 - u
    return 3.0 * (
        (control[1] - control[0]) * v**2
        + 2.0 * (control[2] - control[1]) * u * v
        + (control[3] - control[2]) * u**2
    )


def second_derivative(control: np.ndarray, u: np.ndarray) -> np.ndarray:
    control = np.asarray(control, dtype=float)
    u = np.atleast_1d(np.asarray(u, dtype=float))[:, None]
    return 6.0 * (
        (control[2] - 2.0 * control[1] + control[0]) * (1.0 - u)
        + (control[3] - 2.0 * control[2] + control[1]) * u
    )


def _curvature_from_derivatives(d1: np.ndarray, d2: np.ndarray) -> np.ndarray:
    """Curvatura ``κ = |P' × P''| / |P'|³`` (equação 3.4), em 2D ou 3D."""
    if d1.shape[-1] == 2:
        cross = np.abs(d1[..., 0] * d2[..., 1] - d1[..., 1] * d2[..., 0])
    else:
        cross = np.linalg.norm(np.cross(d1, d2), axis=-1)
    speed = np.linalg.norm(d1, axis=-1)
    return cross / np.maximum(speed, _EPSILON) ** 3


def curvature(control: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Curvatura da curva nos parâmetros ``u``."""
    return _curvature_from_derivatives(
        first_derivative(control, u), second_derivative(control, u)
    )


def curvature_distribution(control: np.ndarray, samples: int = CURVATURE_SAMPLES) -> np.ndarray:
    """Curvatura em ``samples`` pontos igualmente espaçados em ``u``."""
    return curvature(control, np.linspace(0.0, 1.0, samples))


def minimum_radius(control: np.ndarray, samples: int = CURVATURE_SAMPLES) -> float:
    """Menor raio de curvatura da curva; ``inf`` se ela for reta."""
    kappa = curvature_distribution(control, samples).max()
    return float("inf") if kappa < 1e-9 else float(1.0 / kappa)


def length(control: np.ndarray, samples: int = 200) -> float:
    """Comprimento aproximado da curva."""
    points = evaluate(control, np.linspace(0.0, 1.0, samples))
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def unit(vector: np.ndarray, fallback: np.ndarray | None = None) -> np.ndarray:
    """Normaliza um vetor; devolve ``fallback`` (ou zeros) se ele for nulo."""
    vector = np.asarray(vector, dtype=float)
    norm = np.linalg.norm(vector)
    if norm < _EPSILON:
        return np.zeros_like(vector) if fallback is None else np.asarray(fallback, float)
    return vector / norm


def end_directions(control: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Direções unitárias ``n̂1`` (de P0 para P1) e ``n̂2`` (de P3 para P2)."""
    control = np.asarray(control, dtype=float)
    chord = unit(control[3] - control[0])
    return unit(control[1] - control[0], chord), unit(control[2] - control[3], -chord)


def critical_parameters(
    p0: np.ndarray, n1: np.ndarray, p3: np.ndarray, n2: np.ndarray
) -> tuple[float, float]:
    """Parâmetros ``(t´, ḱ)`` do ponto crítico (interseção das duas tangentes).

    Em 3D as retas costumam ser reversas; usa-se então o par de pontos de
    menor distância. Quando não há interseção útil (retas paralelas ou que se
    afastam), recorre-se a metade da corda, o que mantém a busca limitada.
    """
    chord = float(np.linalg.norm(p3 - p0))
    fallback = (0.5 * chord, 0.5 * chord)
    w = p0 - p3
    a, b, c = float(n1 @ n1), float(n1 @ n2), float(n2 @ n2)
    d, e = float(n1 @ w), float(n2 @ w)
    denominator = a * c - b * b
    if denominator < 1e-9:
        return fallback
    t = (b * e - c * d) / denominator
    k = (a * e - b * d) / denominator
    if t <= 1e-6 or k <= 1e-6:
        return fallback
    # Tangentes quase paralelas cruzam muito longe: limita a busca.
    limit = 2.0 * max(chord, _EPSILON)
    return min(t, limit), min(k, limit)


def _curvature_at(controls: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Curvatura de várias curvas ``(n, 4, d)`` nos parâmetros ``u`` ``(n ou 1, m)`` → ``(n, m)``."""
    u = u[:, :, None]
    v = 1.0 - u
    p0, p1, p2, p3 = (controls[:, i, None, :] for i in range(4))
    d1 = 3.0 * ((p1 - p0) * v**2 + 2.0 * (p2 - p1) * u * v + (p3 - p2) * u**2)
    d2 = 6.0 * ((p2 - 2.0 * p1 + p0) * v + (p3 - 2.0 * p2 + p1) * u)
    return _curvature_from_derivatives(d1, d2)


def _curvature_batch(controls: np.ndarray, samples: int) -> np.ndarray:
    """Curvatura de várias curvas ``(n, 4, d)`` em ``samples`` pontos → ``(n, samples)``."""
    return _curvature_at(controls, np.linspace(0.0, 1.0, samples)[None, :])


#: Pontos da grade fina em torno do máximo grosso (a grade grossa tem ``ξ / 10``).
_REFINE_POINTS = 21


def _max_curvature(controls: np.ndarray, samples: int) -> np.ndarray:
    """Curvatura máxima de cada curva, com a resolução de ``samples`` pontos.

    Uma grade grossa de ``samples / 10`` pontos localiza o máximo; uma grade
    fina de ``_REFINE_POINTS`` pontos entre os vizinhos dele devolve o espaçamento
    de uma grade uniforme de ``samples`` pontos, com cerca de um décimo do custo.
    """
    coarse = max(100, samples // 10)
    if coarse >= samples:
        return _curvature_batch(controls, samples).max(axis=1)
    kappa = _curvature_batch(controls, coarse)
    peak = kappa.argmax(axis=1)
    step = 1.0 / (coarse - 1)
    centre = peak * step
    low = np.clip(centre - step, 0.0, 1.0)
    high = np.clip(centre + step, 0.0, 1.0)
    fine = low[:, None] + (high - low)[:, None] * np.linspace(0.0, 1.0, _REFINE_POINTS)[None, :]
    return np.maximum(kappa.max(axis=1), _curvature_at(controls, fine).max(axis=1))


def similarity(reference: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """Função objetivo ``F``: cosseno entre as distribuições de curvatura.

    A tese escreve ``F`` sobre os raios de curvatura. Aqui o cosseno é feito
    sobre as curvaturas ``κ = 1/R``, que carregam a mesma informação de forma
    sem o ``R → ∞`` dos trechos retos; ``F`` continua entre 0 e 1 e vale 1 para
    curvas de mesma forma, qualquer que seja a escala.
    """
    reference_norm = np.linalg.norm(reference)
    norms = np.linalg.norm(candidates, axis=1)
    if reference_norm < 1e-9:
        # Referência reta: a melhor candidata é a menos curva.
        return -norms
    return (candidates @ reference) / (np.maximum(norms, _EPSILON) * reference_norm)


def refit_curve(
    reference: np.ndarray,
    p0: np.ndarray,
    p3: np.ndarray,
    n1: np.ndarray | None = None,
    n2: np.ndarray | None = None,
    division: int = DIVISION_CONSTANT,
    samples: int = CURVATURE_SAMPLES,
) -> np.ndarray:
    """Reposiciona ``P1`` e ``P2`` pela abordagem iterativa (IA).

    Args:
        reference: curva de entrada ``(4, d)``, cuja curvatura a nova curva
            deve imitar.
        p0, p3: novos pontos extremos.
        n1, n2: direções das tangentes nas extremidades; por padrão, as da
            curva de entrada (mantém ang1 e ang2 e, com elas, a continuidade G1).
        division: constante de divisão µ; são avaliadas ``µ × µ`` combinações.
        samples: ξ, número de pontos da distribuição de curvatura.

    Returns:
        Nova curva ``(4, d)`` com ``P0 = p0`` e ``P3 = p3``.
    """
    reference = np.asarray(reference, dtype=float)
    p0 = np.asarray(p0, dtype=float)
    p3 = np.asarray(p3, dtype=float)
    ref_n1, ref_n2 = end_directions(reference)
    n1 = ref_n1 if n1 is None else unit(n1, ref_n1)
    n2 = ref_n2 if n2 is None else unit(n2, ref_n2)

    if np.linalg.norm(p3 - p0) < _EPSILON:
        return np.array([p0, p0, p3, p3])

    t_max, k_max = critical_parameters(p0, n1, p3, n2)
    steps = np.arange(1, division + 1) / division
    t_values = steps * t_max
    k_values = steps * k_max
    t_grid, k_grid = np.meshgrid(t_values, k_values, indexing="ij")
    count = division * division
    candidates = np.empty((count, 4, len(p0)))
    candidates[:, 0] = p0
    candidates[:, 3] = p3
    candidates[:, 1] = p0 + n1 * t_grid.reshape(-1, 1)
    candidates[:, 2] = p3 + n2 * k_grid.reshape(-1, 1)

    reference_curvature = curvature_distribution(reference, samples)
    scores = similarity(reference_curvature, _curvature_batch(candidates, samples))
    best = candidates[int(np.argmax(scores))]
    return best.copy()


def radius_family(
    p0: np.ndarray,
    p3: np.ndarray,
    n1: np.ndarray,
    n2: np.ndarray,
    fractions: np.ndarray,
) -> np.ndarray:
    """Curvas ``(n, 4, d)`` com ``P1, P2`` a uma fração do ponto crítico.

    As duas alças se aproximam juntas do ponto crítico, como no operador de
    raio mínimo (3.3.3.1); ``fractions`` vai de perto de 0 até 1.
    """
    p0 = np.asarray(p0, dtype=float)
    p3 = np.asarray(p3, dtype=float)
    t_max, k_max = critical_parameters(p0, n1, p3, n2)
    fractions = np.asarray(fractions, dtype=float)[:, None]
    curves = np.empty((len(fractions), 4, len(p0)))
    curves[:, 0] = p0
    curves[:, 3] = p3
    curves[:, 1] = p0 + n1 * fractions * t_max
    curves[:, 2] = p3 + n2 * fractions * k_max
    return curves


def _minimum_radius_batch(controls: np.ndarray, samples: int) -> np.ndarray:
    kappa = _max_curvature(controls, samples)
    return np.where(kappa < 1e-9, np.inf, 1.0 / np.maximum(kappa, _EPSILON))


#: Menor fração do ponto crítico usada; abaixo disso as alças se confundem
#: com as extremidades e a direção das tangentes se perde.
MINIMUM_HANDLE_FRACTION = 0.02


#: Fator de redução das amostras na varredura grossa da família de curvas.
COARSE_SAMPLE_DIVISOR = 10
#: Folga (em índices da família) em torno do pico e do intervalo refinados.
_REFINE_MARGIN = 3


def _radius_profile(
    curve: np.ndarray, division: int, samples: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Família de curvas e seus raios mínimos, com refino em torno do pico.

    A varredura inteira usa poucas amostras (ela só localiza o pico e o
    intervalo da solução); os raios perto do pico são recalculados com as
    ``samples`` pedidas. Devolve ``(frações, família, n1, n2, raios, pico)``.
    """
    n1, n2 = end_directions(curve)
    fractions = np.linspace(MINIMUM_HANDLE_FRACTION, 1.0, division)
    family = radius_family(curve[0], curve[3], n1, n2, fractions)
    coarse = max(200, samples // COARSE_SAMPLE_DIVISOR)
    radii = _minimum_radius_batch(family, min(coarse, samples))
    radii = np.where(np.isfinite(radii), radii, 0.0)
    if coarse < samples:
        peak = int(np.argmax(radii))
        near = np.arange(max(peak - _REFINE_MARGIN, 0), min(peak + _REFINE_MARGIN + 1, division))
        fine = _minimum_radius_batch(family[near], samples)
        radii[near] = np.where(np.isfinite(fine), fine, 0.0)
    return fractions, family, n1, n2, radii, int(np.argmax(radii))


def maximum_achievable_radius(
    curve: np.ndarray,
    division: int = RADIUS_DIVISION_CONSTANT,
    samples: int = RADIUS_CURVATURE_SAMPLES,
) -> float:
    """Maior raio mínimo de curvatura que a curva consegue assumir."""
    curve = np.asarray(curve, dtype=float)
    _, _, _, _, radii, peak = _radius_profile(curve, division, samples)
    return float(radii[peak])


def set_minimum_radius(
    curve: np.ndarray,
    target: float,
    division: int = RADIUS_DIVISION_CONSTANT,
    samples: int = RADIUS_CURVATURE_SAMPLES,
) -> tuple[np.ndarray, float]:
    """Ajusta o menor raio de curvatura da curva ao valor ``target``.

    Percorre a família de curvas em que as alças se aproximam do ponto
    crítico. O raio mínimo cresce com a fração até um máximo e depois decai;
    a solução é procurada no ramo crescente.

    Returns:
        ``(nova_curva, raio_máximo)``. Se ``target`` excede o raio máximo, a
        curva devolvida é a de maior raio e o chamador decide como avisar.
    """
    curve = np.asarray(curve, dtype=float)
    fractions, family, n1, n2, radii, peak = _radius_profile(curve, division, samples)
    maximum = float(radii[peak])
    if target >= maximum:
        return family[peak].copy(), maximum
    if target <= radii[0]:
        return family[0].copy(), maximum

    def radius_at(fraction: float) -> float:
        candidate = radius_family(curve[0], curve[3], n1, n2, np.array([fraction]))
        return float(_minimum_radius_batch(candidate, samples)[0])

    increasing = radii[: peak + 1]
    index = int(np.searchsorted(np.maximum.accumulate(increasing), target))
    low = fractions[max(index - 1 - _REFINE_MARGIN // 2, 0)]
    high = fractions[min(index + _REFINE_MARGIN // 2, peak)]
    # A varredura grossa pode errar um pouco o raio: garante o intervalo.
    for _ in range(division):
        if radius_at(low) <= target or low <= MINIMUM_HANDLE_FRACTION:
            break
        low = max(low - (fractions[1] - fractions[0]), MINIMUM_HANDLE_FRACTION)
    for _ in range(division):
        if radius_at(high) >= target or high >= fractions[peak]:
            break
        high = min(high + (fractions[1] - fractions[0]), fractions[peak])
    for _ in range(24):
        middle = 0.5 * (low + high)
        if radius_at(middle) < target:
            low = middle
        else:
            high = middle
    best = radius_family(curve[0], curve[3], n1, n2, np.array([0.5 * (low + high)]))
    return best[0], maximum
