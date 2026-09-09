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

        self.assertEqual(mesh.vertices.shape, (32 * 5, 3))
        self.assertEqual(mesh.faces.shape, ((32 - 1) * 4, 4))
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
