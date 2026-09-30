"""Modelos matemáticos de atributos do casco (Dogan, Figura 5.6).

Na tese de referência, cada atributo (forte, rápido, confortável...) é
representado por um modelo polinomial obtido com uma rede neural do tipo
GMDH. Os modelos compartilham três características que reproduzimos aqui:

* as entradas são valores **padronizados** dos parâmetros do casco;
* os neurônios combinam termos lineares, termos de raiz cúbica (``cubert``)
  e produtos entre pares de entradas;
* um casco expressa um atributo quando o valor do modelo é maior que 0,5.

Os coeficientes originais de Dogan dependem das curvas de forma do ModiYacht
(Lr, Dm_1, Be, α, θ...) e aparecem truncados na figura, portanto não podem
ser transcritos para o gerador simplificado do Odisseu. Os coeficientes
abaixo são um **modelo substituto** com a mesma estrutura, calibrado sobre
os parâmetros adimensionais deste gerador e sobre os perfis de
``app.models.profiles``. Eles podem ser substituídos por coeficientes
ajustados a dados de pesquisa sem alterar o restante da aplicação.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

ATTRIBUTE_THRESHOLD = 0.5
"""Valor a partir do qual o casco é considerado portador do atributo."""


@dataclass(frozen=True)
class HullDesign:
    """Variáveis de projeto que o gerador paramétrico aceita."""

    total_length: float
    midship_length: float
    beam: float
    draft: float
    bow_angle: float
    concavity: float


@dataclass(frozen=True)
class FeatureRange:
    """Faixa do espaço de projeto usada para padronizar uma entrada.

    A média e o desvio padrão são os de uma distribuição uniforme na faixa,
    o que mantém a padronização independente dos perfis cadastrados.
    """

    minimum: float
    maximum: float

    @property
    def mean(self) -> float:
        return 0.5 * (self.minimum + self.maximum)

    @property
    def standard_deviation(self) -> float:
        return (self.maximum - self.minimum) / np.sqrt(12.0)

    def standardize(self, value: float) -> float:
        return (value - self.mean) / self.standard_deviation


FEATURE_RANGES: dict[str, FeatureRange] = {
    # Porte do casco em metros.
    "length": FeatureRange(6.0, 24.0),
    # Esbeltez L/B: cascos longos e estreitos são associados a velocidade.
    "slenderness": FeatureRange(1.8, 6.5),
    # Relação boca/calado: valores altos indicam cascos rasos e largos.
    "beam_draft": FeatureRange(1.8, 3.6),
    # Fração do comprimento com seção cheia (plenitude longitudinal).
    "fullness": FeatureRange(0.3, 0.75),
    # Ângulo de entrada da proa em graus.
    "bow_angle": FeatureRange(5.0, 60.0),
    # Concavidade das estações: 0 = chine duro, 1 = seções arredondadas.
    "concavity": FeatureRange(0.0, 1.0),
}


def design_features(design: HullDesign) -> dict[str, float]:
    """Converte as variáveis de projeto em entradas adimensionais."""
    return {
        "length": design.total_length,
        "slenderness": design.total_length / design.beam,
        "beam_draft": design.beam / design.draft,
        "fullness": design.midship_length / design.total_length,
        "bow_angle": design.bow_angle,
        "concavity": design.concavity,
    }


def standardized_features(design: HullDesign) -> dict[str, float]:
    """Retorna as entradas padronizadas, como exigem os modelos GMDH."""
    return {
        name: FEATURE_RANGES[name].standardize(value)
        for name, value in design_features(design).items()
    }


@dataclass(frozen=True)
class AttributeModel:
    """Polinômio no formato dos neurônios GMDH da Figura 5.6.

    ``Y = a0 + Σ aᵢ·xᵢ + Σ cᵢ·cubert(xᵢ) + Σ qᵢ·xᵢ² + Σ pᵢⱼ·xᵢ·xⱼ``
    """

    key: str
    label: str
    intercept: float
    linear: Mapping[str, float] = field(default_factory=dict)
    cube_root: Mapping[str, float] = field(default_factory=dict)
    quadratic: Mapping[str, float] = field(default_factory=dict)
    interaction: Mapping[tuple[str, str], float] = field(default_factory=dict)

    def evaluate_standardized(self, inputs: Mapping[str, float]) -> float:
        value = self.intercept
        for name, weight in self.linear.items():
            value += weight * inputs[name]
        for name, weight in self.cube_root.items():
            value += weight * float(np.cbrt(inputs[name]))
        for name, weight in self.quadratic.items():
            value += weight * inputs[name] ** 2
        for (first, second), weight in self.interaction.items():
            value += weight * inputs[first] * inputs[second]
        return float(value)

    def evaluate(self, design: HullDesign) -> float:
        return self.evaluate_standardized(standardized_features(design))


ATTRIBUTE_MODELS: tuple[AttributeModel, ...] = (
    AttributeModel(
        "strong",
        "Strong (Forte)",
        0.40,
        cube_root={
            "slenderness": -0.06,
            "beam_draft": -0.10,
            "bow_angle": 0.10,
            "concavity": -0.16,
        },
        interaction={("bow_angle", "concavity"): -0.06},
    ),
    AttributeModel(
        "speedy",
        "Speedy (Rápido)",
        0.42,
        cube_root={
            "slenderness": 0.22,
            "fullness": -0.08,
            "bow_angle": -0.08,
            "concavity": -0.04,
        },
    ),
    AttributeModel(
        "comfortable",
        "Comfortable (Confortável)",
        0.46,
        cube_root={
            "slenderness": -0.10,
            "fullness": 0.12,
            "concavity": 0.06,
            "bow_angle": 0.04,
            "length": 0.04,
        },
    ),
    AttributeModel(
        "aesthetic",
        "Aesthetic (Estético)",
        0.52,
        cube_root={"concavity": 0.18, "slenderness": 0.06, "fullness": -0.04},
        quadratic={"bow_angle": -0.06},
    ),
    AttributeModel(
        "usual",
        "Usual (Comum)",
        0.76,
        quadratic={
            "length": -0.05,
            "slenderness": -0.05,
            "beam_draft": -0.05,
            "fullness": -0.05,
            "bow_angle": -0.05,
            "concavity": -0.05,
        },
    ),
    AttributeModel(
        "aggressive",
        "Aggressive (Agressivo)",
        0.40,
        cube_root={
            "bow_angle": -0.08,
            "concavity": -0.18,
            "beam_draft": -0.06,
            "fullness": -0.08,
            "slenderness": 0.04,
        },
    ),
    AttributeModel(
        "compact",
        "Compact (Compacto)",
        0.40,
        cube_root={"length": -0.16, "slenderness": -0.12, "concavity": -0.04},
    ),
    AttributeModel(
        "modern",
        "Modern (Moderno)",
        0.40,
        cube_root={
            "bow_angle": -0.14,
            "fullness": 0.12,
            "beam_draft": 0.04,
            "length": 0.04,
        },
    ),
    AttributeModel(
        "charismatic",
        "Charismatic (Carismático)",
        0.60,
        cube_root={"concavity": 0.06, "fullness": 0.06, "beam_draft": -0.08},
        quadratic={"bow_angle": -0.06, "slenderness": -0.06, "length": -0.04},
    ),
    AttributeModel(
        "cute",
        "Cute (Fofo)",
        0.40,
        cube_root={
            "length": -0.10,
            "concavity": 0.10,
            "bow_angle": 0.08,
            "beam_draft": 0.06,
        },
    ),
)

ATTRIBUTES_BY_KEY: dict[str, AttributeModel] = {
    model.key: model for model in ATTRIBUTE_MODELS
}


def evaluate_attributes(design: HullDesign) -> dict[str, float]:
    """Avalia todos os atributos de um casco, na ordem de ``ATTRIBUTE_MODELS``."""
    inputs = standardized_features(design)
    return {model.key: model.evaluate_standardized(inputs) for model in ATTRIBUTE_MODELS}


def expressed_attributes(design: HullDesign) -> list[str]:
    """Lista os atributos cujo modelo supera o limiar de 0,5."""
    return [
        key
        for key, value in evaluate_attributes(design).items()
        if value > ATTRIBUTE_THRESHOLD
    ]
