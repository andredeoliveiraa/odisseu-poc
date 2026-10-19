"""Operadores de forma do casco (seção 3.3 da referência).

Cada operador recebe um :class:`HullModel`, devolve um novo modelo e deixa o
original intacto. Todos obedecem aos três critérios de qualidade da tese:

1. **continuidade geométrica** G0 e G1 entre curvas vizinhas: as extremidades
   são ligadas às estações (``HullModel.link``) e as tangentes das curvas
   refeitas são mantidas, de modo que os segmentos de controle que se
   encontram numa estação continuam colineares;
2. **fairness**: as curvas cujas extremidades se movem são refeitas pela
   abordagem iterativa (IA), que reproduz a distribuição de curvatura da
   curva de entrada;
3. **modificação independente**: cada operador move só o necessário, o que
   mantém os demais parâmetros como estavam.

Grupo-1 (IA): alongamento, alargamento, aprofundamento, ângulos de proa,
de entrada e de tosamento, comprimento vertical da roda de proa, espessuras
de quina e de quilha, inserção/remoção de quina e posição da quina.
Grupo-2: raio mínimo de curvatura e concavidade das estações.
"""

from __future__ import annotations

import numpy as np

from app.models import bezier as bz
from app.models.hull_model import HullModel, HullParameters

#: Tolerância para considerar que um parâmetro não foi alterado.
TOLERANCE = 1e-6

#: Nomes de curva usados nas sobreposições de direção: (tipo, índice).
CurveKey = tuple[str, int]


class OperatorError(ValueError):
    """Um operador não pôde ser aplicado com o valor pedido."""


class RadiusNotAchievable(OperatorError):
    """O raio mínimo pedido excede o que a curva consegue assumir."""

    def __init__(self, parameter: str, requested: float, maximum: float) -> None:
        self.parameter = parameter
        self.requested = requested
        self.maximum = maximum
        super().__init__(
            f"Informe outro valor para {parameter}. O valor {requested:g} m excede "
            f"o limite máximo alcançável de {maximum:.4f} m para esta curva."
        )


# ----------------------------------------------------------------------
# Refazimento das curvas pela IA
# ----------------------------------------------------------------------
def _refit(
    old: HullModel,
    new: HullModel,
    forced: set[CurveKey] | None = None,
    directions: dict[CurveKey, tuple[np.ndarray | None, np.ndarray | None]] | None = None,
) -> HullModel:
    """Refaz as curvas de ``new`` cujas extremidades mudaram em relação a ``old``.

    Antes de chamar, ``new`` já tem as âncoras (estações, proa) alteradas.
    ``link`` leva as extremidades das curvas até as âncoras; só as curvas que
    de fato se moveram são refeitas. Um deslocamento rígido é aplicado
    exatamente (a IA acharia a mesma forma, mas com a discretização de µ).
    """
    forced = forced or set()
    directions = directions or {}
    new.link()

    def rebuild(key: CurveKey, old_curve: np.ndarray, new_curve: np.ndarray) -> np.ndarray:
        start, end = new_curve[0], new_curve[3]
        moved_start = start - old_curve[0]
        moved_end = end - old_curve[3]
        if key not in forced:
            if np.allclose(moved_start, 0, atol=1e-9) and np.allclose(moved_end, 0, atol=1e-9):
                return old_curve.copy()
            if np.allclose(moved_start, moved_end, atol=1e-9):
                return old_curve + moved_start
        n1, n2 = directions.get(key, (None, None))
        return bz.refit_curve(old_curve, start, end, n1, n2)

    for region in range(3):
        for kind, new_list, old_list in (
            ("deck", new.deck, old.deck),
            ("keel", new.keel, old.keel),
            ("chine", new.chine, old.chine),
        ):
            new_list[region] = rebuild((kind, region), old_list[region], new_list[region])
    for index, (old_station, station) in enumerate(zip(old.stations, new.stations)):
        station.upper = rebuild(("upper", index), old_station.upper, station.upper)
        station.lower = rebuild(("lower", index), old_station.lower, station.lower)
    new.link()
    return new


# ----------------------------------------------------------------------
# Operadores do Grupo-1
# ----------------------------------------------------------------------
def set_length(model: HullModel, region: int, value: float) -> HullModel:
    """Alongamento: ``Le``, ``Lm`` ou ``Lr``.

    ``Le`` move só a proa; ``Lm`` mantém a estação 2 e desloca tudo à frente
    dela; ``Lr`` mantém a estação 3 (o espelho) e desloca o resto.
    """
    if value <= 0:
        raise OperatorError("O comprimento da região deve ser positivo.")
    params = model.parameters()
    delta = value - (params.Le, params.Lm, params.Lr)[region]
    new = model.copy()
    new.bow_top[0] += delta
    new.bow_low[0] += delta
    for index in range(region):
        new.stations[index].x += delta
    return _refit(model, new)


def set_beam(model: HullModel, station: int, value: float) -> HullModel:
    """Alargamento: boca ``Be``, ``Bm`` ou ``Br`` (a espessura da quina é mantida).

    O convés e a quina da estação se afastam do eixo de ``ΔB/2``; a quilha
    fica no lugar, de modo que só a linha inferior precisa ser refeita.
    """
    if value <= 0:
        raise OperatorError("A boca deve ser positiva.")
    new = model.copy()
    target = new.stations[station]
    shift = 0.5 * value - target.upper[0, 0]
    if target.lower[0, 0] + shift <= target.lower[3, 0] + 1e-3:
        raise OperatorError(
            "A boca pedida é estreita demais para a quina e a quilha desta estação."
        )
    target.upper[0, 0] += shift
    target.upper[3, 0] += shift
    target.lower[0, 0] += shift
    # A linha superior desliza inteira; só a inferior muda de forma.
    target.upper[1:3, 0] += shift
    return _refit(model, new)


def set_depth(model: HullModel, station: int, value: float) -> HullModel:
    """Aprofundamento: pontal ``De``, ``Dm`` ou ``Dr``.

    A quilha da estação desce (ou sobe); a linha superior, e portanto a
    posição da quina em relação ao convés (``F``), não se altera.
    """
    new = model.copy()
    target = new.stations[station]
    chine_drop = target.upper[0, 1] - target.upper[3, 1]
    if value <= chine_drop + 1e-3:
        raise OperatorError("O pontal deve ser maior que a posição vertical da quina.")
    target.lower[3, 1] = target.upper[0, 1] - value
    return _refit(model, new)


def _y_at_z(curve: np.ndarray, z: float) -> float | None:
    """Coordenada ``y`` em que a curva ``(y, z)`` passa pela cota ``z``."""
    points = bz.evaluate(curve, np.linspace(0.0, 1.0, 400))
    z_values, y_values = points[:, 1], points[:, 0]
    low, high = float(z_values.min()), float(z_values.max())
    if not low - 1e-9 <= z <= high + 1e-9:
        return None
    order = np.argsort(z_values)
    return float(np.interp(z, z_values[order], y_values[order]))


def set_chine_position(model: HullModel, station: int, value: float) -> HullModel:
    """Posição da quina numa estação: ``Fe``, ``Fm`` ou ``Fr``.

    O plano horizontal na nova cota corta a seção; a quina vai para a
    interseção, na linha superior (quina sobe) ou na inferior (quina desce),
    mantendo a espessura ``C``.
    """
    new = model.copy()
    target = new.stations[station]
    depth = target.upper[0, 1] - target.lower[3, 1]
    if not 0 < value < depth - 1e-3:
        raise OperatorError("A quina deve ficar entre o convés e a quilha da estação.")
    z_new = target.upper[0, 1] - value
    half = 0.5 * target.chine_thickness
    if z_new >= target.upper[3, 1]:
        y = _y_at_z(target.upper, z_new)
        center = None if y is None else y - half
    else:
        y = _y_at_z(target.lower, z_new)
        center = None if y is None else y + half
    if center is None or center - half <= target.lower[3, 0] + 1e-6:
        raise OperatorError("Não há quina possível nesta altura da seção.")
    target.upper[3] = (center + half, z_new)
    target.lower[0] = (center - half, z_new)
    return _refit(model, new)


def set_bow_chine_position(model: HullModel, value: float) -> HullModel:
    """Posição da quina na proa ``Fb``: ponto da roda de proa a ``Fb`` do convés."""
    height = model.bow_top[1] - model.bow_low[1]
    if not 0 <= value <= height + 1e-9:
        raise OperatorError("A quina na proa deve ficar sobre a roda de proa (0 ≤ Fb ≤ H).")
    new = model.copy()
    new.chine_depth = value
    return _refit(model, new)


def set_chine_thickness(model: HullModel, station: int, value: float) -> HullModel:
    """Espessura da quina ``Ce``, ``Cm`` ou ``Cr``: externa e interna ``±ΔC/2``."""
    if value < 0:
        raise OperatorError("A espessura da quina não pode ser negativa.")
    new = model.copy()
    target = new.stations[station]
    delta = value - target.chine_thickness
    if target.lower[0, 0] - 0.5 * delta <= target.lower[3, 0] + 1e-3:
        raise OperatorError("Espessura de quina grande demais para esta seção.")
    target.upper[3, 0] += 0.5 * delta
    target.lower[0, 0] -= 0.5 * delta
    return _refit(model, new)


def set_keel_thickness(model: HullModel, value: float) -> HullModel:
    """Espessura da quilha ``K``: é zero na proa e constante a partir da estação 1."""
    if value < 0:
        raise OperatorError("A espessura da quilha não pode ser negativa.")
    new = model.copy()
    for station in new.stations:
        if value >= station.lower[0, 0] - 1e-3:
            raise OperatorError("Espessura de quilha maior que a seção permite.")
        station.lower[3, 0] = value
    return _refit(model, new)


def set_bow_angle(model: HullModel, value: float) -> HullModel:
    """Ângulo de proa ``β``: gira a roda de proa em torno do ponto do convés."""
    if not 1.0 <= value <= 179.0:
        raise OperatorError("O ângulo de proa deve estar entre 1° e 179°.")
    height = model.bow_top[1] - model.bow_low[1]
    new = model.copy()
    new.bow_low = np.array(
        [model.bow_top[0] - height / np.tan(np.radians(value)), model.bow_low[1]]
    )
    return _refit(model, new)


def set_bow_height(model: HullModel, value: float) -> HullModel:
    """Comprimento vertical da roda de proa ``H`` (``β`` e ``Fb`` ficam como estão)."""
    if value <= 0:
        raise OperatorError("O comprimento vertical da roda de proa deve ser positivo.")
    if value < model.chine_depth - 1e-9:
        raise OperatorError(
            "H não pode ser menor que Fb: reduza antes a posição da quina na proa."
        )
    params = model.parameters()
    new = model.copy()
    new.bow_low = np.array(
        [
            model.bow_top[0] - value / np.tan(np.radians(params.beta)),
            model.bow_top[1] - value,
        ]
    )
    return _refit(model, new)


def set_entrance_angle(model: HullModel, value: float) -> HullModel:
    """Ângulo de entrada ``θ``: direção do primeiro segmento da linha de convés."""
    if not 1.0 <= value <= 89.0:
        raise OperatorError("O ângulo de entrada deve estar entre 1° e 89°.")
    slope = np.tan(np.radians(model.parameters().alpha))
    theta = np.radians(value)
    direction = np.array([-np.cos(theta), np.sin(theta), -np.cos(theta) * slope])
    new = model.copy()
    return _refit(
        model, new, forced={("deck", 0)}, directions={("deck", 0): (direction, None)}
    )


def set_sheer_angle(model: HullModel, value: float) -> HullModel:
    """Ângulo de tosamento ``α``: inclina o plano do convés em torno do espelho.

    Os pontos de convés das estações 1 e 2 são projetados na vertical sobre o
    novo plano; o ponto de convés da proa desliza ao longo da roda de proa
    (``β`` constante). As tangentes das linhas de convés passam a pertencer
    ao plano.
    """
    if not -45.0 <= value <= 45.0:
        raise OperatorError("O ângulo de tosamento deve estar entre -45° e 45°.")
    slope = float(np.tan(np.radians(value)))
    new = model.copy()
    reference = new.stations[2]
    x3, z3 = reference.x, reference.upper[0, 1]

    def plane(x: float) -> float:
        return z3 + slope * (x - x3)

    for station in new.stations[:2]:
        station.upper[0, 1] = plane(station.x)

    low = model.bow_low
    along = model.bow_top - model.bow_low
    denominator = along[1] - slope * along[0]
    if abs(denominator) < 1e-9:
        raise OperatorError("O plano do convés é paralelo à roda de proa.")
    factor = (plane(low[0]) - low[1]) / denominator
    if factor <= 0:
        raise OperatorError("O tosamento pedido leva o convés abaixo da roda de proa.")
    chine_point = model.chine_bow_point()
    new.bow_top = low + factor * along
    new.chine_depth = float(new.bow_top[1] - chine_point[2])

    directions: dict[CurveKey, tuple[np.ndarray | None, np.ndarray | None]] = {}
    forced: set[CurveKey] = set()
    for region in range(3):
        start, end = bz.end_directions(model.deck[region])
        directions[("deck", region)] = tuple(
            np.array([d[0], d[1], slope * d[0]]) for d in (start, end)
        )
        forced.add(("deck", region))
    return _refit(model, new, forced=forced, directions=directions)


# ----------------------------------------------------------------------
# Tipo de quina (remover / inserir)
# ----------------------------------------------------------------------
DOUBLE_CHINE = "double"
SINGLE_CHINE = "single"
NO_CHINE = "none"

#: Espessuras usadas ao inserir a quina dupla, se nenhuma for informada.
DEFAULT_CHINE_THICKNESS = (0.19, 0.15, 0.10)


def _angle_between(first: np.ndarray, second: np.ndarray) -> float:
    """Ângulo em graus entre dois vetores (``atan2`` é exato para ângulos pequenos)."""
    first, second = np.atleast_1d(first), np.atleast_1d(second)
    if first.shape[0] == 2:
        cross = first[0] * second[1] - first[1] * second[0]
    else:
        cross = np.linalg.norm(np.cross(first, second))
    return float(np.degrees(np.arctan2(abs(cross), first @ second)))


def chine_type(model: HullModel, angle_tolerance: float = 3.0) -> str:
    """Classifica a quina atual: dupla, simples (aresta viva) ou sem quina."""
    if any(station.chine_thickness > 1e-6 for station in model.stations):
        return DOUBLE_CHINE
    for station in model.stations:
        upper_end = -bz.end_directions(station.upper)[1]
        lower_start = bz.end_directions(station.lower)[0]
        angle = _angle_between(upper_end, lower_start)
        if angle > angle_tolerance:
            return SINGLE_CHINE
    return NO_CHINE


def set_chine_type(
    model: HullModel,
    kind: str,
    thickness: tuple[float, float, float] | None = None,
) -> HullModel:
    """Remove ou insere quinas (chine remover / chine inserter).

    * ``double``: define as espessuras (inserção);
    * ``single``: espessuras nulas, mantendo a aresta viva;
    * ``none``: espessuras nulas e linha superior e inferior com tangentes
      colineares na quina, para que ela deixe de existir (G1).
    """
    if kind == DOUBLE_CHINE:
        values = thickness or DEFAULT_CHINE_THICKNESS
        if min(values) < 0 or max(values) <= 0:
            raise OperatorError("Informe espessuras de quina positivas para a quina dupla.")
    elif kind in (SINGLE_CHINE, NO_CHINE):
        values = (0.0, 0.0, 0.0)
    else:
        raise OperatorError(f"Tipo de quina desconhecido: {kind}")

    result = model
    for index, value in enumerate(values):
        if abs(result.stations[index].chine_thickness - value) > TOLERANCE:
            result = set_chine_thickness(result, index, value)
    if kind != NO_CHINE:
        return result

    new = result.copy()
    directions: dict[CurveKey, tuple[np.ndarray | None, np.ndarray | None]] = {}
    forced: set[CurveKey] = set()
    for index, station in enumerate(new.stations):
        travel = -bz.end_directions(station.upper)[1]
        directions[("lower", index)] = (travel, None)
        forced.add(("lower", index))
        # S3 e S4 coincidem sem espessura; garante a mesma cota e posição.
        station.lower[0] = station.upper[3]
    return _refit(result, new, forced=forced, directions=directions)


# ----------------------------------------------------------------------
# Operadores do Grupo-2
# ----------------------------------------------------------------------
RADIUS_CURVES = {
    "Rek": ("keel", 0),
    "Res1": ("upper", 0),
    "Res2": ("lower", 0),
    "Rms1": ("upper", 1),
    "Rms2": ("lower", 1),
    "Rrs1": ("upper", 2),
    "Rrs2": ("lower", 2),
}


def _curve_of(model: HullModel, key: CurveKey) -> np.ndarray:
    kind, index = key
    if kind == "keel":
        return model.keel[index]
    station = model.stations[index]
    return station.upper if kind == "upper" else station.lower


def _store_curve(model: HullModel, key: CurveKey, curve: np.ndarray) -> None:
    kind, index = key
    if kind == "keel":
        model.keel[index] = curve
    elif kind == "upper":
        model.stations[index].upper = curve
    else:
        model.stations[index].lower = curve


def maximum_radius(model: HullModel, name: str) -> float:
    """Maior raio mínimo de curvatura que o parâmetro ``name`` pode assumir."""
    return bz.maximum_achievable_radius(_curve_of(model, RADIUS_CURVES[name]))


def set_minimum_radius(model: HullModel, name: str, value: float) -> HullModel:
    """Raio mínimo de curvatura de uma curva (``Rek``, ``Res1`` ... ``Rrs2``).

    As alças ``P1`` e ``P2`` se aproximam do ponto crítico até o raio mínimo
    atingir ``value``. Raios acima do máximo da curva são recusados com o
    limite alcançável. ``value ≤ 0`` torna a curva praticamente reta.
    """
    if value < 0:
        raise OperatorError("O raio mínimo de curvatura não pode ser negativo.")
    key = RADIUS_CURVES[name]
    curve = _curve_of(model, key)
    new_curve, maximum = bz.set_minimum_radius(curve, value)
    if value > maximum + 1e-9:
        raise RadiusNotAchievable(name, value, maximum)
    new = model.copy()
    _store_curve(new, key, new_curve)
    new.link()
    return new


CONCAVE = "concave"
CONVEX = "convex"


def station_concavity(model: HullModel, station: int, line: str) -> str:
    """Concavidade de uma linha de estação: ``convex`` (bojo para fora) ou ``concave``."""
    station_data = model.stations[station]
    curve = station_data.upper if line == "upper" else station_data.lower
    chord = curve[3] - curve[0]
    normal = np.array([-chord[1], chord[0]])
    interior = np.array([0.0, 0.5 * (station_data.upper[0, 1] + station_data.lower[3, 1])])
    middle = 0.5 * (curve[0] + curve[3])
    if normal @ (middle - interior) < 0:
        normal = -normal
    bulge = 0.5 * (curve[1] + curve[2]) - middle
    return CONVEX if bulge @ normal >= 0 else CONCAVE


def set_station_concavity(
    model: HullModel, station: int, line: str, concavity: str
) -> HullModel:
    """Espelha os pontos internos da linha em torno da corda para trocar a concavidade."""
    if concavity not in (CONCAVE, CONVEX):
        raise OperatorError(f"Concavidade desconhecida: {concavity}")
    if station_concavity(model, station, line) == concavity:
        return model
    new = model.copy()
    data = new.stations[station]
    curve = (data.upper if line == "upper" else data.lower).copy()
    start, end = curve[0], curve[3]
    axis = bz.unit(end - start)
    for index in (1, 2):
        relative = curve[index] - start
        along = (relative @ axis) * axis
        curve[index] = start + along - (relative - along)
    if line == "upper":
        data.upper = curve
    else:
        data.lower = curve
    new.link()
    return new


# ----------------------------------------------------------------------
# Aplicação por parâmetros
# ----------------------------------------------------------------------
def _setter(name: str):
    simple = {
        "Le": lambda m, v: set_length(m, 0, v),
        "Lm": lambda m, v: set_length(m, 1, v),
        "Lr": lambda m, v: set_length(m, 2, v),
        "Be": lambda m, v: set_beam(m, 0, v),
        "Bm": lambda m, v: set_beam(m, 1, v),
        "Br": lambda m, v: set_beam(m, 2, v),
        "De": lambda m, v: set_depth(m, 0, v),
        "Dm": lambda m, v: set_depth(m, 1, v),
        "Dr": lambda m, v: set_depth(m, 2, v),
        "Fe": lambda m, v: set_chine_position(m, 0, v),
        "Fm": lambda m, v: set_chine_position(m, 1, v),
        "Fr": lambda m, v: set_chine_position(m, 2, v),
        "Fb": set_bow_chine_position,
        "Ce": lambda m, v: set_chine_thickness(m, 0, v),
        "Cm": lambda m, v: set_chine_thickness(m, 1, v),
        "Cr": lambda m, v: set_chine_thickness(m, 2, v),
        "K": set_keel_thickness,
        "H": set_bow_height,
        "beta": set_bow_angle,
        "theta": set_entrance_angle,
        "alpha": set_sheer_angle,
    }
    if name in simple:
        return simple[name]
    if name in RADIUS_CURVES:
        return lambda m, v, n=name: set_minimum_radius(m, n, v)
    raise KeyError(name)


#: Ordem de aplicação: dimensões, quinas, proa e, por fim, as curvaturas.
APPLY_ORDER = (
    "Le", "Lm", "Lr",
    "Be", "Bm", "Br",
    "De", "Dm", "Dr",
    "Ce", "Cm", "Cr",
    "Fe", "Fm", "Fr",
    "K",
    "Fb", "H", "beta",
    "theta", "alpha",
    "Rek", "Res1", "Res2", "Rms1", "Rms2", "Rrs1", "Rrs2",
)

#: Parâmetros do Grupo-1 (operadores iterativos) e do Grupo-2.
GROUP_1 = APPLY_ORDER[:21]
GROUP_2 = APPLY_ORDER[21:]


def apply_parameters(model: HullModel, targets: dict[str, float]) -> HullModel:
    """Aplica os operadores correspondentes aos parâmetros que mudaram.

    ``targets`` mapeia nomes de parâmetro a valores desejados. Só são aplicados
    os que diferem do valor atual: sem alteração, o casco volta como está.
    """
    unknown = set(targets) - set(APPLY_ORDER)
    if unknown:
        raise OperatorError(f"Parâmetros desconhecidos: {', '.join(sorted(unknown))}")
    result = model
    order = list(APPLY_ORDER)

    def swap(first: str, second: str) -> None:
        i, j = order.index(first), order.index(second)
        order[i], order[j] = order[j], order[i]

    current = result.parameters()
    # Uma quina na proa mais baixa que a roda de proa atual exige alongar H antes.
    if "Fb" in targets and "H" in targets and targets["Fb"] > current.H:
        swap("Fb", "H")
    # Um pontal menor que a posição atual da quina exige baixar a quina antes.
    for depth, drop in (("De", "Fe"), ("Dm", "Fm"), ("Dr", "Fr")):
        if depth in targets and drop in targets and targets[depth] <= getattr(current, drop) + 2e-3:
            swap(depth, drop)
    for name in order:
        if name not in targets:
            continue
        current = getattr(result.parameters(), name)
        wanted = targets[name]
        if np.isfinite(current) and abs(wanted - current) <= TOLERANCE:
            continue
        if not np.isfinite(current) and not np.isfinite(wanted):
            continue
        result = _setter(name)(result, wanted)
    return result


# ----------------------------------------------------------------------
# Verificações de qualidade
# ----------------------------------------------------------------------
def curve_similarity(before: HullModel, after: HullModel) -> dict[str, float]:
    """Valor de ``F`` (similaridade das curvaturas) de cada curva longitudinal."""
    result: dict[str, float] = {}
    for (name, old), new in zip(before.curvature_curves().items(), after.curvature_curves().values()):
        reference = bz.curvature_distribution(old)
        candidate = bz.curvature_distribution(new)[None, :]
        result[name] = float(bz.similarity(reference, candidate)[0])
    return result


def continuity_report(model: HullModel) -> dict[str, float]:
    """Desvio angular (graus) das tangentes nas estações: 0 indica G1."""
    report: dict[str, float] = {}
    for kind, curves in (("convés", model.deck), ("quina", model.chine), ("quilha", model.keel)):
        for index in range(2):
            fore_end = -bz.end_directions(curves[index])[1]
            aft_start = bz.end_directions(curves[index + 1])[0]
            angle = _angle_between(fore_end, aft_start)
            report[f"{kind} · estação {index + 1}"] = float(angle)
    return report
