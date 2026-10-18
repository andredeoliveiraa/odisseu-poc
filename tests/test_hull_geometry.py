"""Testes da geometria e das restrições independentes da interface Qt."""

from __future__ import annotations

import unittest

import numpy as np

from app.hull_generator import ChineOptions, HullGenerator, StepOptions
from app.models.constraints import HullConstraintValidator
from app.models.transforms import TransformParameters, transformation_matrix


def closed_surface_report(mesh) -> tuple[int, float]:
    """Retorna (arestas abertas, volume) após fundir vértices coincidentes."""
    _, inverse = np.unique(np.round(mesh.vertices, 9), axis=0, return_inverse=True)
    points = np.round(mesh.vertices, 9)
    triangles = inverse.ravel()[mesh.triangulated()]
    triangles = triangles[
        (triangles[:, 0] != triangles[:, 1])
        & (triangles[:, 1] != triangles[:, 2])
        & (triangles[:, 0] != triangles[:, 2])
    ]
    edges = np.sort(
        np.vstack((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])),
        axis=1,
    )
    _, counts = np.unique(edges, axis=0, return_counts=True)
    unique_points = np.unique(points, axis=0)
    corners = unique_points[triangles]
    volume = np.einsum(
        "ij,ij->i", corners[:, 0], np.cross(corners[:, 1], corners[:, 2])
    ).sum() / 6.0
    return int((counts != 2).sum()), float(volume)


def shell_grid(generator: HullGenerator) -> np.ndarray:
    """Vértices do costado organizados por (estação, ponto da seção, xyz)."""
    count = generator.points_per_station
    rows = generator.row_count
    return generator.generate_mesh().vertices[: rows * count].reshape(rows, count, 3)


class HullGeneratorTests(unittest.TestCase):
    def test_default_mesh_has_expected_topology(self) -> None:
        generator = HullGenerator()
        mesh = generator.generate_mesh()
        count = generator.points_per_station

        transom_interior = (count // 2) * (generator._cross_columns - 2)

        self.assertEqual(count, 33 + 2 * 4)
        self.assertEqual(mesh.vertices.shape, (64 * count + transom_interior, 3))
        self.assertGreaterEqual(int(mesh.faces.min()), 0)
        self.assertLess(int(mesh.faces.max()), len(mesh.vertices))

    def test_declared_dimensions_are_reached(self) -> None:
        generator = HullGenerator(
            total_length=12.0, beam=4.0, draft=1.8, freeboard=1.1, sheer_bow=0.0
        )
        mesh = generator.generate_mesh()

        np.testing.assert_allclose(np.ptp(mesh.vertices[:, 0]), 12.0)
        np.testing.assert_allclose(np.ptp(mesh.vertices[:, 1]), 4.0)
        np.testing.assert_allclose(mesh.vertices[:, 2].min(), -1.8)
        np.testing.assert_allclose(mesh.vertices[:, 2].max(), 1.1)

    def test_hull_is_a_closed_outward_surface(self) -> None:
        for parameters in (
            {},
            {"transom_ratio": 0.0},
            {"deadrise": 30.0, "station_concavity": 1.0},
            {"stations": 4, "section_points": 5},
        ):
            with self.subTest(**parameters):
                open_edges, volume = closed_surface_report(
                    HullGenerator(closed_deck=True, **parameters).generate_mesh()
                )
                self.assertEqual(open_edges, 0)
                self.assertGreater(volume, 0.0)

    def test_transom_widens_the_stern_and_adds_volume(self) -> None:
        pointed = HullGenerator(transom_ratio=0.0, closed_deck=True)
        transom = HullGenerator(transom_ratio=0.7, closed_deck=True)
        stern = transom.generate_mesh().vertices[: transom.points_per_station]

        np.testing.assert_allclose(np.ptp(stern[:, 1]), 0.7 * 4.0)
        self.assertGreater(
            closed_surface_report(transom.generate_mesh())[1],
            closed_surface_report(pointed.generate_mesh())[1],
        )

    def test_open_deck_leaves_only_the_deck_edge_open(self) -> None:
        generator = HullGenerator(closed_deck=False, sheer_bow=0.0)
        mesh = generator.generate_mesh()
        closed = HullGenerator(closed_deck=True, sheer_bow=0.0).generate_mesh()

        self.assertEqual(
            len(closed.faces) - len(mesh.faces),
            (generator.stations - 1) * (generator._cross_columns - 1),
        )
        points = np.round(mesh.vertices, 9)
        unique_points, inverse = np.unique(points, axis=0, return_inverse=True)
        triangles = inverse.ravel()[mesh.triangulated()]
        edges = np.sort(
            np.vstack((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])),
            axis=1,
        )
        edges = edges[edges[:, 0] != edges[:, 1]]
        unique_edges, counts = np.unique(edges, axis=0, return_counts=True)
        open_edges = unique_edges[counts == 1]

        self.assertGreater(len(open_edges), 0)
        np.testing.assert_allclose(unique_points[open_edges][..., 2], generator.freeboard)

    def test_deadrise_sets_the_bottom_angle_at_the_keel(self) -> None:
        generator = HullGenerator(deadrise=20.0, stations=5, section_points=65)
        vertices = generator.generate_mesh().vertices
        count = generator.points_per_station
        midship = vertices[2 * count : 3 * count]
        keel = midship[count // 2]
        beside = midship[count // 2 + 1]

        angle = np.degrees(np.arctan2(beside[2] - keel[2], beside[1] - keel[1]))
        self.assertAlmostEqual(angle, 20.0, delta=1.5)
        flat = HullGenerator(deadrise=0.0, stations=5, section_points=65).generate_mesh().vertices
        flat_mid = flat[2 * count : 3 * count]
        self.assertLess(flat_mid[count // 2 + 1, 2] - flat_mid[count // 2, 2], 0.01)

    def test_invalid_dimensions_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            HullGenerator(total_length=5.0, midship_length=6.0)
        with self.assertRaises(ValueError):
            HullGenerator(beam=0.0)
        with self.assertRaises(ValueError):
            HullGenerator(station_concavity=1.1)
        with self.assertRaises(ValueError):
            HullGenerator(stations=513)
        with self.assertRaises(ValueError):
            HullGenerator(section_points=32)
        with self.assertRaises(ValueError):
            HullGenerator(section_points=3)
        with self.assertRaises(ValueError):
            HullGenerator(freeboard=0.0)
        with self.assertRaises(ValueError):
            HullGenerator(transom_ratio=0.99)
        with self.assertRaises(ValueError):
            HullGenerator(deadrise=40.0)

    def test_longitudinal_resolution_can_be_changed(self) -> None:
        generator = HullGenerator(stations=12, section_points=5)
        shell = shell_grid(generator)

        self.assertEqual(shell.shape, (12, generator.points_per_station, 3))

    def test_finer_sections_follow_the_bottom_curve(self) -> None:
        def midship_bottom(section_points: int) -> np.ndarray:
            generator = HullGenerator(stations=5, section_points=section_points)
            count = generator.points_per_station
            section = generator.generate_mesh().vertices[2 * count : 3 * count]
            return section[section[:, 2] <= 1e-12][:, 1:]

        coarse = midship_bottom(5)
        fine = midship_bottom(33)
        # A malha grossa liga os pontos por retas; a fina segue a curva, que
        # fica abaixo dessas cordas (seção convexa).
        coarse = coarse[np.argsort(coarse[:, 0])]
        chord = np.interp(fine[:, 0], coarse[:, 0], coarse[:, 1])
        self.assertTrue(np.all(fine[:, 1] <= chord + 1e-9))
        self.assertGreater(np.max(chord - fine[:, 1]), 0.02)

    def test_stations_concentrate_where_the_shape_changes(self) -> None:
        generator = HullGenerator(stations=64, transom_ratio=0.0)
        adaptive = generator._station_parameters()
        uniform = np.linspace(0.0, 1.0, 64)

        self.assertLess(
            np.abs(np.diff(generator._longitudinal_fullness(adaptive))).max(),
            0.6 * np.abs(np.diff(generator._longitudinal_fullness(uniform))).max(),
        )


class HullFairingTests(unittest.TestCase):
    def test_sheer_raises_the_deck_at_the_bow(self) -> None:
        flat = shell_grid(HullGenerator(sheer_bow=0.0))
        raised = shell_grid(HullGenerator(sheer_bow=0.3))

        np.testing.assert_allclose(flat[:, 0, 2], 1.0)
        self.assertAlmostEqual(raised[-1, 0, 2], 1.3)
        self.assertAlmostEqual(raised[0, 0, 2], 1.0)

    def test_bow_flare_opens_the_topsides_forward(self) -> None:
        generator = HullGenerator(bow_flare=0.3, stern_flare=0.0, stations=9)
        shell = shell_grid(generator)
        waterline = generator.topside_points

        stern_ratio = shell[1, 0, 1] / shell[1, waterline, 1]
        bow_ratio = shell[-2, 0, 1] / shell[-2, waterline, 1]
        self.assertGreater(bow_ratio, stern_ratio + 0.1)

    def test_deck_camber_raises_the_centerline(self) -> None:
        generator = HullGenerator(closed_deck=True, deck_camber=0.04, sheer_bow=0.0)
        vertices = generator.generate_mesh().vertices

        # Topo do convés na seção média: 1 m de borda livre + 4% de 4 m de boca.
        self.assertAlmostEqual(vertices[:, 2].max(), 1.0 + 0.04 * 4.0, places=2)

    def test_transom_camber_bulges_aft_at_the_centerline(self) -> None:
        flat = HullGenerator(transom_camber=0.0).generate_mesh().vertices
        curved = HullGenerator(transom_camber=0.2).generate_mesh().vertices

        self.assertAlmostEqual(flat[:, 0].min(), -6.0)
        self.assertLess(curved[:, 0].min(), -6.0 - 0.1)


class ChineAndStepTests(unittest.TestCase):
    def test_chine_creates_a_knuckle_at_the_requested_height(self) -> None:
        chine = ChineOptions(height_bow=0.5, height_stern=0.5, flat_width=0.0)
        generator = HullGenerator(chine=chine, stations=9, sheer_bow=0.0)
        shell = shell_grid(generator)
        column = generator.chine_column
        midship = shell[4]

        # Meio do pontal (calado 1,8 + borda livre 1,0) acima da quilha.
        self.assertAlmostEqual(midship[column, 2], -1.8 + 0.5 * 2.8, places=6)
        above = midship[column - 1] - midship[column]
        below = midship[column + 2] - midship[column + 1]
        cosine = np.dot(above[1:], -below[1:]) / (
            np.linalg.norm(above[1:]) * np.linalg.norm(below[1:])
        )
        self.assertLess(np.degrees(np.arccos(cosine)), 170.0)

    def test_chine_flat_has_the_requested_width(self) -> None:
        chine = ChineOptions(flat_width=0.12, flat_angle=0.0)
        generator = HullGenerator(chine=chine, stations=9)
        midship = shell_grid(generator)[4]
        column = generator.chine_column

        self.assertAlmostEqual(abs(midship[column, 1]) - abs(midship[column + 1, 1]), 0.12)
        self.assertAlmostEqual(midship[column, 2], midship[column + 1, 2])

    def test_step_raises_the_bottom_aft_of_the_step(self) -> None:
        step = StepOptions(position=0.5, height_keel=0.04, height_chine=0.07, sweep=0.0)
        generator = HullGenerator(chine=ChineOptions(), steps=(step,))
        _, aft_rows = generator._row_layout()
        shell = shell_grid(generator)
        keel = generator.points_per_station // 2
        column = generator.chine_column
        aft, forward = shell[aft_rows[0]], shell[aft_rows[0] + 1]

        self.assertAlmostEqual(forward[keel, 0] - aft[keel, 0], 0.01, places=6)
        self.assertAlmostEqual(aft[keel, 2] - forward[keel, 2], 0.04, places=3)
        self.assertAlmostEqual(aft[column, 2] - forward[column, 2], 0.07, places=3)

    def test_swept_step_puts_the_chine_end_further_aft(self) -> None:
        step = StepOptions(position=0.5, sweep=20.0)
        generator = HullGenerator(chine=ChineOptions(), steps=(step,))
        _, aft_rows = generator._row_layout()
        aft = shell_grid(generator)[aft_rows[0]]
        keel = generator.points_per_station // 2
        column = generator.chine_column

        expected = aft[column, 1] * np.tan(np.radians(20.0))
        self.assertAlmostEqual(aft[keel, 0] - aft[column, 0], abs(expected), places=2)

    def test_stepped_hull_is_closed(self) -> None:
        steps = (
            StepOptions(position=0.4, sweep=10.0),
            StepOptions(position=0.6, sweep=-15.0, curve=0.1),
        )
        for stations, points in ((64, 33), (8, 5)):
            with self.subTest(stations=stations):
                generator = HullGenerator(
                    chine=ChineOptions(),
                    steps=steps,
                    closed_deck=True,
                    stations=stations,
                    section_points=points,
                )
                open_edges, volume = closed_surface_report(generator.generate_mesh())
                self.assertEqual(open_edges, 0)
                self.assertGreater(volume, 0.0)

    def test_invalid_chine_and_steps_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            HullGenerator(steps=(StepOptions(),))
        with self.assertRaises(ValueError):
            HullGenerator(chine=ChineOptions(height_bow=1.2))
        with self.assertRaises(ValueError):
            HullGenerator(chine=ChineOptions(), steps=(StepOptions(position=0.95),))
        with self.assertRaises(ValueError):
            HullGenerator(
                chine=ChineOptions(),
                steps=(StepOptions(position=0.40), StepOptions(position=0.42)),
            )


class HullConstraintValidatorTests(unittest.TestCase):
    def test_radius_above_estimated_limit_is_rejected(self) -> None:
        generator = HullGenerator(midship_length=6.0, draft=1.8)
        validator = HullConstraintValidator()

        result = validator.validate(generator, concavity=0.2, minimum_radius=4.9)

        self.assertFalse(result.valid)
        self.assertAlmostEqual(result.maximum_radius, 4.8)

    def test_valid_radius_is_accepted(self) -> None:
        generator = HullGenerator()
        result = HullConstraintValidator().validate(
            generator, concavity=0.2, minimum_radius=2.0
        )

        self.assertTrue(result.valid)


class TransformationTests(unittest.TestCase):
    def test_rotation_uses_object_pivot(self) -> None:
        parameters = TransformParameters(rotation_degrees=(0.0, 0.0, 90.0))
        matrix = transformation_matrix(parameters, pivot=(1.0, 0.0, 0.0))
        point = np.array([2.0, 0.0, 0.0, 1.0])

        np.testing.assert_allclose(
            matrix @ point,
            np.array([1.0, 1.0, 0.0, 1.0]),
            atol=1e-12,
        )

    def test_scale_and_translation_are_composed(self) -> None:
        parameters = TransformParameters(
            translation=(3.0, -1.0, 2.0),
            uniform_scale=2.0,
        )
        matrix = transformation_matrix(parameters, pivot=(0.0, 0.0, 0.0))
        point = np.array([1.0, 2.0, 3.0, 1.0])

        np.testing.assert_allclose(matrix @ point, [5.0, 3.0, 8.0, 1.0])

    def test_non_positive_scale_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            transformation_matrix(
                TransformParameters(uniform_scale=0.0),
                pivot=(0.0, 0.0, 0.0),
            )


if __name__ == "__main__":
    unittest.main()
