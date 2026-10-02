"""Geração paramétrica de uma malha fechada de casco."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

FLARE = 0.08
"""Abertura das obras mortas: a boca no convés é 8% maior que na linha d'água."""


@dataclass(frozen=True)
class HullMesh:
    """Dados de uma malha de superfície compatível com PyVista."""

    vertices: np.ndarray
    faces: np.ndarray
    triangles: np.ndarray = field(
        default_factory=lambda: np.empty((0, 3), dtype=np.int64)
    )

    @property
    def pyvista_faces(self) -> np.ndarray:
        """Retorna faces no formato achatado exigido por ``pyvista.PolyData``."""
        quads = np.hstack((np.full((len(self.faces), 1), 4), self.faces)).ravel()
        triangles = np.hstack(
            (np.full((len(self.triangles), 1), 3), self.triangles)
        ).ravel()
        return np.concatenate((quads, triangles)).astype(np.int64)

    def triangulated(self) -> np.ndarray:
        """Retorna todas as faces como triângulos, útil para cálculos."""
        return np.vstack(
            (self.faces[:, [0, 1, 2]], self.faces[:, [0, 2, 3]], self.triangles)
        )


class HullGenerator:
    """Gera um casco fechado por seções transversais suaves.

    Cada seção vai do convés de bombordo ao de boreste passando pelas obras
    mortas (acima da linha d'água), pelo fundo e pela quilha. A plenitude
    diminui da seção média até a proa, que termina em ponta, e até a popa,
    que termina no espelho. Opcionalmente, o convés fecha a superfície.

    O eixo X aponta da popa (x = -L/2) para a proa (x = +L/2) e a linha
    d'água está em z = 0.
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
        freeboard: float = 1.0,
        transom_ratio: float = 0.65,
        deadrise: float = 12.0,
        closed_deck: bool = False,
    ) -> None:
        """Inicializa os parâmetros dimensionais do casco.

        Args:
            total_length: Comprimento total do casco.
            midship_length: Comprimento aproximado da seção de boca máxima.
            beam: Boca máxima, medida no convés.
            draft: Calado, medido da quilha à linha d'água.
            stations: Quantidade de seções longitudinais da malha.
            section_points: Pontos na parte submersa de cada seção, da linha
                d'água de um bordo à do outro. Deve ser ímpar para haver um
                ponto exatamente sobre a quilha.
            freeboard: Altura do convés acima da linha d'água.
            transom_ratio: Largura do espelho de popa como fração da boca;
                zero produz uma popa em ponta.
            deadrise: Ângulo do fundo junto à quilha, em graus.
            closed_deck: Fecha o topo com o convés, tornando a malha estanque
                (necessário para volume, CFD ou impressão 3D).
        """
        self.total_length = float(total_length)
        self.midship_length = float(midship_length)
        self.beam = float(beam)
        self.draft = float(draft)
        self.bow_angle = float(bow_angle)
        self.station_concavity = float(station_concavity)
        self.stations = int(stations)
        self.section_points = int(section_points)
        self.freeboard = float(freeboard)
        self.transom_ratio = float(transom_ratio)
        self.deadrise = float(deadrise)
        self.closed_deck = bool(closed_deck)
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
        if self.freeboard <= 0:
            raise ValueError("A borda livre deve ser positiva.")
        if not 0.0 <= self.transom_ratio <= 0.95:
            raise ValueError("A largura do espelho deve estar entre 0 e 0,95 da boca.")
        if not 0.0 <= self.deadrise <= 35.0:
            raise ValueError("O pé de caverna deve estar entre 0 e 35 graus.")

    @property
    def topside_points(self) -> int:
        """Pontos de cada bordo acima da linha d'água, sem contar a própria linha."""
        return max(2, self.section_points // 8)

    @property
    def points_per_station(self) -> int:
        return self.section_points + 2 * self.topside_points

    def _longitudinal_fullness(self, parameter: np.ndarray) -> np.ndarray:
        """Calcula a redução suave da seção em direção à proa e à popa."""
        ratio = self.midship_length / self.total_length
        transition = (1.0 - ratio) / 2.0
        if transition <= np.finfo(float).eps:
            return np.ones_like(parameter)

        def smoothstep(value: np.ndarray) -> np.ndarray:
            # Derivada nula nas duas pontas: encontro suave com a seção média.
            value = np.clip(value, 0.0, 1.0)
            return value**2 * (3.0 - 2.0 * value)

        sharpness = 1.0 + (45.0 - self.bow_angle) / 90.0
        bow = smoothstep(np.clip((1.0 - parameter) / transition, 0.0, 1.0) ** sharpness)
        stern = self.transom_ratio + (1.0 - self.transom_ratio) * smoothstep(
            parameter / transition
        )
        return np.where(parameter < 0.5, stern, bow)

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

    def _half_section(self, fullness: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Calcula meia-seção (y ≥ 0) do convés até a quilha para cada estação.

        A parte submersa segue ``z = -T·(1 - g(u))`` com
        ``g(u) = d·u + (1 - d)·u^p``, com ``p = 2 + concavidade``. Como
        ``p ≥ 2``, o termo de potência é plano na quilha e o fundo em V vem
        apenas do termo linear, que impõe o pé de caverna; a concavidade
        controla quão cheio é o bojo. Acima da
        linha d'água, uma Bézier quadrática continua a tangente do fundo e
        termina vertical no convés.
        """
        half_count = self.section_points // 2
        waterline_half_beam = 0.5 * self.beam * fullness / (1.0 + FLARE)
        local_draft = self.draft * (0.75 + 0.25 * fullness)
        exponent = 2.0 + self.station_concavity
        linear_share = np.clip(
            np.tan(np.radians(self.deadrise)) * waterline_half_beam / local_draft,
            0.0,
            1.0,
        )[:, None]

        # u = 1 na linha d'água, u = 0 na quilha.
        u = np.linspace(1.0, 0.0, half_count + 1)[None, :]
        shape = linear_share * u + (1.0 - linear_share) * u**exponent
        bottom_y = waterline_half_beam[:, None] * u
        bottom_z = -local_draft[:, None] * (1.0 - shape)

        waterline_slope = local_draft * (
            linear_share[:, 0] + (1.0 - linear_share[:, 0]) * exponent
        )
        # O ponto de controle fica sobre a tangente do fundo na linha d'água
        # (inclinação dz/dy = waterline_slope / meia-boca), na vertical do convés.
        offset = FLARE * waterline_half_beam
        control_z = np.minimum(FLARE * waterline_slope, 0.6 * self.freeboard)
        tau = np.linspace(1.0, 0.0, self.topside_points + 1)[None, :-1]
        start_y, start_z = waterline_half_beam[:, None], 0.0
        corner_y = (waterline_half_beam + offset)[:, None]
        control = control_z[:, None]
        top_y = (1 - tau) ** 2 * start_y + 2 * (1 - tau) * tau * corner_y + tau**2 * corner_y
        top_z = (1 - tau) ** 2 * start_z + 2 * (1 - tau) * tau * control + tau**2 * self.freeboard

        return np.hstack((top_y, bottom_y)), np.hstack((top_z, bottom_z))

    def generate_mesh(self) -> HullMesh:
        """Calcula vértices e faces do casco fechado."""
        longitudinal = self._station_parameters()
        fullness = self._longitudinal_fullness(longitudinal)
        half_y, half_z = self._half_section(fullness)

        # Bombordo (y < 0) do convés até a quilha, depois boreste até o convés.
        section_y = np.hstack((-half_y, half_y[:, -2::-1]))
        section_z = np.hstack((half_z, half_z[:, -2::-1]))
        count = self.points_per_station
        x = np.repeat((longitudinal - 0.5) * self.total_length, count)
        vertices = np.column_stack((x, section_y.ravel(), section_z.ravel()))

        rows = np.arange(self.stations - 1)[:, None] * count
        first = (rows + np.arange(count - 1)[None, :]).ravel()
        shell = np.column_stack((first, first + 1, first + count + 1, first + count))

        faces = [shell]
        if self.closed_deck:
            # Convés: liga as bordas de bombordo e boreste de estações vizinhas.
            port = np.arange(self.stations - 1) * count
            starboard = port + count - 1
            faces.append(
                np.column_stack((port, port + count, starboard + count, starboard))
            )
        triangles = np.empty((0, 3), dtype=np.int64)
        if self.transom_ratio > 0:
            # Espelho: faixas horizontais entre pontos simétricos da popa.
            middle = count // 2
            left = np.arange(middle - 1)
            right = count - 1 - left
            faces.append(np.column_stack((left, right, right - 1, left + 1)))
            triangles = np.array([[middle - 1, middle + 1, middle]], dtype=np.int64)

        return HullMesh(
            vertices=vertices.astype(np.float64),
            faces=np.vstack(faces).astype(np.int64),
            triangles=triangles,
        )
