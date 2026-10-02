"""Perfis paramétricos pré-configurados para cascos de iates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HullProfile:
    """Conjunto de valores iniciais que continua editável no painel."""

    name: str
    description: str
    total_length: float
    midship_length: float
    beam: float
    draft: float
    bow_angle: float
    concavity: float
    minimum_radius: float
    freeboard: float = 1.0
    transom_ratio: float = 0.65
    deadrise: float = 12.0


HULL_PROFILES: tuple[HullProfile, ...] = (
    HullProfile("Strong (Forte)", "Boca larga e proa robusta.", 14.0, 8.0, 5.2, 2.2, 48.0, 0.05, 2.0, 1.3, 0.75, 14.0),
    HullProfile("Speedy (Rápido)", "Casco esbelto, leve e de proa afiada.", 18.0, 6.5, 3.0, 1.2, 18.0, 0.15, 2.0, 0.8, 0.8, 20.0),
    HullProfile("Comfortable (Confortável)", "Volume generoso e linhas arredondadas.", 13.0, 8.5, 5.4, 2.0, 38.0, 0.65, 2.0, 1.4, 0.7, 8.0),
    HullProfile("Aesthetic (Estético)", "Transições fluidas e suaves.", 15.0, 8.0, 4.3, 1.7, 30.0, 0.75, 2.0, 1.0, 0.55, 12.0),
    HullProfile("Usual (Comum)", "Proporções equilibradas de semi-deslocamento.", 12.0, 6.0, 4.0, 1.8, 32.0, 0.35, 2.0, 1.0, 0.65, 12.0),
    HullProfile("Aggressive (Agressivo)", "Chine rígido e proa reta.", 16.0, 7.0, 4.5, 2.1, 12.0, 0.0, 2.0, 0.9, 0.8, 22.0),
    HullProfile("Compact (Compacto)", "Curto e largo para espaços reduzidos.", 9.0, 6.0, 4.6, 1.5, 42.0, 0.45, 2.0, 1.1, 0.75, 10.0),
    HullProfile("Modern (Moderno)", "Linhas limpas e proa vertical.", 15.5, 9.0, 5.0, 1.9, 8.0, 0.2, 2.0, 1.2, 0.85, 16.0),
    HullProfile("Charismatic (Carismático)", "Tosamento clássico de trawler.", 13.5, 8.0, 4.6, 2.0, 35.0, 0.55, 2.0, 1.5, 0.5, 6.0),
    HullProfile("Cute (Fofo)", "Pequeno, arredondado e acolhedor.", 8.5, 5.5, 4.4, 1.35, 50.0, 0.9, 2.0, 1.0, 0.45, 5.0),
)
