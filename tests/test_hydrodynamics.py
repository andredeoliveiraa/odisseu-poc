"""Testes da hidrostática e da resistência (Michell + ITTC-57).

O casco de Wigley, ``y = B/2 (1 − (2x/L)²)(1 − (z/T)²)``, é o mesmo usado no
artigo do ShipD para validar a integral de Michell; suas grandezas
hidrostáticas têm forma fechada.
"""

from __future__ import annotations

import unittest

import numpy as np

from app.hull_generator import ChineOptions, HullGenerator, StepOptions
from app.models import hydrodynamics as hd

L, B, T = 1.0, 0.1, 0.0625


def wigley_half_breadth(x: np.ndarray, z: np.ndarray) -> np.ndarray:
    return B / 2 * (1 - (2 * x / L) ** 2) * (1 - (z / T) ** 2)


def wigley_mesh(nx: int = 161, nz: int = 41) -> tuple[np.ndarray, np.ndarray]:
    """Malha fechada abaixo de z = 0 (os dois bordos se encontram na quilha)."""
    x = np.linspace(-L / 2, L / 2, nx)
    z = np.linspace(-T, 0.0, nz)
    grid_x, grid_z = np.meshgrid(x, z, indexing="ij")
    y = wigley_half_breadth(grid_x, grid_z)
    points = np.concatenate(
        [np.stack((grid_x, side * y, grid_z), axis=-1).reshape(-1, 3) for side in (1, -1)]
    )
    i, j = np.meshgrid(np.arange(nx - 1), np.arange(nz - 1), indexing="ij")
    a = (i * nz + j).ravel()
    b, c, d = a + nz, a + nz + 1, a + 1
    starboard = np.vstack((np.column_stack((a, c, b)), np.column_stack((a, d, c))))
    offset = nx * nz
    port = np.vstack(
        (np.column_stack((a, b, c)), np.column_stack((a, c, d)))
    ) + offset
    return points, np.vstack((starboard, port))


def wigley_offsets(nx: int, nz: int) -> hd.OffsetGrid:
    x = np.linspace(-L / 2, L / 2, nx)
    z = np.linspace(-T, 0.0, nz)
    grid_x, grid_z = np.meshgrid(x, z, indexing="ij")
    return hd.OffsetGrid(x, z, wigley_half_breadth(grid_x, grid_z))


def wave_coefficient(froude: float, offsets: hd.OffsetGrid) -> float:
    speed = froude * np.sqrt(hd.GRAVITY * L)
    resistance = hd.michell_wave_resistance(offsets, speed)
    return resistance / (0.5 * hd.SEAWATER_DENSITY * speed**2 * 0.1487 * L**2)


class WigleyHydrostaticsTests(unittest.TestCase):
    def setUp(self) -> None:
        points, triangles = wigley_mesh()
        offsets = wigley_offsets(201, 41)
        self.result = hd.compute_hydrostatics(points, triangles, hd.midship_area(offsets))

    def test_volume_and_waterplane_match_closed_form(self) -> None:
        self.assertAlmostEqual(self.result.volume, 4 / 9 * L * B * T, delta=2e-6)
        self.assertAlmostEqual(self.result.waterplane_area, 2 / 3 * L * B, delta=5e-5)
        self.assertAlmostEqual(self.result.block_coefficient, 4 / 9, places=3)
        self.assertAlmostEqual(self.result.prismatic_coefficient, 2 / 3, places=3)
        self.assertAlmostEqual(self.result.midship_coefficient, 2 / 3, places=3)

    def test_centers_and_metacentric_radius_match_closed_form(self) -> None:
        inertia = (2 / 3) * (B / 2) ** 3 * L * 16 / 35
        self.assertAlmostEqual(self.result.vcb, -3 * T / 8, places=5)
        self.assertAlmostEqual(self.result.lcb, 0.0, places=4)
        self.assertAlmostEqual(self.result.bm, inertia / (4 / 9 * L * B * T), places=4)

    def test_wetted_area_matches_literature(self) -> None:
        # S/L² = 0,1487 para o Wigley de L/B = 10, L/T = 16.
        self.assertAlmostEqual(self.result.wetted_area / L**2, 0.1487, delta=0.0005)


class MichellIntegralTests(unittest.TestCase):
    def test_wigley_result_converges_with_the_grid(self) -> None:
        for froude in (0.25, 0.30, 0.40):
            with self.subTest(froude=froude):
                coarse = wave_coefficient(froude, wigley_offsets(101, 21))
                fine = wave_coefficient(froude, wigley_offsets(201, 41))
                self.assertAlmostEqual(coarse / fine, 1.0, delta=0.005)

    def test_wigley_shows_the_classic_hump_and_hollow(self) -> None:
        offsets = wigley_offsets(201, 41)
        hump, hollow, rise = (wave_coefficient(f, offsets) for f in (0.30, 0.35, 0.45))
        self.assertGreater(hump, hollow)
        self.assertGreater(rise, hump)
        # Ordem de grandeza da teoria do navio delgado para o Wigley.
        self.assertTrue(1e-3 < hump < 4e-3)

    def test_ittc57_friction_line(self) -> None:
        self.assertAlmostEqual(hd.ittc57_friction_coefficient(1e7), 0.075 / 25.0)


class GeneratedHullPerformanceTests(unittest.TestCase):
    def evaluate(self, **parameters):
        generator = HullGenerator(**parameters)
        offsets = hd.underwater_offsets(*generator.half_sections())
        mesh = generator.generate_mesh()
        result = hd.compute_hydrostatics(
            mesh.vertices, mesh.triangulated(), hd.midship_area(offsets)
        )
        return offsets, result

    def test_mesh_and_offsets_give_the_same_volume(self) -> None:
        for parameters in (
            {},
            {"transom_ratio": 0.0},
            {"chine": ChineOptions(), "steps": (StepOptions(0.4), StepOptions(0.62))},
        ):
            with self.subTest(**{key: str(value) for key, value in parameters.items()}):
                offsets, result = self.evaluate(**parameters)
                volume = 2 * np.trapz(np.trapz(offsets.half_breadth, offsets.z, axis=1), offsets.x)
                self.assertAlmostEqual(volume / result.volume, 1.0, delta=0.01)

    def test_hydrostatics_of_the_default_hull(self) -> None:
        _, result = self.evaluate(sheer_bow=0.0)

        self.assertAlmostEqual(result.waterline_length, 12.0, places=6)
        self.assertAlmostEqual(result.draft, 1.8, places=6)
        self.assertAlmostEqual(result.displacement, 1.025 * result.volume)
        self.assertTrue(0.3 < result.block_coefficient < 0.8)
        # Popa com espelho: o centro de carena fica a ré da meia-nau.
        self.assertLess(result.lcb, 0.0)

    def test_resistance_curve_components_add_up(self) -> None:
        offsets, result = self.evaluate()
        speeds = np.array([2.0, 3.0, 4.0])
        curve = hd.resistance_curve(offsets, result, speeds)

        for point, speed in zip(curve, speeds):
            self.assertAlmostEqual(point.total, point.wave + point.friction)
            self.assertAlmostEqual(point.effective_power, point.total * speed)
            self.assertGreater(point.wave, 0.0)
        self.assertLess(curve[0].total, curve[-1].total)

    def test_beamy_hull_gets_a_validity_warning(self) -> None:
        _, result = self.evaluate()
        notes = hd.validity_notes(result, maximum_froude=0.45)

        self.assertEqual(len(notes), 1)
        self.assertIn("L/B", notes[0])
        self.assertEqual(len(hd.validity_notes(result, maximum_froude=0.8)), 2)


if __name__ == "__main__":
    unittest.main()
