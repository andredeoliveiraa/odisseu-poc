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
        stations: int = 32,
    ) -> None:
        """Inicializa os parâmetros dimensionais do casco.

        Args:
            total_length: Comprimento total do casco.
            midship_length: Comprimento aproximado da seção de boca máxima.
            beam: Boca máxima, medida entre as bordas livres.
            draft: Calado, medido da quilha à linha d'água.
            stations: Quantidade de seções longitudinais da malha.
        """
        self.total_length = float(total_length)
        self.midship_length = float(midship_length)
        self.beam = float(beam)
        self.draft = float(draft)
        self.bow_angle = float(bow_angle)
        self.station_concavity = float(station_concavity)
        self.stations = int(stations)
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

    def generate_mesh(self) -> HullMesh:
        """Calcula vértices e faces quadrilaterais da superfície do casco."""
        longitudinal = np.linspace(0.0, 1.0, self.stations)
        fullness = self._longitudinal_fullness(longitudinal)
        half_beam = self.beam / 2

        # Cinco pontos por seção: borda livre/chine/quilha/chine/borda livre.
        # A interpolação cúbica no eixo transversal deixa a superfície contínua.
        section_parameter = np.linspace(-1.0, 1.0, 5)
        vertices = np.empty((self.stations * 5, 3), dtype=np.float64)
        for index, (station, scale) in enumerate(zip(longitudinal, fullness)):
            x = (station - 0.5) * self.total_length
            transverse = section_parameter * half_beam * scale
            vertical = -self.draft * (
                1.0 - np.abs(section_parameter) ** (1.35 + self.station_concavity)
            ) * (0.75 + 0.25 * scale)
            vertices[index * 5 : (index + 1) * 5] = np.column_stack(
                (np.full(5, x), transverse, vertical)
            )

        faces = []
        for station in range(self.stations - 1):
            row = station * 5
            next_row = (station + 1) * 5
            for section_point in range(4):
                faces.append(
                    (
                        row + section_point,
                        row + section_point + 1,
                        next_row + section_point + 1,
                        next_row + section_point,
                    )
                )

        return HullMesh(vertices=vertices, faces=np.asarray(faces, dtype=np.int64))
