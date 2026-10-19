"""Testes da hidrostática (Tabela 3.6)."""

from __future__ import annotations

import unittest

import numpy as np

from app.models.hull_model import MeshResolution
from app.models.hull_types import (
    DISPLACEMENT,
    PLANING,
    SEMI_DISPLACEMENT,
    initial_hull,
)
from app.models.hydrostatics import (
    COLUMN_INFO,
    HydrostaticResult,
    compute_hydrostatics,
    default_drafts,
    hydrostatic_table,
    maximum_draft,
)
from app.models.mesh import HullMesh


def box_mesh(length: float, beam: float, height: float) -> HullMesh:
    """Caixa fechada, com normais para fora: x ∈ [0, L], y ∈ [−B/2, B/2], z ∈ [0, H]."""
    vertices = np.array(
        [[x, y, z] for x in (0, length) for y in (-beam / 2, beam / 2) for z in (0, height)],
        dtype=float,
    )

    def index(x: int, y: int, z: int) -> int:
        return x * 4 + y * 2 + z

    quads = np.array(
        [
            [index(0, 0, 0), index(0, 1, 0), index(0, 1, 1), index(0, 0, 1)],
            [index(1, 0, 0), index(1, 0, 1), index(1, 1, 1), index(1, 1, 0)],
            [index(0, 0, 0), index(1, 0, 0), index(1, 1, 0), index(0, 1, 0)],
            [index(0, 0, 1), index(0, 1, 1), index(1, 1, 1), index(1, 0, 1)],
            [index(0, 0, 0), index(0, 0, 1), index(1, 0, 1), index(1, 0, 0)],
            [index(0, 1, 0), index(1, 1, 0), index(1, 1, 1), index(0, 1, 1)],
        ]
    )
    center = vertices.mean(axis=0)
    for row, quad in enumerate(quads):
        points = vertices[quad]
        normal = np.cross(points[1] - points[0], points[3] - points[0])
        if normal @ (points.mean(axis=0) - center) < 0:
            quads[row] = quad[::-1]
    return HullMesh(vertices, quads)


class BoxHydrostaticsTests(unittest.TestCase):
    """Uma caixa tem resultados analíticos conhecidos."""

    def test_box_matches_closed_form_values(self) -> None:
        length, beam, height, draft = 10.0, 4.0, 3.0, 1.5
        result = compute_hydrostatics(box_mesh(length, beam, height), draft)

        self.assertAlmostEqual(result.V, length * beam * draft)
        self.assertAlmostEqual(result.Aw, length * beam)
        self.assertAlmostEqual(result.LWL, length)
        self.assertAlmostEqual(result.BWL, beam)
        self.assertAlmostEqual(result.KB, draft / 2)
        self.assertAlmostEqual(result.LCB, length / 2)
        self.assertAlmostEqual(result.LCF, length / 2)
        self.assertAlmostEqual(result.IT, length * beam**3 / 12)
        self.assertAlmostEqual(result.IL, beam * length**3 / 12)
        self.assertAlmostEqual(result.Ax, beam * draft)
        self.assertAlmostEqual(result.BM, beam**2 / (12 * draft))
        self.assertAlmostEqual(result.KM, draft / 2 + beam**2 / (12 * draft))

    def test_box_coefficients_are_all_one(self) -> None:
        result = compute_hydrostatics(box_mesh(8.0, 3.0, 2.0), 1.0)

        for name in ("Cp", "Cm", "Cw", "Cb"):
            self.assertAlmostEqual(getattr(result, name), 1.0, places=9)

    def test_invalid_drafts_are_rejected(self) -> None:
        mesh = box_mesh(8.0, 3.0, 2.0)
        for draft in (0.0, -1.0, 2.5):
            with self.subTest(draft=draft), self.assertRaises(ValueError):
                compute_hydrostatics(mesh, draft)


class HullHydrostaticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = initial_hull(SEMI_DISPLACEMENT)
        cls.results = hydrostatic_table(cls.model, default_drafts(cls.model))

    def test_table_has_every_column_of_table_3_6(self) -> None:
        self.assertEqual(HydrostaticResult.columns(), tuple(COLUMN_INFO))
        self.assertEqual(
            set(COLUMN_INFO),
            {"T", "LWL", "BWL", "V", "Aw", "LCB", "KB", "LCF", "IL", "IT",
             "Ax", "BM", "KM", "Cp", "Cm", "Cw", "Cb"},
        )

    def test_displacement_grows_with_draft(self) -> None:
        volumes = [result.V for result in self.results]
        areas = [result.Ax for result in self.results]

        self.assertEqual(volumes, sorted(volumes))
        self.assertEqual(areas, sorted(areas))
        self.assertTrue(all(v > 0 for v in volumes))

    def test_values_are_physically_consistent(self) -> None:
        for result in self.results:
            with self.subTest(draft=result.T):
                self.assertTrue(0.0 < result.KB < result.T)
                self.assertTrue(0.0 < result.LCB < result.LWL * 1.3)
                for name in ("Cp", "Cm", "Cw", "Cb"):
                    self.assertTrue(0.0 < getattr(result, name) <= 1.0, name)
                self.assertAlmostEqual(result.KM, result.KB + result.BM)
                self.assertAlmostEqual(result.BM, result.IT / result.V)
                self.assertAlmostEqual(result.Cb, result.Cp * result.Cm, delta=0.02)

    def test_volume_is_independent_of_mesh_resolution(self) -> None:
        coarse = compute_hydrostatics(self.model.build_mesh(MeshResolution.coarse()), 1.3)
        fine = compute_hydrostatics(self.model.build_mesh(MeshResolution(96, 16, 24)), 1.3)

        self.assertAlmostEqual(coarse.V, fine.V, delta=0.01 * fine.V)
        self.assertAlmostEqual(coarse.Aw, fine.Aw, delta=0.01 * fine.Aw)

    def test_table_is_available_for_every_hull_type(self) -> None:
        for hull_type in (PLANING, DISPLACEMENT):
            with self.subTest(hull=hull_type):
                model = initial_hull(hull_type)
                results = hydrostatic_table(model, default_drafts(model))

                self.assertEqual(len(results), 3)
                self.assertTrue(all(r.V > 0 for r in results))

    def test_draft_beyond_the_hull_is_reported(self) -> None:
        with self.assertRaises(ValueError):
            hydrostatic_table(self.model, [maximum_draft(self.model) + 0.5])

    def test_widening_the_hull_increases_the_displacement(self) -> None:
        from app.models.shape_operators import apply_parameters

        wider = apply_parameters(self.model, {"Be": 7.4, "Bm": 7.3})
        base = hydrostatic_table(self.model, [1.5])[0]
        modified = hydrostatic_table(wider, [1.5])[0]

        self.assertGreater(modified.V, base.V)
        self.assertGreater(modified.BWL, base.BWL)
        self.assertGreater(modified.IT, base.IT)


COLUMNS = ("LWL", "BWL", "V", "Aw", "LCB", "KB", "LCF", "IL", "IT", "Ax", "BM", "KM", "Cp", "Cm", "Cw", "Cb")
THESIS_DRAFTS = (0.74, 1.24, 1.74)

#: Tabela 3.6 (tese), uma linha por calado. KB e KM saem do texto original, em que
#: KB é contado a partir da linha d'água; ``thesis_rows`` converte para a quilha.
THESIS_INPUT = (
    (13.89, 3.78, 13.48, 38.03, 8.369, 0.235, 8.337, 402.4, 33.31, 1.606, 2.470, 2.706, 0.604, 0.574, 0.724, 0.347),
    (16.86, 5.54, 38.80, 63.76, 8.330, 0.405, 8.272, 961.5, 111.11, 3.883, 2.863, 3.268, 0.592, 0.565, 0.682, 0.335),
    (18.38, 6.00, 76.03, 82.65, 8.303, 0.579, 8.324, 1616.0, 185.16, 6.769, 2.435, 3.014, 0.611, 0.648, 0.749, 0.396),
)
THESIS_KEEL = (
    (13.89, 3.98, 17.76, 42.01, 8.467, 0.270, 8.386, 492.11, 40.46, 2.010, 2.278, 2.548, 0.636, 0.682, 0.760, 0.434),
    (16.86, 5.54, 44.32, 64.96, 8.377, 0.448, 8.258, 1026.3, 112.21, 4.311, 2.531, 2.979, 0.609, 0.629, 0.698, 0.384),
    (18.38, 6.00, 81.85, 82.74, 8.325, 0.623, 8.326, 1622.8, 185.22, 7.194, 2.262, 2.886, 0.620, 0.689, 0.752, 0.427),
)
THESIS_ELONGATION = (
    (16.89, 3.90, 16.87, 47.33, 9.839, 0.236, 9.812, 721.44, 44.38, 1.663, 2.629, 2.865, 0.600, 0.576, 0.718, 0.346),
    (19.86, 5.70, 48.09, 77.86, 9.805, 0.407, 9.754, 1621.02, 145.53, 4.011, 3.025, 3.433, 0.603, 0.567, 0.687, 0.342),
    (21.36, 6.16, 93.32, 100.07, 9.776, 0.584, 9.780, 2650.2, 241.63, 6.985, 2.589, 3.173, 0.625, 0.651, 0.760, 0.407),
)
THESIS_WIDENING = (
    (13.89, 5.02, 16.43, 47.41, 8.652, 0.231, 8.758, 485.0, 67.089, 2.050, 4.081, 4.312, 0.577, 0.551, 0.679, 0.318),
    (16.86, 6.98, 47.90, 77.82, 8.765, 0.401, 8.840, 1168.5, 202.59, 5.013, 4.229, 4.631, 0.566, 0.579, 0.661, 0.328),
    (18.38, 7.46, 92.19, 97.02, 8.797, 0.584, 8.848, 1874.5, 303.85, 8.548, 3.295, 3.880, 0.586, 0.658, 0.707, 0.386),
)


def thesis_rows(rows):
    """Converte KB (da linha d'água, como na tese) e KM = KB + BM para a convenção da quilha."""
    converted = []
    for draft, row in zip(THESIS_DRAFTS, rows):
        row = list(row)
        row[5] = draft - row[5]
        row[11] = row[5] + row[10]
        converted.append(row)
    return np.array(converted)


def table_of(model) -> np.ndarray:
    mesh = model.build_mesh()
    return np.array(
        [[getattr(compute_hydrostatics(mesh, draft), name) for name in COLUMNS] for draft in THESIS_DRAFTS]
    )


class ThesisTableTests(unittest.TestCase):
    """Compara o casco SD e três operadores com a Tabela 3.6 da tese."""

    @classmethod
    def setUpClass(cls) -> None:
        from app.models.shape_operators import apply_parameters

        cls.model = initial_hull(SEMI_DISPLACEMENT)
        cls.apply = staticmethod(apply_parameters)
        cls.parameters = cls.model.parameters()

    def assert_close_to(self, model, rows, worst: float, median: float) -> None:
        error = np.abs(table_of(model) / thesis_rows(rows) - 1.0)
        self.assertLess(float(error.max()), worst, msg=dict(zip(COLUMNS, error.max(axis=0).round(2))))
        self.assertLess(float(np.median(error)), median)

    def test_input_hull_matches_the_thesis_hydrostatics(self) -> None:
        self.assert_close_to(self.model, THESIS_INPUT, worst=0.15, median=0.05)

    def test_keel_thickness_operator_matches_the_thesis(self) -> None:
        self.assert_close_to(self.apply(self.model, {"K": 0.5}), THESIS_KEEL, worst=0.15, median=0.05)

    def test_elongation_operator_matches_the_thesis(self) -> None:
        longer = self.apply(self.model, {"Lm": self.parameters.Lm + 3.0})

        self.assert_close_to(longer, THESIS_ELONGATION, worst=0.25, median=0.08)
        # A tese registra o alongamento exato de 3 m no comprimento na linha d'água.
        gain = table_of(longer)[:, 0] - table_of(self.model)[:, 0]
        np.testing.assert_allclose(gain, 3.0, atol=0.15)

    def test_widening_operator_matches_the_thesis(self) -> None:
        self.assert_close_to(
            self.apply(self.model, {"Be": self.parameters.Be + 1.0}), THESIS_WIDENING, worst=0.30, median=0.08
        )

    def test_default_drafts_are_the_ones_of_table_3_6(self) -> None:
        self.assertEqual(default_drafts(self.model), THESIS_DRAFTS)

    def test_keel_and_metacentre_follow_the_naval_convention(self) -> None:
        """KB e KM contados da quilha: KB < T e KM = KB + BM."""
        mesh = self.model.build_mesh()
        for draft in THESIS_DRAFTS:
            result = compute_hydrostatics(mesh, draft)
            self.assertTrue(0.4 * draft < result.KB < 0.8 * draft)
            self.assertAlmostEqual(result.KM, result.KB + result.BM)


if __name__ == "__main__":
    unittest.main()
