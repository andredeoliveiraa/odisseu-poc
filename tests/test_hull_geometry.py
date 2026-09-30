"""Testes da geometria e das restrições independentes da interface Qt."""

from __future__ import annotations

import unittest

import numpy as np

from app.hull_generator import HullGenerator
from app.models.constraints import HullConstraintValidator
from app.models.transforms import TransformParameters, transformation_matrix


class HullGeneratorTests(unittest.TestCase):
    def test_default_mesh_has_expected_topology(self) -> None:
        generator = HullGenerator()
        mesh = generator.generate_mesh()

        self.assertEqual(mesh.vertices.shape, (64 * 33, 3))
        self.assertEqual(mesh.faces.shape, ((64 - 1) * 32, 4))
        self.assertGreaterEqual(int(mesh.faces.min()), 0)
        self.assertLess(int(mesh.faces.max()), len(mesh.vertices))

    def test_declared_dimensions_are_reached(self) -> None:
        generator = HullGenerator(total_length=12.0, beam=4.0, draft=1.8)
        mesh = generator.generate_mesh()

        np.testing.assert_allclose(np.ptp(mesh.vertices[:, 0]), 12.0)
        np.testing.assert_allclose(np.ptp(mesh.vertices[:, 1]), 4.0)
        np.testing.assert_allclose(mesh.vertices[:, 2].min(), -1.8)
        np.testing.assert_allclose(mesh.vertices[:, 2].max(), 0.0)

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

    def test_longitudinal_resolution_can_be_changed(self) -> None:
        mesh = HullGenerator(stations=12, section_points=5).generate_mesh()

        self.assertEqual(mesh.vertices.shape, (12 * 5, 3))
        self.assertEqual(mesh.faces.shape, ((12 - 1) * 4, 4))

    def test_sections_follow_the_analytic_curve(self) -> None:
        coarse = HullGenerator(section_points=5).generate_mesh().vertices
        fine = HullGenerator(section_points=33).generate_mesh().vertices
        midship = 32

        # O ponto a 1/4 da boca existe nas duas malhas e deve coincidir.
        np.testing.assert_allclose(coarse[midship * 5 + 1], fine[midship * 33 + 8])
        # A malha fina segue a curva entre esses pontos em vez de uma reta.
        coarse_chord = 0.5 * (coarse[midship * 5 + 1, 2] + coarse[midship * 5 + 2, 2])
        self.assertLess(fine[midship * 33 + 12, 2], coarse_chord)

    def test_stations_concentrate_where_the_shape_changes(self) -> None:
        generator = HullGenerator(stations=64)
        x = generator.generate_mesh().vertices[::33, 0]
        spacing = np.diff(x)
        adaptive = generator._station_parameters()
        uniform = np.linspace(0.0, 1.0, 64)

        np.testing.assert_allclose(spacing, spacing[::-1], atol=1e-9)
        self.assertLess(
            np.abs(np.diff(generator._longitudinal_fullness(adaptive))).max(),
            0.6 * np.abs(np.diff(generator._longitudinal_fullness(uniform))).max(),
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
