"""Modelos matemáticos de atributos do casco (Dogan, Figura 5.6).

Na tese de referência, cada atributo (forte, rápido, confortável...) é
representado por um modelo polinomial obtido com uma rede neural do tipo
GMDH. Os modelos compartilham características que reproduzimos aqui:

* as entradas são valores **padronizados** das variáveis de projeto;
* os neurônios combinam termos lineares, de raiz cúbica (``cubert``),
  quadráticos e produtos entre pares de entradas;
* um casco expressa um atributo quando o valor do modelo é maior que 0,5.

As variáveis de projeto são as 11 da Tabela 4.1 (``Le, Lm, Lr, Be, Bm, Br,
De, Dm, Dr, β, θ``), com os mesmos limites do experimento da tese.

Os coeficientes originais de Dogan aparecem truncados na figura (a imagem do
PDF tem só 1096 × 519 pixels, com linhas intermediárias omitidas) e dependem de
curvas de forma do ModiYacht (``Rm_1``, ``Dm_1`` ...) que não podem ser
transcritas. Os coeficientes abaixo são um **modelo substituto** com a mesma
estrutura e a mesma convenção (padronização e limiar 0,5), calibrado para que
cada atributo e as combinações usuais sejam alcançáveis no espaço de projeto.

Para usar coeficientes reais, grave-os em ``app/data/attribute_models.json`` (o
formato é o de :func:`export_attribute_models`, que gera um modelo de partida)
ou chame :func:`load_attribute_models`; o restante da aplicação não muda.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.models.hull_model import HullParameters
from app.models.hull_types import SEMI_DISPLACEMENT, INITIAL_PARAMETERS

ATTRIBUTE_THRESHOLD = 0.5
"""Valor a partir do qual o casco é considerado portador do atributo."""

#: Variáveis de projeto amostradas (Tabela 4.1), em ordem fixa.
DESIGN_VARIABLES = ("Le", "Lm", "Lr", "Be", "Bm", "Br", "De", "Dm", "Dr", "beta", "theta")


@dataclass(frozen=True)
class FeatureRange:
    """Faixa de uma variável de projeto (limites da Tabela 4.1).

    A média e o desvio padrão são os de uma distribuição uniforme na faixa,
    o que mantém a padronização independente de qualquer casco cadastrado.
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


#: Limites de cada variável de projeto, conforme a Tabela 4.1.
FEATURE_RANGES: dict[str, FeatureRange] = {
    "Le": FeatureRange(6.0, 12.0),
    "Lm": FeatureRange(6.0, 12.0),
    "Lr": FeatureRange(2.5, 8.0),
    "Be": FeatureRange(4.80, 10.80),
    "Bm": FeatureRange(4.64, 10.64),
    "Br": FeatureRange(3.0, 9.0),
    "De": FeatureRange(2.34, 4.34),
    "Dm": FeatureRange(2.21, 4.21),
    "Dr": FeatureRange(1.75, 3.50),
    "beta": FeatureRange(30.0, 120.0),
    "theta": FeatureRange(25.0, 70.0),
}


@dataclass(frozen=True)
class HullDesign:
    """Variáveis de projeto do casco (as 11 da Tabela 4.1)."""

    Le: float
    Lm: float
    Lr: float
    Be: float
    Bm: float
    Br: float
    De: float
    Dm: float
    Dr: float
    beta: float
    theta: float

    @classmethod
    def from_parameters(cls, parameters: HullParameters) -> "HullDesign":
        return cls(**{name: getattr(parameters, name) for name in DESIGN_VARIABLES})

    @classmethod
    def from_dict(cls, values: Mapping[str, float]) -> "HullDesign":
        return cls(**{name: float(values[name]) for name in DESIGN_VARIABLES})

    def as_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in DESIGN_VARIABLES}

    def to_parameters(
        self, base: HullParameters | None = None
    ) -> HullParameters:
        """Parâmetros completos do casco: as 11 variáveis mais as dependentes.

        Quinas e raio de curvatura acompanham a escala do casco-base (o
        semi-deslocamento da Tabela 3.4, por padrão), de modo que qualquer
        combinação de variáveis dentro dos limites forme um casco válido.
        """
        base = base or INITIAL_PARAMETERS[SEMI_DISPLACEMENT]
        scale = self.De / base.De
        height = base.H * scale
        return base.replace(
            **self.as_dict(),
            Fe=base.Fe / base.De * self.De,
            Fm=base.Fm / base.Dm * self.Dm,
            Fr=base.Fr / base.Dr * self.Dr,
            H=height,
            Fb=height * base.Fb / base.H,
            Rek=base.Rek * scale,
            Res1=base.Res1 * scale,
            Res2=base.Res2 * scale,
            Rms1=base.Rms1 * scale,
            Rms2=base.Rms2 * scale,
            Rrs1=base.Rrs1 * scale,
            Rrs2=base.Rrs2 * scale,
        )


def standardize_values(values: np.ndarray) -> np.ndarray:
    """Padroniza uma matriz ``(m, 11)`` de valores reais, colunas em ``DESIGN_VARIABLES``."""
    means = np.array([FEATURE_RANGES[n].mean for n in DESIGN_VARIABLES])
    deviations = np.array([FEATURE_RANGES[n].standard_deviation for n in DESIGN_VARIABLES])
    return (np.asarray(values, dtype=float) - means) / deviations


def standardized_features(design: HullDesign) -> dict[str, float]:
    """Retorna as entradas padronizadas, como exigem os modelos GMDH."""
    return {
        name: FEATURE_RANGES[name].standardize(getattr(design, name))
        for name in DESIGN_VARIABLES
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

    def evaluate_matrix(self, standardized: np.ndarray) -> np.ndarray:
        """Avalia várias linhas de entradas padronizadas (colunas em ``DESIGN_VARIABLES``)."""
        column = {name: standardized[:, i] for i, name in enumerate(DESIGN_VARIABLES)}
        value = np.full(len(standardized), self.intercept, dtype=float)
        for name, weight in self.linear.items():
            value += weight * column[name]
        for name, weight in self.cube_root.items():
            value += weight * np.cbrt(column[name])
        for name, weight in self.quadratic.items():
            value += weight * column[name] ** 2
        for (first, second), weight in self.interaction.items():
            value += weight * column[first] * column[second]
        return value


_DEFAULT_MODELS: tuple[AttributeModel, ...] = (
    AttributeModel(
        "strong", "Strong (Forte)", 0.36,
        cube_root={"Be": 0.07, "Bm": 0.07, "De": 0.06, "Dm": 0.08, "theta": 0.06, "Le": -0.04},
    ),
    AttributeModel(
        "speedy", "Speedy (Rápido)", 0.38,
        cube_root={"Le": 0.09, "theta": -0.09, "Br": -0.06, "De": -0.05, "beta": 0.04, "Lm": 0.03},
    ),
    AttributeModel(
        "comfortable", "Comfortable (Confortável)", 0.40,
        cube_root={"Bm": 0.07, "Lm": 0.07, "Lr": 0.06, "Be": 0.05, "De": 0.05, "beta": -0.03},
    ),
    AttributeModel(
        "aesthetic", "Aesthetic (Estético)", 0.52,
        cube_root={"beta": 0.08, "theta": -0.05, "Le": 0.05, "Be": -0.05},
        quadratic={"theta": -0.03, "Lm": -0.02},
    ),
    AttributeModel(
        "usual", "Usual (Comum)", 0.74,
        quadratic={"Le": -0.05, "Lm": -0.05, "Be": -0.05, "Bm": -0.05, "De": -0.05, "Dm": -0.05},
    ),
    AttributeModel(
        "aggressive", "Aggressive (Agressivo)", 0.34,
        cube_root={"theta": -0.09, "Le": 0.08, "De": 0.06, "Be": -0.06, "beta": -0.05},
    ),
    AttributeModel(
        "compact", "Compact (Compacto)", 0.38,
        cube_root={"Lm": -0.09, "Lr": -0.07, "Le": -0.04, "Dm": 0.04, "Bm": -0.03},
    ),
    AttributeModel(
        "modern", "Modern (Moderno)", 0.36,
        cube_root={"beta": 0.09, "theta": -0.07, "Lm": 0.04, "Br": -0.05, "Be": 0.04},
    ),
    AttributeModel(
        "charismatic", "Charismatic (Carismático)", 0.46,
        cube_root={"De": 0.07, "Dm": 0.06, "Lm": -0.05, "Be": 0.05},
        quadratic={"theta": -0.04},
    ),
    AttributeModel(
        "cute", "Cute (Fofo)", 0.38,
        cube_root={"Le": -0.05, "Lm": -0.06, "Be": 0.07, "beta": -0.06, "theta": 0.06, "Dm": 0.04},
    ),
)

#: Modelos em uso. As duas coleções são alteradas no lugar (ver
#: :func:`set_attribute_models`), então quem as importou continua vendo a troca.
ATTRIBUTE_MODELS: list[AttributeModel] = list(_DEFAULT_MODELS)
ATTRIBUTES_BY_KEY: dict[str, AttributeModel] = {
    model.key: model for model in ATTRIBUTE_MODELS
}

#: Arquivo opcional com os coeficientes reais, lido na importação do módulo.
MODELS_FILE = Path(__file__).resolve().parent.parent / "data" / "attribute_models.json"


def _check_variables(names: Sequence[str], key: str) -> None:
    unknown = [name for name in names if name not in DESIGN_VARIABLES]
    if unknown:
        raise ValueError(
            f"Atributo '{key}': variáveis desconhecidas {', '.join(unknown)} "
            f"(use {', '.join(DESIGN_VARIABLES)})."
        )


def model_from_dict(data: Mapping) -> AttributeModel:
    """Cria um modelo a partir do formato JSON de :func:`export_attribute_models`."""
    try:
        key = str(data["key"])
        intercept = float(data["intercept"])
    except KeyError as error:
        raise ValueError(f"Falta o campo {error} em um modelo de atributo.") from error
    linear = {str(n): float(w) for n, w in data.get("linear", {}).items()}
    cube_root = {str(n): float(w) for n, w in data.get("cube_root", {}).items()}
    quadratic = {str(n): float(w) for n, w in data.get("quadratic", {}).items()}
    interaction: dict[tuple[str, str], float] = {}
    for first, second, weight in data.get("interaction", []):
        interaction[(str(first), str(second))] = float(weight)
    for group in (linear, cube_root, quadratic):
        _check_variables(list(group), key)
    _check_variables([name for pair in interaction for name in pair], key)
    return AttributeModel(
        key=key,
        label=str(data.get("label", key)),
        intercept=intercept,
        linear=linear,
        cube_root=cube_root,
        quadratic=quadratic,
        interaction=interaction,
    )


def model_to_dict(model: AttributeModel) -> dict:
    return {
        "key": model.key,
        "label": model.label,
        "intercept": model.intercept,
        "linear": dict(model.linear),
        "cube_root": dict(model.cube_root),
        "quadratic": dict(model.quadratic),
        "interaction": [[a, b, w] for (a, b), w in model.interaction.items()],
    }


def set_attribute_models(models: Sequence[AttributeModel]) -> None:
    """Troca os modelos em uso (altera ``ATTRIBUTE_MODELS`` e ``ATTRIBUTES_BY_KEY`` no lugar)."""
    models = list(models)
    if not models:
        raise ValueError("É necessário pelo menos um modelo de atributo.")
    keys = [model.key for model in models]
    if len(set(keys)) != len(keys):
        raise ValueError("As chaves dos modelos de atributo devem ser únicas.")
    ATTRIBUTE_MODELS[:] = models
    ATTRIBUTES_BY_KEY.clear()
    ATTRIBUTES_BY_KEY.update({model.key: model for model in models})


def load_attribute_models(path: str | Path) -> list[AttributeModel]:
    """Lê os modelos de um arquivo JSON, passa a usá-los e os devolve."""
    with open(path, encoding="utf-8") as handle:
        content = json.load(handle)
    entries = content["models"] if isinstance(content, dict) else content
    models = [model_from_dict(entry) for entry in entries]
    set_attribute_models(models)
    return models


def export_attribute_models(path: str | Path, models: Sequence[AttributeModel] | None = None) -> None:
    """Grava os modelos (por padrão, os em uso) como JSON, para servir de modelo de partida."""
    selected = list(ATTRIBUTE_MODELS if models is None else models)
    payload = {
        "description": "Modelos de atributo (Figura 5.6): Y = a0 + Σ linear·x + Σ cube_root·cbrt(x) "
        "+ Σ quadratic·x² + Σ interaction·xi·xj, com x padronizado (Tabela 4.1).",
        "variables": list(DESIGN_VARIABLES),
        "models": [model_to_dict(model) for model in selected],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


if MODELS_FILE.is_file():
    load_attribute_models(MODELS_FILE)


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
