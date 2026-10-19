"""Testes das transformações rígidas e dos nomes de arquivo de exportação."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from app.models.transforms import TransformParameters, transformation_matrix


class ExportPathTests(unittest.TestCase):
    def test_extension_is_added_to_names_containing_dots(self) -> None:
        from app.main_window import MainWindow

        self.assertEqual(
            MainWindow._path_with_selected_extension(
                Path("casco v1.2"), "STL (*.stl)"
            ).name,
            "casco v1.2.stl",
        )
        self.assertEqual(
            MainWindow._path_with_selected_extension(
                Path("casco"), "PLY (*.ply)"
            ).name,
            "casco.ply",
        )
        self.assertEqual(
            MainWindow._path_with_selected_extension(
                Path("casco.vtk"), "STL (*.stl)"
            ).name,
            "casco.vtk",
        )


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
