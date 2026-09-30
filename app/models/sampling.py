"""Amostragem de cascos por atributo com S-TLBO (seção 5.2 da referência).

O S-TLBO estende o Teaching-Learning Based Optimization para amostragem de
projetos: cada amostra é o *professor* de uma subpopulação independente.
Os alunos de cada subpopulação melhoram pelas fases de ensino e de
aprendizagem, favorecendo projetos que

* satisfazem as restrições (atributos escolhidos com Y > 0,5 e limites
  geométricos do gerador), por meio de uma penalidade;
* preenchem o espaço (maior distância mínima aos outros professores);
* não colapsam (diferem dos outros professores em cada eixo individual).

Ao final, os professores das subpopulações são os projetos amostrados.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.models.attributes import (
    ATTRIBUTE_THRESHOLD,
    ATTRIBUTES_BY_KEY,
    FEATURE_RANGES,
    HullDesign,
    design_features,
    evaluate_attributes,
)

DEFAULT_MINIMUM_RADIUS = 2.0
"""Raio mínimo usado pelos perfis e validado para cada amostra."""


@dataclass(frozen=True)
class DesignBounds:
    """Limites das variáveis de projeto amostradas.

    A seção média é amostrada como fração do comprimento total, o que
    garante por construção que ela nunca excede o comprimento.
    """

    total_length: tuple[float, float] = (6.0, 24.0)
    midship_ratio: tuple[float, float] = (0.3, 0.75)
    beam: tuple[float, float] = (2.0, 7.0)
    draft: tuple[float, float] = (0.8, 3.0)
    bow_angle: tuple[float, float] = (5.0, 60.0)
    concavity: tuple[float, float] = (0.0, 1.0)

    def as_array(self) -> np.ndarray:
        return np.array(
            [
                self.total_length,
                self.midship_ratio,
                self.beam,
                self.draft,
                self.bow_angle,
                self.concavity,
            ],
            dtype=float,
        )


@dataclass(frozen=True)
class SampledDesign:
    """Projeto amostrado com a avaliação de todos os atributos."""

    design: HullDesign
    scores: dict[str, float]
    feasible: bool


class AttributeSampler:
    """Gera cascos que expressam os atributos escolhidos via S-TLBO."""

    def __init__(
        self,
        bounds: DesignBounds | None = None,
        learners_per_population: int = 10,
        iterations: int = 40,
        margin: float = 0.02,
        seed: int | None = None,
    ) -> None:
        if learners_per_population < 2:
            raise ValueError("Cada subpopulação precisa de pelo menos 2 alunos.")
        if iterations < 1:
            raise ValueError("São necessárias pelo menos 1 iteração.")
        self._limits = (bounds or DesignBounds()).as_array()
        self.learners_per_population = learners_per_population
        self.iterations = iterations
        self.margin = margin
        self._rng = np.random.default_rng(seed)

    def _to_design(self, unit: np.ndarray) -> HullDesign:
        low, high = self._limits[:, 0], self._limits[:, 1]
        length, ratio, beam, draft, bow, concavity = low + unit * (high - low)
        return HullDesign(
            total_length=float(length),
            midship_length=float(ratio * length),
            beam=float(beam),
            draft=float(draft),
            bow_angle=float(bow),
            concavity=float(concavity),
        )

    def _violation(self, design: HullDesign, attributes: Sequence[str]) -> float:
        """Soma das violações; zero significa projeto viável."""
        scores = evaluate_attributes(design)
        target = ATTRIBUTE_THRESHOLD + self.margin
        violation = sum(max(0.0, target - scores[key]) for key in attributes)

        # As proporções precisam permanecer na faixa em que os modelos de
        # atributo foram padronizados, senão a extrapolação perde sentido.
        features = design_features(design)
        for name in ("slenderness", "beam_draft"):
            feature_range = FEATURE_RANGES[name]
            span = feature_range.maximum - feature_range.minimum
            violation += max(0.0, feature_range.minimum - features[name]) / span
            violation += max(0.0, features[name] - feature_range.maximum) / span

        # Mesmo limite de raio aplicado por HullConstraintValidator, com folga
        # para o arredondamento de duas casas decimais do formulário.
        maximum_radius = 0.5 * design.midship_length + design.draft
        violation += max(0.0, DEFAULT_MINIMUM_RADIUS + 0.05 - maximum_radius)
        return violation

    def _cost(
        self,
        unit: np.ndarray,
        others: np.ndarray,
        attributes: Sequence[str],
    ) -> float:
        """Custo a minimizar: penalidade de restrições menos a dispersão."""
        penalty = 100.0 * self._violation(self._to_design(unit), attributes)
        if len(others) == 0:
            return penalty
        differences = np.abs(others - unit)
        space_filling = float(np.sqrt((differences**2).sum(axis=1)).min())
        non_collapsing = float(differences.min())
        return penalty - space_filling - 0.5 * non_collapsing

    def sample(self, attributes: Sequence[str], count: int) -> list[SampledDesign]:
        """Amostra ``count`` cascos que expressem todos os ``attributes``."""
        unknown = [key for key in attributes if key not in ATTRIBUTES_BY_KEY]
        if unknown:
            raise ValueError(f"Atributos desconhecidos: {', '.join(unknown)}")
        if not attributes:
            raise ValueError("Selecione pelo menos um atributo.")
        if count < 1:
            raise ValueError("A quantidade de projetos deve ser positiva.")

        dimensions = len(self._limits)
        populations = self._rng.random((count, self.learners_per_population, dimensions))
        costs = np.empty((count, self.learners_per_population))
        teachers = populations[:, 0, :].copy()

        def others_of(index: int) -> np.ndarray:
            return np.delete(teachers, index, axis=0)

        for index in range(count):
            others = others_of(index)
            costs[index] = [
                self._cost(learner, others, attributes) for learner in populations[index]
            ]
            teachers[index] = populations[index, int(costs[index].argmin())]

        for _ in range(self.iterations):
            for index in range(count):
                population = populations[index]
                population_costs = costs[index]
                others = others_of(index)
                # Custos dependem dos outros professores, que mudam a cada passo.
                population_costs[:] = [
                    self._cost(learner, others, attributes) for learner in population
                ]
                teacher = population[int(population_costs.argmin())]

                # Fase de ensino: aproxima os alunos do professor.
                teaching_factor = self._rng.integers(1, 3)
                mean = population.mean(axis=0)
                for learner_index in range(self.learners_per_population):
                    step = self._rng.random(dimensions) * (teacher - teaching_factor * mean)
                    self._try_move(
                        population, population_costs, learner_index, step, others, attributes
                    )

                # Fase de aprendizagem: cada aluno aprende com um colega.
                for learner_index in range(self.learners_per_population):
                    partner = self._rng.integers(self.learners_per_population - 1)
                    partner += partner >= learner_index
                    direction = population[partner] - population[learner_index]
                    if population_costs[partner] > population_costs[learner_index]:
                        direction = -direction
                    step = self._rng.random(dimensions) * direction
                    self._try_move(
                        population, population_costs, learner_index, step, others, attributes
                    )

                teachers[index] = population[int(population_costs.argmin())]

        results = []
        for unit in teachers:
            design = self._to_design(unit)
            results.append(
                SampledDesign(
                    design=design,
                    scores=evaluate_attributes(design),
                    feasible=self._violation(design, attributes) == 0.0,
                )
            )
        return results

    def _try_move(
        self,
        population: np.ndarray,
        costs: np.ndarray,
        learner_index: int,
        step: np.ndarray,
        others: np.ndarray,
        attributes: Sequence[str],
    ) -> None:
        """Aceita o novo aluno apenas quando ele melhora o custo (seleção gulosa)."""
        candidate = np.clip(population[learner_index] + step, 0.0, 1.0)
        candidate_cost = self._cost(candidate, others, attributes)
        if candidate_cost < costs[learner_index]:
            population[learner_index] = candidate
            costs[learner_index] = candidate_cost
