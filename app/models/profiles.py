"""Perfis paramétricos pré-configurados para cascos de iates."""

from __future__ import annotations

from dataclasses import dataclass


#: Rótulo usado quando os campos não correspondem mais a nenhum preset.
CUSTOM_PROFILE_NAME = "Personalizado"


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

    @property
    def values(self) -> tuple[float, ...]:
        """Valores na mesma ordem dos campos do painel."""
        return (
            self.total_length,
            self.midship_length,
            self.beam,
            self.draft,
            self.bow_angle,
            self.concavity,
            self.minimum_radius,
        )


# O raio mínimo de cada perfil respeita o limite geométrico da sua seção
# mestra, dado por (meia-boca² + calado²) / (2 · calado).
HULL_PROFILES: tuple[HullProfile, ...] = (
    HullProfile("Strong (Forte)", "Boca larga e proa robusta.", 14.0, 8.0, 5.2, 2.2, 48.0, 0.05, 2.2),
    HullProfile("Speedy (Rápido)", "Casco esbelto, leve e de proa afiada.", 18.0, 6.5, 3.0, 1.2, 18.0, 0.15, 0.9),
    HullProfile("Comfortable (Confortável)", "Volume generoso e linhas arredondadas.", 13.0, 8.5, 5.4, 2.0, 38.0, 0.65, 2.6),
    HullProfile("Aesthetic (Estético)", "Transições fluidas e suaves.", 15.0, 8.0, 4.3, 1.7, 30.0, 0.75, 1.8),
    HullProfile("Usual (Comum)", "Proporções equilibradas de semi-deslocamento.", 12.0, 6.0, 4.0, 1.8, 32.0, 0.35, 1.9),
    HullProfile("Aggressive (Agressivo)", "Chine rígido e proa reta.", 16.0, 7.0, 4.5, 2.1, 12.0, 0.0, 1.1),
    HullProfile("Compact (Compacto)", "Curto e largo para espaços reduzidos.", 9.0, 6.0, 4.6, 1.5, 42.0, 0.45, 2.0),
    HullProfile("Modern (Moderno)", "Linhas limpas e proa vertical.", 15.5, 9.0, 5.0, 1.9, 8.0, 0.2, 1.5),
    HullProfile("Charismatic (Carismático)", "Tosamento clássico de trawler.", 13.5, 8.0, 4.6, 2.0, 35.0, 0.55, 2.0),
    HullProfile("Cute (Fofo)", "Pequeno, arredondado e acolhedor.", 8.5, 5.5, 4.4, 1.35, 50.0, 0.9, 2.1),
)

#: Perfil aplicado ao abrir a aplicação e ao criar um casco novo.
DEFAULT_PROFILE: HullProfile = HULL_PROFILES[4]
