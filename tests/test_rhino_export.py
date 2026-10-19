"""Testes do exportador de cascos paramétricos como .3dm (Rhino)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rhino3dm

from app.models.hull_types import SEMI_DISPLACEMENT, initial_hull
from app.models.rhino_export import (
    RhinoExportError,
    _bezier_to_nurbs,
    _mirror_y,
    export_hull_as_3dm,
    require_rhino3dm,
)


_CTRL_3D = np.array(
    [[0.0, 0.0, 0.0], [1.0, 2.0, 0.5], [3.0, 1.0, 0.3], [4.0, 0.0, 0.0]]
)


class BezierToNurbsTests(unittest.TestCase):
    def test_returns_degree_3_curve(self) -> None:
        curve = _bezier_to_nurbs(_CTRL_3D)

        self.assertEqual(curve.Degree, 3)

    def test_curve_has_four_control_points(self) -> None:
        curve = _bezier_to_nurbs(_CTRL_3D)

        self.assertEqual(len(curve.Points), 4)

    def test_knots_are_clamped_bezier(self) -> None:
        curve = _bezier_to_nurbs(_CTRL_3D)

        # Nós canônicos de Bézier cúbico: [0, 0, 0, 1, 1, 1]
        expected = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
        for i, expected_knot in enumerate(expected):
            self.assertAlmostEqual(curve.Knots[i], expected_knot)

    def test_accepts_2d_control_points(self) -> None:
        ctrl_2d = np.array([[0.0, 0.0], [1.0, 2.0], [3.0, 1.0], [4.0, 0.0]])
        curve = _bezier_to_nurbs(ctrl_2d)

        self.assertEqual(curve.Degree, 3)
        self.assertEqual(len(curve.Points), 4)

    def test_control_point_coordinates_are_preserved(self) -> None:
        curve = _bezier_to_nurbs(_CTRL_3D)

        for i, (x, y, z) in enumerate(_CTRL_3D):
            pt = curve.Points[i]
            self.assertAlmostEqual(pt.X, x)
            self.assertAlmostEqual(pt.Y, y)
            self.assertAlmostEqual(pt.Z, z)
            self.assertAlmostEqual(pt.W, 1.0)


class MirrorYTests(unittest.TestCase):
    _CONTROL = np.array(
        [[0.0, 1.0, 0.0], [1.0, 2.0, 0.5], [2.0, 3.0, 1.0], [3.0, 4.0, 0.0]]
    )

    def test_y_coordinates_are_negated(self) -> None:
        mirrored = _mirror_y(self._CONTROL)

        np.testing.assert_allclose(mirrored[:, 1], -self._CONTROL[:, 1])

    def test_x_coordinates_are_unchanged(self) -> None:
        mirrored = _mirror_y(self._CONTROL)

        np.testing.assert_allclose(mirrored[:, 0], self._CONTROL[:, 0])

    def test_z_coordinates_are_unchanged(self) -> None:
        mirrored = _mirror_y(self._CONTROL)

        np.testing.assert_allclose(mirrored[:, 2], self._CONTROL[:, 2])

    def test_does_not_modify_original(self) -> None:
        original_y = self._CONTROL[:, 1].copy()
        _mirror_y(self._CONTROL)

        np.testing.assert_allclose(self._CONTROL[:, 1], original_y)


class ExportHullAs3dmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = initial_hull(SEMI_DISPLACEMENT)

    def _export_and_read(self) -> tuple[Path, rhino3dm.File3dm]:
        handle = tempfile.NamedTemporaryFile(suffix=".3dm", delete=False)
        handle.close()
        path = Path(handle.name)
        export_hull_as_3dm(self.model, path)
        loaded = rhino3dm.File3dm.Read(str(path))
        return path, loaded

    def test_creates_a_valid_3dm_file(self) -> None:
        path, loaded = self._export_and_read()
        try:
            self.assertIsNotNone(loaded)
        finally:
            path.unlink(missing_ok=True)

    def test_file_has_five_layers(self) -> None:
        path, loaded = self._export_and_read()
        try:
            layer_names = {layer.Name for layer in loaded.Layers}
            self.assertEqual(
                layer_names, {"Convés", "Quilha", "Quina", "Estações", "Proa"}
            )
        finally:
            path.unlink(missing_ok=True)

    def _layer_index_by_name(self, loaded: rhino3dm.File3dm, name: str) -> int:
        for i, layer in enumerate(loaded.Layers):
            if layer.Name == name:
                return i
        raise KeyError(name)

    def test_chine_layer_has_six_curves(self) -> None:
        """A quina tem 3 regiões × 2 bordos = 6 curvas na camada Quina."""
        path, loaded = self._export_and_read()
        try:
            chine_index = self._layer_index_by_name(loaded, "Quina")
            chine_count = sum(
                1
                for obj in loaded.Objects
                if obj.Attributes.LayerIndex == chine_index
            )
            self.assertEqual(chine_count, 6)
        finally:
            path.unlink(missing_ok=True)

    def test_station_layer_has_twelve_curves(self) -> None:
        """3 estações × 2 linhas (sup/inf) × 2 bordos = 12 curvas na camada Estações."""
        path, loaded = self._export_and_read()
        try:
            station_index = self._layer_index_by_name(loaded, "Estações")
            station_count = sum(
                1
                for obj in loaded.Objects
                if obj.Attributes.LayerIndex == station_index
            )
            self.assertEqual(station_count, 12)
        finally:
            path.unlink(missing_ok=True)

    def test_bow_layer_has_one_curve(self) -> None:
        path, loaded = self._export_and_read()
        try:
            bow_index = self._layer_index_by_name(loaded, "Proa")
            bow_count = sum(
                1
                for obj in loaded.Objects
                if obj.Attributes.LayerIndex == bow_index
            )
            self.assertEqual(bow_count, 1)
        finally:
            path.unlink(missing_ok=True)

    def test_total_curve_count(self) -> None:
        """3 deck + 3 keel + 6 chine + 12 stations + 1 bow = 25 curvas."""
        path, loaded = self._export_and_read()
        try:
            total = sum(1 for _ in loaded.Objects)
            self.assertEqual(total, 25)
        finally:
            path.unlink(missing_ok=True)

    def test_all_exported_curves_are_degree_3(self) -> None:
        path, loaded = self._export_and_read()
        try:
            for obj in loaded.Objects:
                geom = obj.Geometry
                if isinstance(geom, rhino3dm.NurbsCurve):
                    self.assertEqual(geom.Degree, 3)
        finally:
            path.unlink(missing_ok=True)


class RequireRhino3dmTests(unittest.TestCase):
    def test_does_not_raise_when_rhino3dm_is_available(self) -> None:
        # rhino3dm está instalado; não deve lançar exceção.
        try:
            require_rhino3dm()
        except RhinoExportError:
            self.fail("require_rhino3dm() lançou RhinoExportError com rhino3dm instalado")
