"""Geração paramétrica de uma malha inicial de casco."""

from __future__ import annotations

import math
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

    Cada seção transversal é construída como um arco de bojo na quilha seguido
    do trecho que alcança a borda livre, de modo que o raio mínimo pedido pelo
    usuário é o raio real da curvatura na quilha da seção mestra. A plenitude
    cresce suavemente das extremidades até a região de seção média, e a
    reflexão em relação ao plano central produz os dois lados do casco.
    """

    #: Pontos usados em cada meia-seção, da quilha até a borda livre.
    TRANSVERSE_SAMPLES = 13

    def __init__(
        self,
        total_length: float = 12.0,
        midship_length: float = 6.0,
        beam: float = 4.0,
        draft: float = 1.8,
        bow_angle: float = 32.0,
        station_concavity: float = 0.0,
        minimum_radius: float = 1.9,
        stations: int = 32,
    ) -> None:
        """Inicializa os parâmetros dimensionais do casco.

        Args:
            total_length: Comprimento total do casco.
            midship_length: Comprimento aproximado da seção de boca máxima.
            beam: Boca máxima, medida entre as bordas livres.
            draft: Calado, medido da quilha à linha d'água.
            bow_angle: Índice de afilamento da proa, em graus; valores menores
                afinam a entrada. Não altera a popa.
            station_concavity: Quanto o costado é puxado para dentro, de 0 a 1.
            minimum_radius: Raio de curvatura da quilha na seção mestra.
            stations: Quantidade de seções longitudinais da malha.
        """
        self.total_length = float(total_length)
        self.midship_length = float(midship_length)
        self.beam = float(beam)
        self.draft = float(draft)
        self.bow_angle = float(bow_angle)
        self.station_concavity = float(station_concavity)
        self.minimum_radius = float(minimum_radius)
        self.stations = int(stations)
        self._validate_parameters()

    def _validate_parameters(self) -> None:
        if self.total_length <= 0 or self.midship_length <= 0:
            raise ValueError("Os comprimentos devem ser positivos.")
        if self.midship_length > self.total_length:
            raise ValueError("A seção média não pode exceder o comprimento total.")
        if self.beam <= 0 or self.draft <= 0:
            raise ValueError("A boca e o calado devem ser positivos.")
        if not 1.0 <= self.bow_angle <= 89.0:
            raise ValueError("O ângulo de proa deve estar entre 1 e 89 graus.")
        if not 0.0 <= self.station_concavity <= 1.0:
            raise ValueError("A concavidade das estações deve estar entre 0 e 1.")
        if self.minimum_radius <= 0:
            raise ValueError("O raio mínimo deve ser maior que zero.")
        if self.stations < 4:
            raise ValueError("São necessárias pelo menos 4 estações.")

    @staticmethod
    def maximum_station_radius(half_width: float, depth: float) -> float:
        """Maior raio de quilha admissível para uma seção transversal.

        O limite é a própria meia-boca. O arco chega a se afastar do plano
        central em até um raio, então um raio maior que a meia-boca estufaria a
        seção além da boca declarada.

        O outro limite concebível, o de construtibilidade do arco tangente
        — ``(meia-boca² + profundidade²) / (2 · profundidade)`` —, nunca é o
        que manda: ele é maior ou igual à meia-boca para qualquer seção, já que
        a desigualdade equivale a ``(meia-boca - profundidade)² >= 0``.
        """
        if depth <= 0 or half_width <= 0:
            return 0.0
        return half_width

    def maximum_keel_radius(self) -> float:
        """Limite do raio mínimo para a seção mestra deste casco."""
        return self.maximum_station_radius(self.beam / 2.0, self.draft)

    def _longitudinal_fullness(self, parameter: np.ndarray) -> np.ndarray:
        """Calcula a redução suave da seção em direção à proa e à popa."""
        ratio = self.midship_length / self.total_length
        transition = (1.0 - ratio) / 2.0
        if transition <= np.finfo(float).eps:
            return np.ones_like(parameter)

        # Smoothstep mantém derivada nula tanto nas extremidades quanto no
        # encontro com a região central de boca máxima. O expoente de
        # afilamento é aplicado apenas na metade de proa: a popa mantém a
        # transição neutra, para que "ângulo de proa" só reformule a proa.
        distance_from_end = np.minimum(parameter, 1.0 - parameter)
        normalized = np.clip(distance_from_end / transition, 0.0, 1.0)
        bow_sharpness = 1.0 + (45.0 - self.bow_angle) / 90.0
        sharpness = np.where(parameter > 0.5, bow_sharpness, 1.0)
        shaped = np.clip(normalized**sharpness, 0.0, 1.0)
        return shaped**2 * (3.0 - 2.0 * shaped)

    def _half_station(self, half_width: float, depth: float) -> np.ndarray:
        """Constrói metade de uma seção transversal, da quilha à borda livre.

        Retorna ``TRANSVERSE_SAMPLES`` pares ``(y, z)`` espaçados uniformemente
        ao longo do perfil. O primeiro ponto é a quilha em ``(0, -depth)`` e o
        último é a borda livre em ``(half_width, 0)``.
        """
        samples = self.TRANSVERSE_SAMPLES
        if half_width <= 1e-9 or depth <= 1e-9:
            fraction = np.linspace(0.0, 1.0, samples)
            return np.column_stack(
                (np.full(samples, half_width) * fraction, -depth * (1.0 - fraction))
            )

        radius = min(
            self.minimum_radius,
            self.maximum_station_radius(half_width, depth),
        )
        center_z = -depth + radius
        distance = math.hypot(half_width, depth - radius)
        tangent_length = math.sqrt(max(distance**2 - radius**2, 0.0))
        angle_to_sheer = math.atan2(depth - radius, half_width)
        theta_tangent = angle_to_sheer + math.asin(min(radius / distance, 1.0))
        arc_length = radius * theta_tangent
        tangent_y = radius * math.sin(theta_tangent)
        tangent_z = center_z - radius * math.cos(theta_tangent)
        total_length = arc_length + tangent_length
        concavity_pull = 0.25 * half_width * self.station_concavity

        profile = np.empty((samples, 2), dtype=np.float64)
        for index, position in enumerate(np.linspace(0.0, total_length, samples)):
            if position <= arc_length and arc_length > 0.0:
                theta = position / radius
                y = radius * math.sin(theta)
                z = center_z - radius * math.cos(theta)
            else:
                fraction = (
                    (position - arc_length) / tangent_length
                    if tangent_length > 0.0
                    else 1.0
                )
                y = tangent_y + fraction * (half_width - tangent_y)
                z = tangent_z + fraction * (0.0 - tangent_z)
                # A concavidade puxa o costado para dentro sem deslocar nem o
                # ponto de tangência nem a borda livre.
                y -= concavity_pull * math.sin(math.pi * fraction)
            profile[index] = (y, z)

        profile[0] = (0.0, -depth)
        profile[-1] = (half_width, 0.0)
        return profile

    @property
    def points_per_station(self) -> int:
        """Pontos de uma seção completa, já considerando o espelhamento."""
        return 2 * self.TRANSVERSE_SAMPLES - 1

    def generate_mesh(self) -> HullMesh:
        """Calcula vértices e faces quadrilaterais da superfície do casco."""
        longitudinal = np.linspace(0.0, 1.0, self.stations)
        fullness = self._longitudinal_fullness(longitudinal)
        half_beam = self.beam / 2.0
        width = self.points_per_station

        vertices = np.empty((self.stations * width, 3), dtype=np.float64)
        for index, (station, scale) in enumerate(zip(longitudinal, fullness)):
            x = (station - 0.5) * self.total_length
            half_section = self._half_station(
                half_beam * scale,
                self.draft * (0.75 + 0.25 * scale),
            )
            # De bombordo para boreste: meia-seção espelhada, quilha, meia-seção.
            transverse = np.concatenate(
                (-half_section[:0:-1, 0], half_section[:, 0])
            )
            vertical = np.concatenate(
                (half_section[:0:-1, 1], half_section[:, 1])
            )
            vertices[index * width : (index + 1) * width] = np.column_stack(
                (np.full(width, x), transverse, vertical)
            )

        faces = []
        for station in range(self.stations - 1):
            row = station * width
            next_row = (station + 1) * width
            for section_point in range(width - 1):
                faces.append(
                    (
                        row + section_point,
                        row + section_point + 1,
                        next_row + section_point + 1,
                        next_row + section_point,
                    )
                )

        return HullMesh(vertices=vertices, faces=np.asarray(faces, dtype=np.int64))
