"""Validação das restrições matemáticas dos operadores de forma."""

from __future__ import annotations

from dataclasses import dataclass

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
        """Maior raio de quilha admissível na seção mestra do casco.

        O limite é geométrico, e não uma estimativa: acima da meia-boca o arco
        de bojo faria a seção ultrapassar a boca declarada.
        """
        return max(0.01, generator.maximum_keel_radius())

    def validate(
        self,
        generator: HullGenerator,
        concavity: float,
        minimum_radius: float,
    ) -> ConstraintResult:
        """Valida concavidade e raio mínimo antes de gerar a malha."""
        maximum_radius = self.maximum_achievable_radius(generator)
        if not 0.0 <= concavity <= 1.0:
            return ConstraintResult(
                False,
                maximum_radius,
                "A concavidade das estações deve estar entre 0 e 1.",
            )
        if minimum_radius <= 0:
            return ConstraintResult(
                False,
                maximum_radius,
                "O raio mínimo deve ser maior que zero.",
            )
        if minimum_radius > maximum_radius:
            return ConstraintResult(
                False,
                maximum_radius,
                (
                    f"O raio mínimo de {minimum_radius:.2f} m não cabe nesta "
                    f"seção: com boca de {generator.beam:.2f} m o limite é a "
                    f"meia-boca, {maximum_radius:.2f} m. Reduza o raio ou "
                    "aumente a boca."
                ),
            )
        return ConstraintResult(True, maximum_radius)
