"""Geração paramétrica de uma malha de casco com quina e redans opcionais."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

STEP_RISER_WIDTH = 0.01
"""Distância longitudinal (m) entre as duas estações que formam o espelho do redan."""


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


@dataclass(frozen=True)
class ChineOptions:
    """Quina viva (hard chine) típica de cascos de planeio.

    As alturas são frações do pontal local (da quilha ao convés). A quina
    sobe da popa para a proa, como nos cascos de planeio usuais.
    """

    height_bow: float = 0.55
    height_stern: float = 0.35
    flat_width: float = 0.05
    flat_angle: float = 0.0

    def validate(self) -> None:
        for height in (self.height_bow, self.height_stern):
            if not 0.05 <= height <= 0.95:
                raise ValueError("A altura da quina deve estar entre 5% e 95% do pontal.")
        if self.flat_width < 0:
            raise ValueError("A largura do flat da quina não pode ser negativa.")
        if not -30.0 <= self.flat_angle <= 30.0:
            raise ValueError("O ângulo do flat da quina deve estar entre -30 e 30 graus.")


@dataclass(frozen=True)
class StepOptions:
    """Redan (degrau) transversal no fundo.

    Atrás do redan o fundo sobe ``height_keel`` na quilha e ``height_chine``
    na quina. A linha do redan forma ``sweep`` graus com a linha de estação
    (positivo: a ponta na quina fica mais para ré) e pode ser arqueada por
    ``curve`` metros no meio da meia-boca (positivo: arco para vante).
    """

    position: float = 0.45
    height_keel: float = 0.03
    height_chine: float = 0.05
    sweep: float = 10.0
    curve: float = 0.0


class HullGenerator:
    """Gera a superfície do casco por seções transversais.

    Cada seção vai do convés de bombordo ao de boreste passando pelas obras
    mortas, pelo fundo e pela quilha. A plenitude diminui da seção média até
    a proa, que termina em ponta, e até a popa, que termina no espelho.
    Opcionalmente, o convés fecha a superfície, a seção ganha uma quina viva
    e o fundo recebe redans.

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
        sheer_bow: float = 0.15,
        sheer_stern: float = 0.0,
        bow_flare: float = 0.08,
        stern_flare: float = 0.08,
        deck_camber: float = 0.02,
        transom_camber: float = 0.0,
        chine: ChineOptions | None = None,
        steps: tuple[StepOptions, ...] = (),
    ) -> None:
        """Inicializa os parâmetros dimensionais do casco.

        Args:
            total_length: Comprimento total do casco.
            midship_length: Comprimento aproximado da seção de boca máxima.
            beam: Boca máxima, medida no convés.
            draft: Calado, medido da quilha à linha d'água.
            stations: Quantidade de seções longitudinais da malha (cada redan
                acrescenta duas).
            section_points: Pontos na parte submersa de cada seção, da linha
                d'água de um bordo à do outro. Deve ser ímpar para haver um
                ponto exatamente sobre a quilha.
            freeboard: Altura do convés acima da linha d'água na seção média.
            transom_ratio: Largura do espelho de popa como fração da boca;
                zero produz uma popa em ponta.
            deadrise: Ângulo do fundo junto à quilha, em graus.
            closed_deck: Fecha o topo com o convés, tornando a malha estanque.
            sheer_bow: Elevação do convés na proa, como fração da borda livre.
            sheer_stern: Elevação do convés na popa, como fração da borda livre.
            bow_flare: Abertura das obras mortas na proa: a boca no convés é
                ``1 + bow_flare`` vezes a boca na linha d'água.
            stern_flare: Abertura das obras mortas na popa.
            deck_camber: Abaulamento do convés como fração da boca local.
            transom_camber: Curvatura do espelho para ré, como fração da boca
                do espelho.
            chine: Opções da quina viva; ``None`` gera bojo arredondado.
            steps: Redans do fundo, exigem quina.
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
        self.sheer_bow = float(sheer_bow)
        self.sheer_stern = float(sheer_stern)
        self.bow_flare = float(bow_flare)
        self.stern_flare = float(stern_flare)
        self.deck_camber = float(deck_camber)
        self.transom_camber = float(transom_camber)
        self.chine = chine
        self.steps = tuple(sorted(steps, key=lambda step: step.position))
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
        for sheer in (self.sheer_bow, self.sheer_stern):
            if not 0.0 <= sheer <= 1.0:
                raise ValueError("O tosamento deve estar entre 0% e 100% da borda livre.")
        for flare in (self.bow_flare, self.stern_flare):
            if not 0.0 <= flare <= 0.5:
                raise ValueError("A abertura das obras mortas deve estar entre 0% e 50%.")
        if not 0.0 <= self.deck_camber <= 0.1:
            raise ValueError("O abaulamento do convés deve estar entre 0% e 10% da boca.")
        if not 0.0 <= self.transom_camber <= 0.3:
            raise ValueError("A curvatura do espelho deve estar entre 0% e 30% da boca.")
        if self.chine is not None:
            self.chine.validate()
        self._validate_steps()

    def _validate_steps(self) -> None:
        if not self.steps:
            return
        if self.chine is None:
            raise ValueError("Os redans exigem um casco com quina.")
        positions = [step.position for step in self.steps]
        if any(not 0.15 <= position <= 0.85 for position in positions):
            raise ValueError("Os redans devem ficar entre 15% e 85% do comprimento.")
        if any(b - a < 0.05 for a, b in zip(positions, positions[1:])):
            raise ValueError("Os redans devem estar separados por pelo menos 5% do comprimento.")
        for step in self.steps:
            if not 0.0 <= step.height_keel <= 0.5 * self.draft:
                raise ValueError("A altura do redan na quilha deve estar entre 0 e metade do calado.")
            if not 0.0 <= step.height_chine <= 0.5 * self.draft:
                raise ValueError("A altura do redan na quina deve estar entre 0 e metade do calado.")
            if not -45.0 <= step.sweep <= 45.0:
                raise ValueError("O ângulo do redan deve estar entre -45 e 45 graus.")

    @property
    def topside_points(self) -> int:
        """Pontos de cada bordo acima da linha d'água, sem contar a própria linha."""
        return max(2, self.section_points // 8)

    @property
    def half_points(self) -> int:
        """Pontos de meia-seção, do convés até a quilha (inclusive)."""
        return self.section_points // 2 + 1 + self.topside_points

    @property
    def points_per_station(self) -> int:
        return 2 * self.half_points - 1

    @property
    def side_points(self) -> int:
        """Pontos do costado acima da quina (modo com quina)."""
        return self.topside_points + self.section_points // 8

    @property
    def chine_column(self) -> int | None:
        """Índice (na meia-seção) do ponto externo da quina."""
        return None if self.chine is None else self.side_points

    @property
    def row_count(self) -> int:
        return len(self._row_layout()[0])

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

    def _station_quantities(self, t: np.ndarray) -> dict[str, np.ndarray]:
        """Grandezas da seção em função da posição longitudinal ``t``."""
        fullness = self._longitudinal_fullness(t)
        flare = self.stern_flare + (self.bow_flare - self.stern_flare) * t
        deck_half_beam = 0.5 * self.beam * fullness
        bow_weight = np.clip((t - 0.5) / 0.5, 0.0, 1.0) ** 2
        stern_weight = np.clip((0.5 - t) / 0.5, 0.0, 1.0) ** 2
        return {
            "t": t,
            "flare": flare,
            "deck_half_beam": deck_half_beam,
            "waterline_half_beam": deck_half_beam / (1.0 + flare),
            "draft": self.draft * (0.75 + 0.25 * fullness),
            "freeboard": self.freeboard
            * (1.0 + self.sheer_bow * bow_weight + self.sheer_stern * stern_weight),
        }

    def _half_section(
        self,
        t: np.ndarray,
        keel_raise: np.ndarray | float = 0.0,
        chine_raise: np.ndarray | float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Calcula meias-seções (y ≥ 0) do convés até a quilha.

        ``t`` tem forma ``(S, 1)`` (todas as colunas da estação na mesma
        posição) ou ``(S, H)`` (cada coluna com sua posição, usado nos
        redans). Retorna ``y`` e ``z`` com forma ``(S, H)``.
        """
        quantities = self._station_quantities(t)
        if self.chine is None:
            return self._round_bilge_section(quantities)
        return self._chine_section(quantities, keel_raise, chine_raise)

    @staticmethod
    def _columns(quantities: dict[str, np.ndarray], columns: slice) -> dict[str, np.ndarray]:
        """Recorta as grandezas para um trecho de colunas, se variarem por coluna."""
        return {
            key: value if value.shape[1] == 1 else value[:, columns]
            for key, value in quantities.items()
        }

    def _round_bilge_section(
        self, quantities: dict[str, np.ndarray]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Seção de bojo arredondado.

        A parte submersa segue ``z = -T·(1 - g(u))`` com
        ``g(u) = d·u + (1 - d)·u^p``, com ``p = 2 + concavidade``. Como
        ``p ≥ 2``, o termo de potência é plano na quilha e o fundo em V vem
        apenas do termo linear, que impõe o pé de caverna; a concavidade
        controla quão cheio é o bojo. Acima da linha d'água, uma Bézier
        quadrática continua a tangente do fundo e termina vertical no convés.
        """
        top_count = self.topside_points
        exponent = 2.0 + self.station_concavity
        tan_deadrise = np.tan(np.radians(self.deadrise))

        bottom = self._columns(quantities, slice(top_count, None))
        half_beam = bottom["waterline_half_beam"]
        draft = bottom["draft"]
        linear_share = np.clip(tan_deadrise * half_beam / draft, 0.0, 1.0)
        # u = 1 na linha d'água, u = 0 na quilha.
        u = np.linspace(1.0, 0.0, self.section_points // 2 + 1)[None, :]
        shape = linear_share * u + (1.0 - linear_share) * u**exponent
        bottom_y = half_beam * u
        bottom_z = -draft * (1.0 - shape)

        top = self._columns(quantities, slice(0, top_count))
        half_beam = top["waterline_half_beam"]
        linear_share = np.clip(tan_deadrise * half_beam / top["draft"], 0.0, 1.0)
        # O ponto de controle fica sobre a tangente do fundo na linha d'água,
        # na vertical do convés, para que o costado continue o fundo sem quina.
        waterline_slope = top["draft"] * (linear_share + (1.0 - linear_share) * exponent)
        control_z = np.minimum(top["flare"] * waterline_slope, 0.6 * top["freeboard"])
        corner_y = top["deck_half_beam"]
        tau = np.linspace(1.0, 0.0, top_count + 1)[None, :-1]
        top_y = (1 - tau) ** 2 * half_beam + (2 * (1 - tau) * tau + tau**2) * corner_y
        top_z = 2 * (1 - tau) * tau * control_z + tau**2 * top["freeboard"]

        return np.hstack((top_y, bottom_y)), np.hstack((top_z, bottom_z))

    def _chine_section(
        self,
        quantities: dict[str, np.ndarray],
        keel_raise: np.ndarray | float,
        chine_raise: np.ndarray | float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Seção com quina viva: fundo, flat da quina e costado.

        O fundo vai da quilha ao ponto interno da quina com o mesmo perfil
        ``g`` do bojo arredondado; o flat liga o ponto interno ao externo;
        o costado é uma Bézier quadrática do ponto externo até o convés.
        """
        chine = self.chine
        side_count = self.side_points
        bottom_count = self.half_points - side_count - 2
        exponent = 2.0 + self.station_concavity
        tan_deadrise = np.tan(np.radians(self.deadrise))

        def chine_points(values: dict[str, np.ndarray]) -> tuple[np.ndarray, ...]:
            draft = values["draft"]
            depth = draft + values["freeboard"]
            height = chine.height_stern + (chine.height_bow - chine.height_stern) * values["t"] ** 2
            outer_y = values["waterline_half_beam"]
            outer_z = -draft + height * depth
            width = np.minimum(chine.flat_width, 0.5 * outer_y)
            inner_y = outer_y - width
            inner_z = outer_z + width * np.tan(np.radians(chine.flat_angle))
            return outer_y, outer_z, inner_y, inner_z

        side = self._columns(quantities, slice(0, side_count))
        outer_y, outer_z, _, _ = chine_points(side)
        outer_z = outer_z + chine_raise
        deck_y = side["deck_half_beam"]
        deck_z = side["freeboard"]
        control_z = outer_z + 0.4 * (deck_z - outer_z)
        tau = np.linspace(1.0, 0.0, side_count + 1)[None, :-1]
        side_y = (1 - tau) ** 2 * outer_y + (2 * (1 - tau) * tau + tau**2) * deck_y
        side_z = (1 - tau) ** 2 * outer_z + 2 * (1 - tau) * tau * control_z + tau**2 * deck_z

        flat = self._columns(quantities, slice(side_count, side_count + 2))
        outer_y, outer_z, inner_y, inner_z = chine_points(flat)
        rows = side_y.shape[0]
        flat_y = np.hstack(
            (np.broadcast_to(outer_y[:, :1], (rows, 1)), np.broadcast_to(inner_y[:, -1:], (rows, 1)))
        )
        flat_z = np.hstack(
            (np.broadcast_to(outer_z[:, :1], (rows, 1)), np.broadcast_to(inner_z[:, -1:], (rows, 1)))
        ) + chine_raise

        bottom = self._columns(quantities, slice(side_count + 2, None))
        _, _, inner_y, inner_z = chine_points(bottom)
        draft = bottom["draft"]
        rise = np.maximum(inner_z + draft, 1e-9)
        linear_share = np.clip(tan_deadrise * inner_y / rise, 0.0, 1.0)
        # v = 1 no ponto interno da quina (excluído), v = 0 na quilha.
        v = np.linspace(1.0, 0.0, bottom_count + 1)[None, 1:]
        shape = linear_share * v + (1.0 - linear_share) * v**exponent
        bottom_y = inner_y * v
        bottom_z = -draft + rise * shape + keel_raise + (chine_raise - keel_raise) * v

        return (
            np.hstack(
                (side_y, flat_y, np.broadcast_to(bottom_y, (rows, bottom_count)))
            ),
            np.hstack(
                (side_z, flat_z, np.broadcast_to(bottom_z, (rows, bottom_count)))
            ),
        )

    def _row_layout(self) -> tuple[np.ndarray, list[int]]:
        """Parâmetros nominais das linhas de estações e índices dos redans.

        Cada redan recebe duas linhas próprias, separadas por
        ``STEP_RISER_WIDTH``: a de ré (fundo elevado) e a de vante. Estações
        regulares muito próximas delas são descartadas.
        """
        base = self._station_parameters()
        if not self.steps:
            return base, []
        gap = 0.5 * STEP_RISER_WIDTH / self.total_length
        centers = np.array([1.0 - step.position for step in self.steps])
        anchors = np.sort(np.concatenate((centers - gap, centers + gap)))
        distance = np.min(np.abs(base[:, None] - anchors[None, :]), axis=1)
        kept = base[(distance > 4 * gap) | (base == 0.0) | (base == 1.0)]
        rows = np.sort(np.concatenate((kept, anchors)))
        aft_rows = [int(np.searchsorted(rows, center - gap)) for center in centers]
        return rows, aft_rows

    def _station_grid(self) -> tuple[np.ndarray, list[int]]:
        """Posição longitudinal de cada ponto de cada meia-seção.

        Sem redans, todas as colunas de uma estação ficam na mesma posição.
        Com redans, cada coluna é deslocada para que as duas linhas do redan
        sigam a linha enviesada do degrau, mantendo a malha estruturada.
        """
        rows, aft_rows = self._row_layout()
        if not self.steps:
            return rows[:, None], []

        gap = 0.5 * STEP_RISER_WIDTH / self.total_length
        centers = np.array([1.0 - step.position for step in self.steps])
        nominal_y, _ = self._half_section(centers[:, None])
        chine_y = nominal_y[:, self.chine_column][:, None]
        reach = np.minimum(nominal_y, chine_y)
        fraction = np.divide(reach, chine_y, out=np.zeros_like(reach), where=chine_y > 0)
        sweep = np.tan(np.radians([step.sweep for step in self.steps]))[:, None]
        curve = np.array([step.curve for step in self.steps])[:, None]
        # Deslocamento para ré (positivo) da linha do redan em cada coluna.
        offset = (reach * sweep - curve * 4.0 * fraction * (1.0 - fraction)) / self.total_length

        # t cresce da popa para a proa: processa os redans nessa ordem.
        order = np.argsort(centers)
        centers = centers[order]
        targets = centers[:, None] - offset[order]
        knots_nominal = np.empty(2 * len(centers))
        knots_nominal[0::2] = centers - gap
        knots_nominal[1::2] = centers + gap
        knots_nominal = np.concatenate(([0.0], knots_nominal, [1.0]))
        grid = np.empty((len(rows), self.half_points))
        for column in range(self.half_points):
            knots = np.empty(2 * len(centers))
            knots[0::2] = targets[:, column] - gap
            knots[1::2] = targets[:, column] + gap
            knots = np.clip(knots, 2 * gap, 1.0 - 2 * gap)
            knots = np.maximum.accumulate(knots + np.arange(len(knots)) * 1e-9)
            grid[:, column] = np.interp(
                rows, knots_nominal, np.concatenate(([0.0], knots, [1.0]))
            )
        return grid, aft_rows

    def _step_raises(self, row_count: int, aft_rows: list[int]) -> tuple[np.ndarray, np.ndarray]:
        """Elevação acumulada do fundo na quilha e na quina para cada linha."""
        keel = np.zeros((row_count, 1))
        chine = np.zeros((row_count, 1))
        for step, aft_row in zip(self.steps, aft_rows):
            keel[: aft_row + 1] += step.height_keel
            chine[: aft_row + 1] += step.height_chine
        return keel, chine

    def generate_mesh(self) -> HullMesh:
        """Calcula vértices e faces do casco."""
        grid, aft_rows = self._station_grid()
        row_count = grid.shape[0]
        keel_raise, chine_raise = self._step_raises(row_count, aft_rows)
        half_y, half_z = self._half_section(grid, keel_raise, chine_raise)
        half_t = np.broadcast_to(grid, half_y.shape)

        # Bombordo (y < 0) do convés até a quilha, depois boreste até o convés.
        section_y = np.hstack((-half_y, half_y[:, -2::-1]))
        section_z = np.hstack((half_z, half_z[:, -2::-1]))
        section_t = np.hstack((half_t, half_t[:, -2::-1]))
        count = self.points_per_station
        section_x = (section_t - 0.5) * self.total_length
        vertices = [np.column_stack((section_x.ravel(), section_y.ravel(), section_z.ravel()))]
        next_index = row_count * count

        faces, triangles = self._shell_faces(row_count, count)
        faces = [faces]

        transom_top = None
        if self.transom_ratio > 0:
            transom_vertices, transom_faces, transom_triangles, transom_top = self._transom(
                section_x[0], section_y[0], section_z[0], next_index
            )
            vertices.append(transom_vertices)
            faces.append(transom_faces)
            triangles = np.vstack((triangles, transom_triangles))
            next_index += len(transom_vertices)

        if self.closed_deck:
            # A primeira linha do convés é a borda superior do espelho: os dois
            # compartilham vértices para que a malha feche sem frestas.
            deck_vertices, deck_faces = self._deck(
                section_x, section_y, section_z, next_index, transom_top
            )
            vertices.append(deck_vertices)
            faces.append(deck_faces)

        return HullMesh(
            vertices=np.vstack(vertices).astype(np.float64),
            faces=np.vstack(faces).astype(np.int64),
            triangles=triangles.astype(np.int64),
        )

    def _shell_faces(self, row_count: int, count: int) -> tuple[np.ndarray, np.ndarray]:
        """Quadriláteros do costado e triângulos das faixas que colapsam.

        Na ponta da proa (e na popa sem espelho) a seção vira uma linha no
        plano central. Ali cada quadrilátero é dividido pela diagonal que sai
        do plano central; a outra diagonal criaria o mesmo triângulo plano em
        bombordo e boreste, deixando uma aresta compartilhada por mais de
        duas faces.
        """
        strips = np.arange(row_count - 1)
        collapsed = [row_count - 2]
        if self.transom_ratio == 0:
            collapsed.append(0)
        regular = np.setdiff1d(strips, collapsed)

        def corners(strip_rows: np.ndarray, columns: np.ndarray) -> np.ndarray:
            first = (strip_rows[:, None] * count + columns[None, :]).ravel()
            return np.column_stack((first, first + 1, first + count + 1, first + count))

        quads = corners(regular, np.arange(count - 1))
        keel = count // 2
        port_columns = np.arange(keel)
        starboard_columns = np.arange(keel, count - 1)
        # Cantos (0, 1) estão na estação de ré e (3, 2) na de vante. Na proa a
        # estação que colapsa é a de vante; na popa sem espelho, a de ré. A
        # diagonal escolhida é sempre a que liga um ponto fora do plano central.
        bow = np.array([row_count - 2])
        bow_port = corners(bow, port_columns)
        bow_starboard = corners(bow, starboard_columns)
        pieces = [
            bow_port[:, [0, 1, 2]],
            bow_port[:, [0, 2, 3]],
            bow_starboard[:, [0, 1, 3]],
            bow_starboard[:, [1, 2, 3]],
        ]
        if self.transom_ratio == 0:
            stern = np.array([0])
            stern_port = corners(stern, port_columns)
            stern_starboard = corners(stern, starboard_columns)
            pieces += [
                stern_port[:, [0, 1, 3]],
                stern_port[:, [1, 2, 3]],
                stern_starboard[:, [0, 1, 2]],
                stern_starboard[:, [0, 2, 3]],
            ]
        return quads, np.vstack(pieces)

    def _deck(
        self,
        section_x: np.ndarray,
        section_y: np.ndarray,
        section_z: np.ndarray,
        first_index: int,
        stern_interior: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Convés abaulado ligando as bordas de bombordo e boreste.

        ``stern_interior`` são os índices já existentes da primeira linha (a
        borda superior do espelho); quando informados, essa linha não é
        recriada.
        """
        row_count, count = section_y.shape
        columns = self._cross_columns
        first_row = 0 if stern_interior is None else 1
        edge_y = section_y[first_row:, -1:]
        across = np.linspace(-1.0, 1.0, columns)[None, 1:-1]
        interior_y = edge_y * across
        interior_z = section_z[first_row:, -1:] + self._deck_crown(edge_y, across)
        interior_x = np.broadcast_to(section_x[first_row:, -1:], interior_y.shape)
        vertices = np.column_stack((interior_x.ravel(), interior_y.ravel(), interior_z.ravel()))

        interior = first_index + np.arange(len(edge_y) * (columns - 2)).reshape(
            len(edge_y), -1
        )
        if stern_interior is not None:
            interior = np.vstack((stern_interior[None, :], interior))
        port = (np.arange(row_count) * count)[:, None]
        starboard = port + count - 1
        index = np.hstack((port, interior, starboard))
        quads = np.column_stack(
            (
                index[:-1, :-1].ravel(),
                index[1:, :-1].ravel(),
                index[1:, 1:].ravel(),
                index[:-1, 1:].ravel(),
            )
        )
        return vertices, quads

    @property
    def _cross_columns(self) -> int:
        """Pontos (ímpar) em cada linha transversal do convés e do espelho."""
        return max(3, self.section_points // 4) | 1

    def _deck_crown(self, edge_half_beam: np.ndarray, across: np.ndarray) -> np.ndarray:
        """Elevação parabólica do convés: ``deck_camber`` × boca no centro."""
        if not self.closed_deck:
            return np.zeros(np.broadcast_shapes(edge_half_beam.shape, across.shape))
        return self.deck_camber * 2.0 * edge_half_beam * (1.0 - across**2)

    def _transom(
        self,
        stern_x: np.ndarray,
        stern_y: np.ndarray,
        stern_z: np.ndarray,
        first_index: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Espelho de popa em faixas horizontais, com curvatura opcional para ré.

        Retorna também os índices dos pontos internos da borda superior, que
        o convés fechado reutiliza.
        """
        count = len(stern_y)
        middle = count // 2
        columns = self._cross_columns
        left = np.arange(middle)
        right = count - 1 - left
        half_width = stern_y[right][:, None]
        across = np.linspace(-1.0, 1.0, columns)[None, 1:-1]
        interior_y = half_width * across
        # O abaulamento do convés aparece na borda superior e some na quilha.
        height = stern_z[left][:, None]
        span = max(float(stern_z[0] - stern_z[middle]), 1e-12)
        fade = (height - stern_z[middle]) / span
        crown = self._deck_crown(np.full_like(half_width, half_width[0, 0]), across) * fade
        interior_z = height + crown
        transom_half_beam = max(float(stern_y.max()), 1e-12)
        bulge = self.transom_camber * transom_half_beam * (1.0 - across**2)
        interior_x = stern_x[left][:, None] - np.where(half_width > 0, bulge, 0.0)
        vertices = np.column_stack(
            (interior_x.ravel(), interior_y.ravel(), interior_z.ravel())
        )

        interior = first_index + np.arange(middle * (columns - 2)).reshape(middle, -1)
        index = np.hstack((left[:, None], interior, right[:, None]))
        quads = np.column_stack(
            (
                index[:-1, :-1].ravel(),
                index[:-1, 1:].ravel(),
                index[1:, 1:].ravel(),
                index[1:, :-1].ravel(),
            )
        )
        last = index[-1]
        triangles = np.column_stack((last[:-1], last[1:], np.full(len(last) - 1, middle)))
        return vertices, quads, triangles, interior[0]
