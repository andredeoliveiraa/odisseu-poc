"""Validação das restrições matemáticas dos operadores de forma."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.hull_generator import HullGenerator


@dataclass(frozen=True)
class ConstraintResult:
    """Resultado explícito de uma validação de restrição."""

    valid: bool
    maximum_radius: float
    message: str = ""


class HullConstraintValidator:
    """Calcula limites físicos para os parâmetros do Grupo 2."""

    def maximum_achievable_radius(self, generator: HullGenerator) -> float:
        """Estima o maior raio permitido pela escala longitudinal atual.

        Para esta primeira aproximação, o limite é baseado no comprimento da
        seção média e no calado: uma curva que exceda essa escala deixa de ser
        representável dentro do casco atual.
        """
        return max(0.01, 0.5 * generator.midship_length + generator.draft)

    def validate(
        self,
        generator: HullGenerator,
        concavity: float,
        minimum_radius: float,
    ) -> ConstraintResult:
        """Valida concavidade e raio mínimo antes de gerar a malha."""
        if not 0.0 <= concavity <= 1.0:
            return ConstraintResult(
                False,
                self.maximum_achievable_radius(generator),
                "A concavidade das estações deve estar entre 0 e 1.",
            )
        if minimum_radius <= 0:
            return ConstraintResult(
                False,
                self.maximum_achievable_radius(generator),
                "O raio mínimo deve ser maior que zero.",
            )

        maximum_radius = self.maximum_achievable_radius(generator)
        if minimum_radius > maximum_radius:
            return ConstraintResult(
                False,
                maximum_radius,
                (
                    "Informe outro valor. O raio mínimo excedeu o limite "
                    f"estimado de {maximum_radius:.2f} m para este casco."
                ),
            )
        return ConstraintResult(True, maximum_radius)
