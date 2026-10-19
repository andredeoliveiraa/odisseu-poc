"""Modelo paramétrico do casco: regiões, curvas características e superfícies.

Segue a seção 3.2 da referência. O casco é dividido em três regiões (entrada,
meio e popa) separadas pelas estações 1, 2 e 3. Cada região é formada por
*curvas características* (Bézier cúbicas): linha de convés, linha(s) de quilha
e de quina e as linhas de estação. A proa tem ainda a linha de roda de proa
(um segmento reto). Entre as curvas, a superfície é interpolada por patches de
Coons e espelhada em torno do plano de simetria.

Sistema de coordenadas: ``x`` é o comprimento (proa em +x, espelho de popa em
x = 0), ``y`` é a boca e ``z`` é a vertical, com a linha de base (ponto mais
baixo da quilha) em z = 0 na malha gerada.

Espessura de quina e de quilha
------------------------------
A linha de quina é guardada como uma curva *central*; as linhas de quina
externa e interna são a central deslocada de ``± C/2`` na direção da boca,
com ``C`` interpolado suavemente entre as estações (zero na proa). A linha de
quilha deslocada (``offset keel line``) é a quilha deslocada de ``K``. Assim a
espessura é sempre coerente com as estações, sem armazenar curvas redundantes.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

import numpy as np

from app.models import bezier as bz
from app.models.mesh import HullMesh

REGION_NAMES = ("Entrada", "Meio", "Popa")


@dataclass(frozen=True)
class HullParameters:
    """Parâmetros de projeto da Tabela 3.2 (comprimentos em metros, ângulos em graus).

    ``Be``, ``Bm`` e ``Br`` são a boca (largura total) em cada estação.
    ``K`` é a meia-largura do painel plano da quilha e ``Rxx`` é o menor
    raio de curvatura da respectiva curva (``inf`` para curva reta).
    """

    Le: float = 8.0
    Lm: float = 8.0
    Lr: float = 4.0
    Be: float = 6.4
    Bm: float = 6.32
    Br: float = 4.5
    De: float = 3.34
    Dm: float = 3.21
    Dr: float = 2.0
    Fe: float = 2.5
    Fm: float = 2.0
    Fr: float = 1.5
    Fb: float = 1.3
    Ce: float = 0.19
    Cm: float = 0.15
    Cr: float = 0.0
    Rek: float = 3.25
    Res1: float = 2.04
    Res2: float = 3.16
    Rms1: float = 0.88
    Rms2: float = 3.01
    Rrs1: float = 1.42
    Rrs2: float = 1.92
    H: float = 1.5
    K: float = 0.0
    beta: float = 50.0
    alpha: float = 0.0
    theta: float = 30.0

    @classmethod
    def names(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls))

    def as_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in self.names()}

    def replace(self, **changes: float) -> "HullParameters":
        return replace(self, **changes)

    @property
    def total_length(self) -> float:
        return self.Le + self.Lm + self.Lr


#: Descrições (Tabela 3.2) e unidade de cada parâmetro, usadas pela interface.
PARAMETER_INFO: dict[str, tuple[str, str]] = {
    "Le": ("Comprimento da região de entrada", "m"),
    "Lm": ("Comprimento da região do meio", "m"),
    "Lr": ("Comprimento da região de popa", "m"),
    "Be": ("Boca na estação 1", "m"),
    "Bm": ("Boca na estação 2", "m"),
    "Br": ("Boca na estação 3 (espelho)", "m"),
    "De": ("Pontal na estação 1", "m"),
    "Dm": ("Pontal na estação 2", "m"),
    "Dr": ("Pontal na estação 3", "m"),
    "Fe": ("Posição vertical da quina na estação 1", "m"),
    "Fm": ("Posição vertical da quina na estação 2", "m"),
    "Fr": ("Posição vertical da quina na estação 3", "m"),
    "Fb": ("Posição vertical da quina na proa", "m"),
    "Ce": ("Espessura da quina na estação 1", "m"),
    "Cm": ("Espessura da quina na estação 2", "m"),
    "Cr": ("Espessura da quina na estação 3", "m"),
    "Rek": ("Raio mínimo da linha de quilha na entrada", "m"),
    "Res1": ("Raio mínimo da linha superior da estação 1", "m"),
    "Res2": ("Raio mínimo da linha inferior da estação 1", "m"),
    "Rms1": ("Raio mínimo da linha superior da estação 2", "m"),
    "Rms2": ("Raio mínimo da linha inferior da estação 2", "m"),
    "Rrs1": ("Raio mínimo da linha superior da estação 3", "m"),
    "Rrs2": ("Raio mínimo da linha inferior da estação 3", "m"),
    "H": ("Comprimento vertical da linha de roda de proa", "m"),
    "K": ("Espessura da quilha (meia-largura do painel plano)", "m"),
    "beta": ("Ângulo de proa", "°"),
    "alpha": ("Ângulo de tosamento (sheer)", "°"),
    "theta": ("Ângulo de entrada", "°"),
}


@dataclass
class Station:
    """Estação transversal: linha superior, linha inferior e posição ``x``.

    As linhas são Béziers cúbicas em ``(y, z)``. A linha superior vai da borda
    do convés (``S0``) até a quina externa (``S3``); a inferior, da quina
    interna (``S4``) até a quilha deslocada (``S7``). Entre ``S3`` e ``S4``
    fica a linha de espessura da quina; entre ``S7`` e o plano de simetria,
    a de espessura da quilha.
    """

    x: float
    upper: np.ndarray
    lower: np.ndarray

    def copy(self) -> "Station":
        return Station(self.x, self.upper.copy(), self.lower.copy())

    @property
    def chine_thickness(self) -> float:
        return float(self.upper[3, 0] - self.lower[0, 0])

    @property
    def keel_half_width(self) -> float:
        return float(self.lower[3, 0])

    @property
    def keel_z(self) -> float:
        return float(self.lower[3, 1])

    @property
    def chine_center(self) -> tuple[float, float]:
        return (
            float(0.5 * (self.upper[3, 0] + self.lower[0, 0])),
            float(self.upper[3, 1]),
        )


@dataclass(frozen=True)
class MeshResolution:
    """Quantidade de subdivisões dos patches de Coons."""

    longitudinal: int = 54
    upper: int = 10
    lower: int = 14

    @classmethod
    def coarse(cls) -> "MeshResolution":
        return cls(longitudinal=18, upper=5, lower=7)


def _smooth(u: np.ndarray, start: float, end: float) -> np.ndarray:
    """Rampa suave (derivada nula nas pontas) de ``start`` até ``end``."""
    return start + (end - start) * u * u * (3.0 - 2.0 * u)


def _line(a: np.ndarray, b: np.ndarray):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return lambda t: a + (b - a) * np.asarray(t, float)[:, None]


def _point(a: np.ndarray):
    a = np.asarray(a, float)
    return lambda t: np.tile(a, (len(np.asarray(t)), 1))


def _coons(c0, c1, d0, d1, nu: int, nv: int) -> np.ndarray:
    """Patch de Coons bilinearmente misturado, em grade ``(nu+1, nv+1, 3)``.

    ``c0`` e ``c1`` são as curvas em ``v = 0`` e ``v = 1`` (função de ``u``);
    ``d0`` e ``d1`` são as curvas em ``u = 0`` e ``u = 1`` (função de ``v``).
    """
    u = np.linspace(0.0, 1.0, nu + 1)
    v = np.linspace(0.0, 1.0, nv + 1)
    c0u, c1u = c0(u), c1(u)
    d0v, d1v = d0(v), d1(v)
    p00, p10, p01, p11 = c0u[0], c0u[-1], c1u[0], c1u[-1]
    uu = u[:, None, None]
    vv = v[None, :, None]
    ruled_u = (1 - vv) * c0u[:, None, :] + vv * c1u[:, None, :]
    ruled_v = (1 - uu) * d0v[None, :, :] + uu * d1v[None, :, :]
    corners = (
        (1 - uu) * (1 - vv) * p00
        + uu * (1 - vv) * p10
        + (1 - uu) * vv * p01
        + uu * vv * p11
    )
    return ruled_u + ruled_v - corners


class HullModel:
    """Casco paramétrico definido por suas curvas características."""

    def __init__(
        self,
        name: str,
        hull_type: str,
        bow_top: np.ndarray,
        bow_low: np.ndarray,
        chine_depth: float,
        stations: list[Station],
        deck: list[np.ndarray],
        keel: list[np.ndarray],
        chine: list[np.ndarray],
    ) -> None:
        self.name = name
        self.hull_type = hull_type
        self.bow_top = np.asarray(bow_top, float).copy()
        self.bow_low = np.asarray(bow_low, float).copy()
        self.chine_depth = float(chine_depth)
        self.stations = stations
        self.deck = [np.asarray(c, float).copy() for c in deck]
        self.keel = [np.asarray(c, float).copy() for c in keel]
        self.chine = [np.asarray(c, float).copy() for c in chine]
        self.link()

    # ------------------------------------------------------------------
    # Estrutura
    # ------------------------------------------------------------------
    def copy(self) -> "HullModel":
        return HullModel(
            self.name,
            self.hull_type,
            self.bow_top,
            self.bow_low,
            self.chine_depth,
            [station.copy() for station in self.stations],
            self.deck,
            self.keel,
            self.chine,
        )

    def chine_bow_point(self) -> np.ndarray:
        """Ponto da quina na proa: sobre a roda de proa, a ``Fb`` abaixo do convés."""
        height = self.bow_top[1] - self.bow_low[1]
        fraction = 0.0 if height <= 1e-12 else min(self.chine_depth / height, 1.0)
        point = self.bow_top + (self.bow_low - self.bow_top) * fraction
        return np.array([point[0], 0.0, point[1]])

    def link(self) -> None:
        """Faz as extremidades das curvas coincidirem com os pontos âncora.

        Garante a continuidade G0 entre regiões vizinhas: cada estação é a
        extremidade final de uma região e a inicial da seguinte.
        """
        self.deck[0][0] = (self.bow_top[0], 0.0, self.bow_top[1])
        self.keel[0][0] = (self.bow_low[0], 0.0, self.bow_low[1])
        self.chine[0][0] = self.chine_bow_point()
        for index, station in enumerate(self.stations):
            self.deck[index][3] = (station.x, station.upper[0, 0], station.upper[0, 1])
            self.keel[index][3] = (station.x, 0.0, station.lower[3, 1])
            center_y, center_z = station.chine_center
            self.chine[index][3] = (station.x, center_y, center_z)
            station.lower[0, 1] = station.upper[3, 1]
            if index < 2:
                self.deck[index + 1][0] = self.deck[index][3]
                self.keel[index + 1][0] = self.keel[index][3]
                self.chine[index + 1][0] = self.chine[index][3]

    # ------------------------------------------------------------------
    # Leitura dos parâmetros
    # ------------------------------------------------------------------
    def parameters(self) -> HullParameters:
        """Mede os 28 parâmetros de projeto na geometria atual."""
        s1, s2, s3 = self.stations
        bow_x = self.bow_top[0]
        height = self.bow_top[1] - self.bow_low[1]
        rake = self.bow_top[0] - self.bow_low[0]
        first = self.deck[0][1] - self.deck[0][0]
        deck_z_slope = (self.bow_top[1] - s3.upper[0, 1]) / max(
            bow_x - s3.x, 1e-12
        )

        def radius(curve: np.ndarray) -> float:
            return bz.minimum_radius(curve)

        return HullParameters(
            Le=float(bow_x - s1.x),
            Lm=float(s1.x - s2.x),
            Lr=float(s2.x - s3.x),
            Be=float(2 * s1.upper[0, 0]),
            Bm=float(2 * s2.upper[0, 0]),
            Br=float(2 * s3.upper[0, 0]),
            De=float(s1.upper[0, 1] - s1.keel_z),
            Dm=float(s2.upper[0, 1] - s2.keel_z),
            Dr=float(s3.upper[0, 1] - s3.keel_z),
            Fe=float(s1.upper[0, 1] - s1.upper[3, 1]),
            Fm=float(s2.upper[0, 1] - s2.upper[3, 1]),
            Fr=float(s3.upper[0, 1] - s3.upper[3, 1]),
            Fb=float(self.chine_depth),
            Ce=s1.chine_thickness,
            Cm=s2.chine_thickness,
            Cr=s3.chine_thickness,
            Rek=radius(self.keel[0]),
            Res1=radius(s1.upper),
            Res2=radius(s1.lower),
            Rms1=radius(s2.upper),
            Rms2=radius(s2.lower),
            Rrs1=radius(s3.upper),
            Rrs2=radius(s3.lower),
            H=float(height),
            K=s1.keel_half_width,
            beta=float(np.degrees(np.arctan2(height, rake))),
            alpha=float(np.degrees(np.arctan(deck_z_slope))),
            theta=float(np.degrees(np.arctan2(first[1], -first[0]))),
        )

    # ------------------------------------------------------------------
    # Curvas derivadas
    # ------------------------------------------------------------------
    def _fore_aft_values(self, region: int) -> tuple[float, float, float, float]:
        """Espessuras de quina e de quilha na frente e atrás da região."""
        aft = self.stations[region]
        if region == 0:
            return 0.0, aft.chine_thickness, 0.0, aft.keel_half_width
        fore = self.stations[region - 1]
        return (
            fore.chine_thickness,
            aft.chine_thickness,
            fore.keel_half_width,
            aft.keel_half_width,
        )

    def region_curves(self, region: int, u: np.ndarray) -> dict[str, np.ndarray]:
        """Curvas longitudinais da região em ``u`` (``(n, 3)`` cada)."""
        u = np.asarray(u, float)
        c_fore, c_aft, k_fore, k_aft = self._fore_aft_values(region)
        half = 0.5 * _smooth(u, c_fore, c_aft)
        keel_offset = _smooth(u, k_fore, k_aft)
        center = bz.evaluate(self.chine[region], u)
        keel = bz.evaluate(self.keel[region], u)
        side = np.zeros_like(center)
        side[:, 1] = half
        offset = np.zeros_like(keel)
        offset[:, 1] = keel_offset
        return {
            "deck": bz.evaluate(self.deck[region], u),
            "chine_outer": center + side,
            "chine_inner": center - side,
            "keel_offset": keel + offset,
            "keel": keel,
        }

    def station_lines(self, index: int, nu: int, nv: int) -> dict[str, np.ndarray]:
        """Linhas 3D da estação ``index``: superior, inferior e as de espessura."""
        station = self.stations[index]

        def lift(points: np.ndarray) -> np.ndarray:
            return np.column_stack(
                (np.full(len(points), station.x), points[:, 0], points[:, 1])
            )

        upper = lift(bz.evaluate(station.upper, np.linspace(0, 1, nu + 1)))
        lower = lift(bz.evaluate(station.lower, np.linspace(0, 1, nv + 1)))
        return {
            "upper": upper,
            "lower": lower,
            "chine": np.vstack((upper[-1], lower[0])),
            "keel": np.vstack((lower[-1], [station.x, 0.0, lower[-1, 2]])),
        }

    # ------------------------------------------------------------------
    # Malha
    # ------------------------------------------------------------------
    def baseline_offset(self) -> np.ndarray:
        """Deslocamento que leva o espelho a x = 0 e a quilha mais baixa a z = 0."""
        u = np.linspace(0, 1, 120)
        lowest = min(float(np.min(bz.evaluate(curve, u)[:, 2])) for curve in self.keel)
        return np.array([-self.stations[2].x, 0.0, -lowest])

    def build_mesh(
        self,
        resolution: MeshResolution | None = None,
        close_transom: bool = True,
        closed_deck: bool = False,
    ) -> HullMesh:
        """Gera a malha: patches de Coons de cada região, espelhados em ``y``.

        Args:
            resolution: subdivisões dos patches.
            close_transom: tampa o espelho de popa (necessário para volumes).
            closed_deck: fecha o convés, tornando a malha estanque.
        """
        resolution = resolution or MeshResolution()
        offset = self.baseline_offset()
        lengths = [
            abs(self.deck[r][0, 0] - self.deck[r][3, 0]) for r in range(3)
        ]
        total = max(sum(lengths), 1e-9)
        nus = [max(6, int(round(resolution.longitudinal * l / total))) for l in lengths]
        nvu, nvl = resolution.upper, resolution.lower

        grids: list[np.ndarray] = []
        for region in range(3):
            nu = nus[region]
            curves = lambda key: (lambda u, key=key: self.region_curves(region, u)[key])
            aft_lines = self._station_callables(region)
            if region == 0:
                top = np.array([self.bow_top[0], 0.0, self.bow_top[1]])
                chine_pt = self.chine_bow_point()
                low = np.array([self.bow_low[0], 0.0, self.bow_low[1]])
                fore_upper = _line(top, chine_pt)
                fore_chine = _point(chine_pt)
                fore_lower = _line(chine_pt, low)
                fore_keel = _point(low)
            else:
                fore_upper, fore_lower, fore_chine, fore_keel = self._station_callables(
                    region - 1
                )[:4]
            aft_upper, aft_lower, aft_chine, aft_keel = aft_lines[:4]
            grids.append(
                _coons(curves("deck"), curves("chine_outer"), fore_upper, aft_upper, nu, nvu)
            )
            grids.append(
                _coons(curves("chine_outer"), curves("chine_inner"), fore_chine, aft_chine, nu, 1)
            )
            grids.append(
                _coons(curves("chine_inner"), curves("keel_offset"), fore_lower, aft_lower, nu, nvl)
            )
            grids.append(
                _coons(curves("keel_offset"), curves("keel"), fore_keel, aft_keel, nu, 1)
            )

        vertices: list[np.ndarray] = []
        quads: list[np.ndarray] = []
        base = 0

        def add_grid(grid: np.ndarray, flip: bool, mirror: bool) -> None:
            nonlocal base
            nu, nv = grid.shape[0] - 1, grid.shape[1] - 1
            points = grid.reshape(-1, 3).copy()
            if mirror:
                points[:, 1] *= -1.0
            index = np.arange((nu + 1) * (nv + 1)).reshape(nu + 1, nv + 1) + base
            quad = np.stack(
                (index[:-1, :-1], index[1:, :-1], index[1:, 1:], index[:-1, 1:]),
                axis=-1,
            ).reshape(-1, 4)
            # u cresce para a popa e v para baixo: a normal aponta para dentro
            # no bordo de boreste, então inverte-se a ordem; o espelhamento
            # inverte de novo.
            if flip != mirror:
                quad = quad[:, ::-1]
            vertices.append(points)
            quads.append(quad)
            base += len(points)

        for grid in grids:
            add_grid(grid, True, False)
            add_grid(grid, True, True)

        if close_transom:
            cap = self._transom_cap(nvu, nvl)
            add_grid(cap, False, False)
        if closed_deck:
            add_grid(self._deck_cap(nus), False, False)

        mesh = HullMesh.weld(np.vstack(vertices) + offset, np.vstack(quads))
        return mesh

    def _station_callables(self, index: int):
        station = self.stations[index]
        x = station.x

        def lift(points: np.ndarray) -> np.ndarray:
            return np.column_stack((np.full(len(points), x), points[:, 0], points[:, 1]))

        upper = lambda v: lift(bz.evaluate(station.upper, v))
        lower = lambda v: lift(bz.evaluate(station.lower, v))
        chine = _line(
            [x, station.upper[3, 0], station.upper[3, 1]],
            [x, station.lower[0, 0], station.lower[0, 1]],
        )
        keel = _line(
            [x, station.lower[3, 0], station.lower[3, 1]],
            [x, 0.0, station.lower[3, 1]],
        )
        return upper, lower, chine, keel

    def _transom_cap(self, nvu: int, nvl: int) -> np.ndarray:
        """Faixas horizontais do espelho de popa, em grade ``(rungs, 2, 3)``.

        Cada degrau liga pontos simétricos (bombordo e boreste); a região
        entre degraus consecutivos vira um quadrilátero. A tampa só cobre
        a seção da estação 3 e é fechada pelo sentido de ``-x``.
        """
        lines = self.station_lines(2, nvu, nvl)
        outline = np.vstack(
            (lines["upper"], lines["lower"], lines["keel"][1:])
        )
        right = outline.copy()
        left = outline.copy()
        left[:, 1] *= -1.0
        grid = np.stack((right, left), axis=1)  # (rungs, 2, 3): v = 0 -> 1
        return grid

    def _deck_cap(self, nus: list[int]) -> np.ndarray:
        rows = []
        for region in range(3):
            u = np.linspace(0.0, 1.0, nus[region] + 1)
            line = bz.evaluate(self.deck[region], u)
            rows.append(line if region == 0 else line[1:])
        deck = np.vstack(rows)
        left = deck.copy()
        left[:, 1] *= -1.0
        return np.stack((deck, left), axis=1)

    # ------------------------------------------------------------------
    # Elementos auxiliares de exibição
    # ------------------------------------------------------------------
    def feature_curves(self, samples: int = 60) -> dict[str, np.ndarray]:
        """Polilinhas das curvas características (lado de boreste), deslocadas."""
        offset = self.baseline_offset()
        u = np.linspace(0.0, 1.0, samples)
        curves: dict[str, np.ndarray] = {}
        top = np.array([self.bow_top[0], 0.0, self.bow_top[1]])
        low = np.array([self.bow_low[0], 0.0, self.bow_low[1]])
        curves["Roda de proa"] = np.vstack((top, low)) + offset
        for region in range(3):
            name = REGION_NAMES[region]
            data = self.region_curves(region, u)
            curves[f"Convés · {name}"] = data["deck"] + offset
            curves[f"Quina externa · {name}"] = data["chine_outer"] + offset
            curves[f"Quina interna · {name}"] = data["chine_inner"] + offset
            curves[f"Quilha · {name}"] = data["keel"] + offset
            curves[f"Quilha deslocada · {name}"] = data["keel_offset"] + offset
        for index in range(3):
            lines = self.station_lines(index, samples, samples)
            curves[f"Estação {index + 1} · linha superior"] = lines["upper"] + offset
            curves[f"Estação {index + 1} · linha inferior"] = lines["lower"] + offset
        return curves

    def control_polygons(self) -> dict[str, np.ndarray]:
        """Polígonos de controle das curvas principais (boreste), deslocados."""
        offset = self.baseline_offset()
        polygons: dict[str, np.ndarray] = {}
        for region in range(3):
            name = REGION_NAMES[region]
            polygons[f"Convés · {name}"] = self.deck[region] + offset
            polygons[f"Quina · {name}"] = self.chine[region] + offset
            polygons[f"Quilha · {name}"] = self.keel[region] + offset
        for index, station in enumerate(self.stations):
            for key, curve in (("superior", station.upper), ("inferior", station.lower)):
                points = np.column_stack(
                    (np.full(4, station.x), curve[:, 0], curve[:, 1])
                )
                polygons[f"Estação {index + 1} · {key}"] = points + offset
        return polygons

    def curvature_curves(self) -> dict[str, np.ndarray]:
        """Controles (Béziers) cuja distribuição de curvatura a tese examina."""
        curves = {}
        for region in range(3):
            name = REGION_NAMES[region]
            curves[f"Linha de convés · {name}"] = self.deck[region]
            curves[f"Linha de quina · {name}"] = self.chine[region]
            curves[f"Linha de quilha · {name}"] = self.keel[region]
        return curves

    def section_polylines(self, count: int = 25) -> list[np.ndarray]:
        """Seções transversais (``x`` constante) da malha, para inspeção de fairness."""
        mesh = self.build_mesh(MeshResolution.coarse())
        x_min, x_max = mesh.vertices[:, 0].min(), mesh.vertices[:, 0].max()
        sections = []
        for x in np.linspace(x_min, x_max, count + 2)[1:-1]:
            segments = _slice_segments(mesh, 0, x)
            if len(segments):
                sections.append(segments)
        return sections


def _slice_segments(mesh: HullMesh, axis: int, value: float) -> np.ndarray:
    """Segmentos ``(n, 2, 3)`` da interseção da malha com um plano ``eixo = valor``."""
    triangles = mesh.vertices[mesh.triangulated()]
    side = triangles[:, :, axis] - value
    segments = []
    for edge in ((0, 1), (1, 2), (2, 0)):
        a, b = edge
        crossing = (side[:, a] * side[:, b]) < 0
        t = side[crossing, a] / (side[crossing, a] - side[crossing, b])
        point = triangles[crossing, a] + t[:, None] * (
            triangles[crossing, b] - triangles[crossing, a]
        )
        segments.append((np.nonzero(crossing)[0], point))
    by_triangle: dict[int, list[np.ndarray]] = {}
    for indices, points in segments:
        for index, point in zip(indices, points):
            by_triangle.setdefault(int(index), []).append(point)
    pairs = [np.array(points[:2]) for points in by_triangle.values() if len(points) >= 2]
    return np.array(pairs) if pairs else np.empty((0, 2, 3))
