"""Amostragem de modelos CAD com S-TLBO (capítulo 4 da referência).

O S-TLBO estende o *Teaching-Learning Based Optimization* para amostragem de
projetos. A população é dividida em ``N`` subpopulações de ``s`` alunos; o
professor de cada subpopulação é um dos ``N`` projetos amostrados. O custo da
equação 4.15 reúne três termos sobre os professores ``T``:

* ``U1`` — energia potencial de Audze-Eglais (4.6), que espalha os projetos
  pelo espaço (*space-filling*);
* ``U2`` — penalidade de colapso (4.8-4.11): conta as dimensões em que dois
  projetos caem no mesmo nível, favorecendo hipercubos latinos;
* ``U3`` — penalidade estática (4.13-4.14), que cobra cada restrição violada.

``Ū(T) = U1 + α·U2 + β·U3``. Os professores iniciais são escolhidos de forma
gulosa; cada subpopulação passa pelas fases de ensino (4.1) e de aprendizagem
(4.2-4.3) com os professores das demais fixos, e o processo termina quando a
variação do custo entre duas iterações consecutivas se torna desprezível.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from app.models.attributes import (
    ATTRIBUTE_THRESHOLD,
    ATTRIBUTES_BY_KEY,
    DESIGN_VARIABLES,
    FEATURE_RANGES,
    HullDesign,
    evaluate_attributes,
    standardize_values,
)

#: Uma restrição é uma função do projeto (nome → valor) que diz se ela é satisfeita.
Constraint = Callable[[Mapping[str, float]], bool]

#: Pesos usados nos experimentos da tese: α = 100 (colapso) e β = 1000 (restrições).
DEFAULT_ALPHA = 100.0
DEFAULT_BETA = 1000.0


@dataclass(frozen=True)
class DesignSpace:
    """Espaço de projeto: variáveis e seus limites inferior e superior."""

    names: tuple[str, ...]
    lower: np.ndarray
    upper: np.ndarray

    @classmethod
    def from_bounds(cls, bounds: Mapping[str, tuple[float, float]]) -> "DesignSpace":
        names = tuple(bounds)
        return cls(
            names,
            np.array([bounds[name][0] for name in names], dtype=float),
            np.array([bounds[name][1] for name in names], dtype=float),
        )

    @property
    def dimensions(self) -> int:
        return len(self.names)

    def to_values(self, unit: np.ndarray) -> np.ndarray:
        """Converte coordenadas escaladas (0..1) em valores reais."""
        return self.lower + np.asarray(unit) * (self.upper - self.lower)

    def as_dict(self, unit: np.ndarray) -> dict[str, float]:
        return dict(zip(self.names, self.to_values(unit).tolist()))


#: Espaço do casco (Tabela 4.1).
YACHT_HULL_SPACE = DesignSpace.from_bounds(
    {name: (FEATURE_RANGES[name].minimum, FEATURE_RANGES[name].maximum) for name in DESIGN_VARIABLES}
)

#: Espaço da taça de vinho (Tabela 4.2), em milímetros.
WINE_GLASS_SPACE = DesignSpace.from_bounds(
    {
        "Hu": (40.0, 120.0),
        "Hl": (90.0, 170.0),
        "Wu": (130.0, 170.0),
        "Wm": (15.0, 160.0),
        "Wl": (15.0, 65.0),
    }
)

WINE_GLASS_CONSTRAINTS: tuple[Constraint, ...] = (
    lambda d: d["Hl"] >= d["Hu"],
    lambda d: d["Wm"] <= d["Wu"] / 2.0,
    lambda d: d["Wm"] <= d["Wl"],
)

#: Restrições geométricas das preferências dos três participantes (Tabela 4.1).
#: A tabela traz "110 ≤ β ≤ 80" para o participante 3, que é impossível; foi lida
#: como 80 ≤ β ≤ 120, coerente com a regra φ8 (β ≥ 110 admitido).
PARTICIPANT_CONSTRAINTS: dict[str, tuple[Constraint, ...]] = {
    "Participante 1": (
        lambda d: d["Lr"] >= 2.0 * d["Lm"] / 3.0,
        lambda d: d["Be"] >= d["Bm"] / 2.0,
        lambda d: d["Bm"] >= d["Br"],
        lambda d: d["De"] >= d["Dm"] >= d["Dr"],
        lambda d: 50.0 <= d["beta"] <= 120.0,
    ),
    "Participante 2": (
        lambda d: -1.2 <= d["Le"] - d["Lm"] <= 2.4,
        lambda d: d["Lr"] >= d["Lm"] / 2.0,
        lambda d: 0.0 <= d["Be"] - d["Bm"] <= 2.4,
        lambda d: d["Bm"] >= d["Br"],
        lambda d: 0.0 <= d["De"] - d["Dm"] <= 0.7,
        lambda d: d["Dm"] >= d["Dr"],
        lambda d: 40.0 <= d["beta"] <= 70.0,
        lambda d: 45.0 <= d["theta"] <= 70.0,
    ),
    "Participante 3": (
        lambda d: -2.4 <= d["Le"] - d["Lm"] <= 3.6,
        lambda d: d["Lm"] >= d["Lr"] >= d["Lm"] / 2.0,
        lambda d: -1.8 <= d["Be"] - d["Bm"] <= 3.0,
        lambda d: d["Bm"] >= d["Br"],
        lambda d: 0.0 <= d["De"] - d["Dm"] <= 0.7,
        lambda d: d["Dm"] >= d["Dr"],
        lambda d: 80.0 <= d["beta"] <= 120.0,
        lambda d: d["theta"] >= 55.0 if d["beta"] >= 110.0 else True,
    ),
}


# ----------------------------------------------------------------------
# Termos do custo
# ----------------------------------------------------------------------
def potential_energy(unit_designs: np.ndarray) -> float:
    """``U1`` (equação 4.6): Σ 1 / ‖x̄ₚ − x̄_q‖² sobre todos os pares."""
    count = len(unit_designs)
    energy = 0.0
    for p in range(count - 1):
        squared = ((unit_designs[p + 1 :] - unit_designs[p]) ** 2).sum(axis=1)
        energy += float((1.0 / np.maximum(squared, 1e-12)).sum())
    return energy


def levels(unit_designs: np.ndarray, count: int) -> np.ndarray:
    """Nível inteiro (1..N) de cada coordenada, como na equação 4.11."""
    return np.clip(np.floor(np.asarray(unit_designs) * count), 0, count - 1).astype(int) + 1


def collapse_penalty(unit_designs: np.ndarray) -> int:
    """``U2`` (equações 4.8-4.10): coordenadas que pares de projetos compartilham."""
    count = len(unit_designs)
    grid = levels(unit_designs, count)
    total = 0
    for p in range(count - 1):
        total += int((grid[p + 1 :] == grid[p]).sum())
    return total


def collapsing_designs(unit_designs: np.ndarray) -> int:
    """Quantidade de projetos que dividem ao menos uma coordenada com outro."""
    count = len(unit_designs)
    grid = levels(unit_designs, count)
    collapsing = np.zeros(count, dtype=bool)
    for p in range(count):
        same = (grid == grid[p]).any(axis=1)
        same[p] = False
        collapsing[p] = same.any()
    return int(collapsing.sum())


def maximin_distance(unit_designs: np.ndarray) -> float:
    """Menor distância entre dois projetos (equação 4.18); quanto maior, melhor."""
    count = len(unit_designs)
    best = np.inf
    for p in range(count - 1):
        distances = np.sqrt(((unit_designs[p + 1 :] - unit_designs[p]) ** 2).sum(axis=1))
        best = min(best, float(distances.min()))
    return best


@dataclass(frozen=True)
class SamplingResult:
    """Resultado de uma amostragem."""

    unit_designs: np.ndarray
    designs: list[dict[str, float]]
    violations: list[int]
    cost: float
    cost_history: list[float]
    iterations: int
    collapse: int = 0
    """Pares de coordenadas ainda em colapso após a etapa de reparo (U₂ > 0)."""

    @property
    def feasible(self) -> list[bool]:
        return [count == 0 for count in self.violations]


class STLBO:
    """Amostrador S-TLBO para espaços restritos ou irrestritos."""

    def __init__(
        self,
        space: DesignSpace,
        constraints: Sequence[Constraint] = (),
        population_size: int = 30,
        alpha: float = DEFAULT_ALPHA,
        beta: float = DEFAULT_BETA,
        tolerance: float = 1e-6,
        max_iterations: int = 400,
        patience: int = 12,
        seed: int | None = None,
        batch_violations: Callable[[np.ndarray], np.ndarray] | None = None,
        batch_degree: Callable[[np.ndarray], np.ndarray] | None = None,
        degree_weight: float = 0.1,
        repair: bool = True,
    ) -> None:
        if population_size < 2:
            raise ValueError("Cada subpopulação precisa de pelo menos 2 alunos.")
        if max_iterations < 1:
            raise ValueError("É necessária pelo menos 1 iteração.")
        self.space = space
        self.constraints = tuple(constraints)
        self.population_size = population_size
        self.alpha = alpha
        self.beta = beta
        self.tolerance = tolerance
        self.max_iterations = max_iterations
        self.patience = patience
        self._rng = np.random.default_rng(seed)
        self._batch_violations = batch_violations
        self._batch_degree = batch_degree
        self.degree_weight = degree_weight
        self.repair = repair

    # ------------------------------------------------------------------
    def violations_batch(self, units: np.ndarray) -> np.ndarray:
        """Restrições violadas por projeto (soma de ``f2``, equação 4.14)."""
        units = np.atleast_2d(units)
        total = np.zeros(len(units), dtype=int)
        if self._batch_violations is not None:
            total += np.asarray(self._batch_violations(units), dtype=int)
        if self.constraints:
            for index, unit in enumerate(units):
                values = self.space.as_dict(unit)
                total[index] += sum(
                    not bool(constraint(values)) for constraint in self.constraints
                )
        return total

    def penalty_batch(self, units: np.ndarray) -> np.ndarray:
        """Penalidade estática ``β·U3`` de cada projeto.

        Além da contagem de restrições violadas (equação 4.14), soma uma fração
        pequena do *grau* da violação, quando ``batch_degree`` é informado. Como a
        contagem é plana, todos os projetos inviáveis custam o mesmo e os alunos
        não têm para onde seguir; o grau só desempata entre eles e nunca supera
        uma restrição a mais violada.
        """
        units = np.atleast_2d(units)
        penalty = self.beta * self.violations_batch(units).astype(float)
        if self._batch_degree is not None:
            degree = np.asarray(self._batch_degree(units), dtype=float)
            penalty += self.beta * self.degree_weight * np.minimum(degree, 1.0)
        return penalty

    def violations(self, unit: np.ndarray) -> int:
        return int(self.violations_batch(unit)[0])

    def _contributions(
        self, candidates: np.ndarray, others: np.ndarray, count: int
    ) -> np.ndarray:
        """Parte do custo ``Ū(T)`` que depende de cada candidato, dados os demais.

        Trocar um professor só altera os termos de pares que o envolvem e a
        sua própria penalidade; comparar candidatos por esta parcela equivale
        a comparar o custo total.
        """
        candidates = np.atleast_2d(candidates)
        penalty = self.penalty_batch(candidates)
        if len(others) == 0:
            return penalty
        squared = ((candidates[:, None, :] - others[None, :, :]) ** 2).sum(axis=2)
        energy = (1.0 / np.maximum(squared, 1e-12)).sum(axis=1)
        collapse = (
            levels(candidates, count)[:, None, :] == levels(others, count)[None, :, :]
        ).sum(axis=(1, 2))
        return energy + self.alpha * collapse + penalty

    def _contribution(
        self, candidate: np.ndarray, others: np.ndarray, count: int
    ) -> float:
        return float(self._contributions(candidate, others, count)[0])

    def total_cost(self, unit_designs: np.ndarray) -> float:
        """Custo ``Ū(T)`` completo (equação 4.15)."""
        return (
            potential_energy(unit_designs)
            + self.alpha * collapse_penalty(unit_designs)
            + float(self.penalty_batch(unit_designs).sum())
        )

    # ------------------------------------------------------------------
    def sample(
        self,
        count: int,
        progress: Callable[[int, float], bool | None] | None = None,
    ) -> SamplingResult:
        """Amostra ``count`` projetos.

        ``progress(iteração, custo)`` é chamado a cada iteração; se devolver
        ``False``, a amostragem é interrompida e o resultado parcial é devolvido.

        A parada ocorre quando a variação relativa do custo fica abaixo de
        ``tolerance`` por ``patience`` iterações seguidas. A tese usa duas; como
        as penalidades ``α`` e ``β`` são discretas, o custo pode ficar parado
        por algumas iterações antes de uma nova melhora, e uma paciência maior
        evita encerrar cedo demais.
        """
        if count < 1:
            raise ValueError("A quantidade de projetos deve ser positiva.")
        rng = self._rng
        dimensions = self.space.dimensions
        s = self.population_size
        populations = rng.random((count, s, dimensions))
        teachers = self._initial_teachers(populations, count)

        history = [self.total_cost(teachers)]
        stable = 0
        iterations = 0
        keep_going: bool | None = None
        for iterations in range(1, self.max_iterations + 1):
            for g in range(count):
                self._improve_subpopulation(populations[g], teachers, g, count)
            cost = self.total_cost(teachers)
            history.append(cost)
            keep_going = progress(iterations, cost) if progress is not None else None
            if keep_going is False:
                break
            change = abs(history[-2] - history[-1])
            stable = stable + 1 if change <= self.tolerance * max(1.0, abs(cost)) else 0
            if stable >= self.patience:
                break

        if self.repair and keep_going is not False:
            self._repair_collapse(teachers, count)
            history.append(self.total_cost(teachers))

        final_collapse = int(collapse_penalty(teachers))
        if self.repair and final_collapse > 0:
            warnings.warn(
                f"S-TLBO: {final_collapse} par(es) de coordenadas ainda em colapso "
                "após a etapa de reparo. Com restrições de atributo muito estreitas o "
                "hipercubo latino não consegue cobrir todo o espaço viável. "
                "Experimente relaxar os atributos ou aumentar N.",
                stacklevel=3,
            )

        designs = [self.space.as_dict(unit) for unit in teachers]
        return SamplingResult(
            unit_designs=teachers.copy(),
            designs=designs,
            violations=[int(v) for v in self.violations_batch(teachers)],
            cost=history[-1],
            cost_history=history,
            iterations=iterations,
            collapse=final_collapse,
        )

    # ------------------------------------------------------------------
    def _repair_collapse(
        self, teachers: np.ndarray, count: int, sweeps: int = 12, tries: int = 3
    ) -> None:
        """Desfaz o colapso que a busca principal deixou (etapa final).

        As penalidades ``α`` e ``β`` são discretas, e a busca por TLBO quase
        nunca acerta sozinha a permutação exata de níveis do hipercubo latino.
        Cada coordenada que divide um nível com outro projeto é movida para um
        nível livre do mesmo eixo, desde que o custo ``Ū`` diminua: o movimento
        nunca quebra uma restrição que já era satisfeita.
        """
        rng = self._rng
        dimensions = teachers.shape[1]
        for _ in range(sweeps):
            changed = False
            for axis in range(dimensions):
                for index in rng.permutation(count):
                    grid = levels(teachers, count)[:, axis]
                    shared = int((grid == grid[index]).sum())
                    if shared < 2:
                        continue
                    free = np.setdiff1d(np.arange(1, count + 1), grid)
                    if len(free) == 0:
                        continue
                    fractions = np.concatenate(
                        ([0.5], rng.uniform(0.05, 0.95, size=tries))
                    )
                    positions = ((free[:, None] - 1 + fractions[None, :]) / count).ravel()
                    candidates = np.repeat(teachers[index][None, :], len(positions), axis=0)
                    candidates[:, axis] = positions
                    others = np.delete(teachers, index, axis=0)
                    costs = self._contributions(candidates, others, count)
                    best = int(np.argmin(costs))
                    current = self._contribution(teachers[index], others, count)
                    if costs[best] < current:
                        teachers[index] = candidates[best]
                        changed = True
            if not changed:
                break

    # ------------------------------------------------------------------
    def _initial_teachers(self, populations: np.ndarray, count: int) -> np.ndarray:
        """Seleção gulosa dos ``N`` professores iniciais (seção 4.3.1).

        Os dois primeiros professores são o melhor par entre as duas primeiras
        subpopulações; cada um dos seguintes é o melhor aluno dado o que já
        foi escolhido.
        """
        teachers = np.empty((count, populations.shape[2]))
        if count == 1:
            costs = self._contributions(populations[0], teachers[:0], 1)
            teachers[0] = populations[0][int(np.argmin(costs))]
            return teachers

        first, second = populations[0], populations[1]
        penalties_first = self.penalty_batch(first)
        penalties_second = self.penalty_batch(second)
        squared = ((first[:, None, :] - second[None, :, :]) ** 2).sum(axis=2)
        grid_a = levels(first, count)
        grid_b = levels(second, count)
        collapse = (grid_a[:, None, :] == grid_b[None, :, :]).sum(axis=2)
        pair_cost = (
            1.0 / np.maximum(squared, 1e-12)
            + self.alpha * collapse
            + penalties_first[:, None]
            + penalties_second[None, :]
        )
        a, b = np.unravel_index(int(np.argmin(pair_cost)), pair_cost.shape)
        teachers[0], teachers[1] = first[a], second[b]
        for g in range(2, count):
            others = teachers[:g]
            costs = self._contributions(populations[g], others, count)
            teachers[g] = populations[g][int(np.argmin(costs))]
        return teachers

    def _improve_subpopulation(
        self, population: np.ndarray, teachers: np.ndarray, g: int, count: int
    ) -> None:
        """Fases de ensino e de aprendizagem de uma subpopulação."""
        rng = self._rng
        s, dimensions = population.shape
        others = np.delete(teachers, g, axis=0)

        costs = self._contributions(population, others, count)
        teacher = population[int(np.argmin(costs))].copy()

        # Fase de ensino (4.1): os alunos se aproximam do professor.
        mean = population.mean(axis=0)
        teaching_factor = int(rng.integers(1, 3))
        candidates = np.clip(
            population + rng.random((s, dimensions)) * (teacher - teaching_factor * mean),
            0.0,
            1.0,
        )
        candidate_costs = self._contributions(candidates, others, count)
        better = candidate_costs < costs
        population[better] = candidates[better]
        costs[better] = candidate_costs[better]

        # Fase de aprendizagem (4.2 e 4.3): cada aluno aprende com um colega.
        for k in range(s):
            partner = int(rng.integers(s - 1))
            partner += partner >= k
            if np.array_equal(population[k], population[partner]):
                continue
            if costs[k] < costs[partner]:
                direction = population[k] - population[partner]
            else:
                direction = population[partner] - population[k]
            candidate = np.clip(
                population[k] + rng.random(dimensions) * direction, 0.0, 1.0
            )
            candidate_cost = self._contribution(candidate, others, count)
            if candidate_cost < costs[k]:
                population[k], costs[k] = candidate, candidate_cost

        teachers[g] = population[int(np.argmin(costs))]


# ----------------------------------------------------------------------
# Amostragem de cascos por atributo
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class SampledDesign:
    """Projeto amostrado com a avaliação de todos os atributos."""

    design: HullDesign
    scores: dict[str, float]
    feasible: bool
    violated: int = 0


def attribute_constraint(key: str) -> Constraint:
    """Restrição ``Y_atributo > 0,5`` (Figura 5.6) como função do projeto."""
    model = ATTRIBUTES_BY_KEY[key]

    def satisfied(values: Mapping[str, float]) -> bool:
        return model.evaluate(HullDesign.from_dict(values)) > ATTRIBUTE_THRESHOLD

    return satisfied


@dataclass
class AttributeSampler:
    """Gera cascos que expressam os atributos escolhidos via S-TLBO."""

    population_size: int = 30
    alpha: float = DEFAULT_ALPHA
    beta: float = DEFAULT_BETA
    max_iterations: int = 400
    seed: int | None = None
    last_result: SamplingResult | None = field(default=None, init=False, repr=False)

    def sample(
        self,
        attributes: Sequence[str],
        count: int,
        extra_constraints: Sequence[Constraint] = (),
        progress: Callable[[int, float], bool | None] | None = None,
    ) -> list[SampledDesign]:
        """Amostra ``count`` cascos que expressem todos os ``attributes``.

        ``extra_constraints`` acrescenta restrições geométricas (por exemplo,
        as preferências de um participante, em ``PARTICIPANT_CONSTRAINTS``).
        """
        unknown = [key for key in attributes if key not in ATTRIBUTES_BY_KEY]
        if unknown:
            raise ValueError(f"Atributos desconhecidos: {', '.join(unknown)}")
        if not attributes:
            raise ValueError("Selecione pelo menos um atributo.")
        models = [ATTRIBUTES_BY_KEY[key] for key in attributes]

        def attribute_violations(units: np.ndarray) -> np.ndarray:
            values = YACHT_HULL_SPACE.lower + units * (
                YACHT_HULL_SPACE.upper - YACHT_HULL_SPACE.lower
            )
            standardized = standardize_values(values)
            return sum(
                (model.evaluate_matrix(standardized) <= ATTRIBUTE_THRESHOLD).astype(int)
                for model in models
            )

        def attribute_degree(units: np.ndarray) -> np.ndarray:
            values = YACHT_HULL_SPACE.lower + units * (
                YACHT_HULL_SPACE.upper - YACHT_HULL_SPACE.lower
            )
            standardized = standardize_values(values)
            return sum(
                np.maximum(0.0, ATTRIBUTE_THRESHOLD - model.evaluate_matrix(standardized))
                for model in models
            )

        sampler = STLBO(
            YACHT_HULL_SPACE,
            tuple(extra_constraints),
            batch_violations=attribute_violations,
            batch_degree=attribute_degree,
            population_size=self.population_size,
            alpha=self.alpha,
            beta=self.beta,
            max_iterations=self.max_iterations,
            seed=self.seed,
        )
        result = sampler.sample(count, progress)
        self.last_result = result
        samples = []
        for values, violated in zip(result.designs, result.violations):
            design = HullDesign.from_dict(values)
            samples.append(
                SampledDesign(
                    design=design,
                    scores=evaluate_attributes(design),
                    feasible=violated == 0,
                    violated=violated,
                )
            )
        return samples
