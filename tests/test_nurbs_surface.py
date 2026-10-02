"""Testes da edição de superfícies NURBS por ponto de controle."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rhino3dm

from app.models.nurbs_surface import (
    EditableNurbsSurface,
    NurbsSurfaceError,
    list_editable_surfaces,
)


def _flat_patch(count_u: int = 4, count_v: int = 3) -> rhino3dm.NurbsSurface:
    """Uma superfície plana e simples, só para exercitar a mecânica de edição."""
    order_u = min(4, count_u)
    order_v = min(4, count_v)
    surface = rhino3dm.NurbsSurface.Create(3, False, order_u, order_v, count_u, count_v)
    surface.KnotsU.CreateUniformKnots(1.0)
    surface.KnotsV.CreateUniformKnots(1.0)
    for i in range(count_u):
        for j in range(count_v):
            surface.Points[i, j] = rhino3dm.Point4d(float(i), float(j), 0.0, 1.0)
    return surface


def _write_model_with_brep_face(surface: rhino3dm.NurbsSurface, layer_name: str = "Casco") -> Path:
    """Grava um .3dm com a superfície envolvida num Brep de uma face só,
    do jeito que o Rhino normalmente salva uma superfície modelada."""
    model = rhino3dm.File3dm()
    layer = rhino3dm.Layer()
    layer.Name = layer_name
    layer_index = model.Layers.Add(layer)

    brep = rhino3dm.Brep.CreateFromSurface(surface)
    attributes = rhino3dm.ObjectAttributes()
    attributes.LayerIndex = layer_index
    model.Objects.AddBrep(brep, attributes)

    handle = tempfile.NamedTemporaryFile(suffix=".3dm", delete=False)
    handle.close()
    model.Write(handle.name, 7)
    return Path(handle.name)


class EditableNurbsSurfaceTests(unittest.TestCase):
    def test_control_points_match_what_was_written(self) -> None:
        surface = EditableNurbsSurface(_flat_patch())
        grid = surface.control_points()

        self.assertEqual(grid.shape, (4, 3, 3))
        np.testing.assert_allclose(grid[2, 1], (2.0, 1.0, 0.0))

    def test_moving_a_control_point_changes_the_tessellation(self) -> None:
        surface = EditableNurbsSurface(_flat_patch())
        before = surface.tessellate(resolution=12)

        surface.move_control_point(2, 1, (2.0, 1.0, 5.0))
        after = surface.tessellate(resolution=12)

        self.assertFalse(np.allclose(before.vertices, after.vertices))
        # Uma superfície plana não tem pontos acima de z=0; depois de puxar
        # um CV para cima, o topo da malha precisa ter subido de verdade.
        self.assertGreater(after.vertices[:, 2].max(), 0.5)

    def test_move_control_point_flat_matches_move_control_point(self) -> None:
        grid_shape = (4, 3)
        a = EditableNurbsSurface(_flat_patch(*grid_shape))
        b = EditableNurbsSurface(_flat_patch(*grid_shape))

        # índice linear 4 na grade 4x3 (V=3) é (i=1, j=1)
        a.move_control_point(1, 1, (9.0, 9.0, 9.0))
        b.move_control_point_flat(4, (9.0, 9.0, 9.0))

        np.testing.assert_allclose(a.control_points(), b.control_points())

    def test_out_of_range_control_point_raises(self) -> None:
        surface = EditableNurbsSurface(_flat_patch())
        with self.assertRaises(IndexError):
            surface.move_control_point(99, 0, (0.0, 0.0, 0.0))

    def test_tessellation_resolution_controls_vertex_count(self) -> None:
        surface = EditableNurbsSurface(_flat_patch())
        mesh = surface.tessellate(resolution=10)
        self.assertEqual(mesh.vertices.shape, (100, 3))
        self.assertEqual(mesh.faces.shape, (81, 4))

    def test_round_trip_through_a_saved_3dm_file(self) -> None:
        surface = EditableNurbsSurface(_flat_patch())
        surface.move_control_point(1, 1, (1.0, 1.0, 3.5))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "editada.3dm"
            surface.save_to_3dm(path)

            candidates = list_editable_surfaces(path)
            self.assertEqual(len(candidates), 1)

            reloaded = EditableNurbsSurface.from_3dm_face(path, candidates[0].face_index)
            np.testing.assert_allclose(
                reloaded.control_points()[1, 1], (1.0, 1.0, 3.5), atol=1e-9
            )

    def test_lists_surfaces_wrapped_in_a_brep(self) -> None:
        """Cobre o caso real: uma superfície modelada no Rhino vem dentro de um Brep."""
        path = _write_model_with_brep_face(_flat_patch(), layer_name="Casco")
        try:
            candidates = list_editable_surfaces(path)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].layer_name, "Casco")
            self.assertEqual(candidates[0].control_grid, (4, 3))
        finally:
            path.unlink(missing_ok=True)

    def test_raises_for_a_file_without_any_surface(self) -> None:
        model = rhino3dm.File3dm()
        model.Objects.AddCurve(
            rhino3dm.LineCurve(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(1, 0, 0))
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "so_curva.3dm"
            model.Write(str(path), 7)
            self.assertEqual(list_editable_surfaces(path), [])
            with self.assertRaises(NurbsSurfaceError):
                EditableNurbsSurface.from_3dm_face(path, 0)


if __name__ == "__main__":
    unittest.main()
