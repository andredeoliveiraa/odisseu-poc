"""Geração paramétrica de uma malha inicial de casco."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HullMesh:
    """Dados de uma malha de superfície compatível com PyVista."""

    vertices: np.ndarray
    faces: np.ndarray

    @property
    def pyvista_faces(self) -> np.ndarray:
        """Retorna faces no formato achatado exigido por ``pyvista.PolyData``."""
        face_size = np.full((len(self.faces), 1), 4, dtype=np.int64)
        return np.hstack((face_size, self.faces)).ravel()


class HullGenerator:
    """Gera um casco simplificado por seções transversais suaves.

    A plenitude cresce suavemente da proa e da popa até a região de seção
    média. Cada seção liga a quilha, a chine e a borda livre; a reflexão em
    relação ao plano central produz os dois lados do casco.
    """

    def __init__(
        self,
        total_length: float = 12.0,
        midship_length: float = 6.0,
        beam: float = 4.0,
        draft: float = 1.8,
        bow_angle: float = 32.0,
        station_concavity: float = 0.0,
        stations: int = 64,
        section_points: int = 33,
    ) -> None:
        """Inicializa os parâmetros dimensionais do casco.

        Args:
            total_length: Comprimento total do casco.
            midship_length: Comprimento aproximado da seção de boca máxima.
            beam: Boca máxima, medida entre as bordas livres.
            draft: Calado, medido da quilha à linha d'água.
            stations: Quantidade de seções longitudinais da malha.
            section_points: Pontos em cada seção transversal, da borda livre
                de um bordo à do outro. Deve ser ímpar para haver um ponto
                exatamente sobre a quilha.
        """
        self.total_length = float(total_length)
        self.midship_length = float(midship_length)
        self.beam = float(beam)
        self.draft = float(draft)
        self.bow_angle = float(bow_angle)
        self.station_concavity = float(station_concavity)
        self.stations = int(stations)
        self.section_points = int(section_points)
        self._validate_parameters()

    def _validate_parameters(self) -> None:
        if self.total_length <= 0 or self.midship_length <= 0:
            raise ValueError("Os comprimentos devem ser positivos.")
        if self.midship_length > self.total_length:
            raise ValueError("midship_length não pode exceder total_length.")
        if self.beam <= 0 or self.draft <= 0:
            raise ValueError("beam e draft devem ser positivos.")
        if not 1.0 <= self.bow_angle <= 89.0:
            raise ValueError("bow_angle deve estar entre 1 e 89 graus.")
        if not 0.0 <= self.station_concavity <= 1.0:
            raise ValueError("station_concavity deve estar entre 0 e 1.")
        if self.stations < 4:
            raise ValueError("São necessárias pelo menos 4 estações.")
        if self.stations > 512:
            raise ValueError("São permitidas no máximo 512 estações.")
        if not 5 <= self.section_points <= 257:
            raise ValueError("Os pontos por seção devem estar entre 5 e 257.")
        if self.section_points % 2 == 0:
            raise ValueError(
                "Os pontos por seção devem ser ímpares para incluir a quilha."
            )

    def _longitudinal_fullness(self, parameter: np.ndarray) -> np.ndarray:
        """Calcula a redução suave da seção em direção à proa e à popa."""
        ratio = self.midship_length / self.total_length
        transition = (1.0 - ratio) / 2.0
        if transition <= np.finfo(float).eps:
            return np.ones_like(parameter)

        # Smoothstep mantém derivada nula tanto nas extremidades quanto no
        # encontro com a região central de boca máxima.
        distance_from_end = np.minimum(parameter, 1.0 - parameter)
        normalized = np.clip(distance_from_end / transition, 0.0, 1.0)
        sharpness = 1.0 + (45.0 - self.bow_angle) / 90.0
        return np.clip(normalized**sharpness, 0.0, 1.0) ** 2 * (
            3.0 - 2.0 * np.clip(normalized**sharpness, 0.0, 1.0)
        )

    def _station_parameters(self) -> np.ndarray:
        """Distribui as estações conforme a variação da forma.

        Metade das estações segue um espaçamento uniforme; a outra metade é
        distribuída proporcionalmente à variação da plenitude. Assim, as
        regiões de transição entre a seção média e as extremidades recebem
        mais seções, e a região de seção constante recebe menos.
        """
        dense = np.linspace(0.0, 1.0, 4001)
        change = np.concatenate(
            ([0.0], np.cumsum(np.abs(np.diff(self._longitudinal_fullness(dense)))))
        )
        if change[-1] > 0:
            change /= change[-1]
        else:
            change = dense
        measure = 0.5 * (dense + change)
        return np.interp(np.linspace(0.0, 1.0, self.stations), measure, dense)

    def generate_mesh(self) -> HullMesh:
        """Calcula vértices e faces quadrilaterais da superfície do casco."""
        longitudinal = self._station_parameters()
        fullness = self._longitudinal_fullness(longitudinal)
        half_beam = self.beam / 2

        # Cada seção vai da borda livre de bombordo à de boreste passando pela
        # quilha; a reflexão em relação ao plano central é implícita em s.
        section_parameter = np.linspace(-1.0, 1.0, self.section_points)
        x = np.repeat((longitudinal - 0.5) * self.total_length, self.section_points)
        transverse = np.outer(fullness, section_parameter) * half_beam
        profile = 1.0 - np.abs(section_parameter) ** (1.35 + self.station_concavity)
        vertical = -self.draft * np.outer(0.75 + 0.25 * fullness, profile)
        vertices = np.column_stack((x, transverse.ravel(), vertical.ravel()))

        rows = np.arange(self.stations - 1)[:, None] * self.section_points
        columns = np.arange(self.section_points - 1)[None, :]
        first = (rows + columns).ravel()
        faces = np.column_stack(
            (
                first,
                first + 1,
                first + self.section_points + 1,
                first + self.section_points,
            )
        ).astype(np.int64)

        return HullMesh(vertices=vertices.astype(np.float64), faces=faces)
