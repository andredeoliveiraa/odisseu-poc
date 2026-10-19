"""Testes do importador de arquivos .3dm (Rhino)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import rhino3dm

from app.rhino_import import RhinoImportError, read_3dm_as_polydata, unit_label


def _square_mesh() -> rhino3dm.Mesh:
    """Um quadrado simples de 2x2, como duas faces triangulares."""
    mesh = rhino3dm.Mesh()
    for x, y in ((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)):
        mesh.Vertices.Add(x, y, 0.0)
    mesh.Faces.AddFace(0, 1, 2, 3)
    return mesh


def _write_model(
    objects: list[tuple[object, dict]],
    unit_system: rhino3dm.UnitSystem | None = None,
) -> Path:
    """Grava um .3dm temporário com os objetos e atributos dados."""
    model = rhino3dm.File3dm()
    if unit_system is not None:
        model.Settings.ModelUnitSystem = unit_system
    for geometry, attr_overrides in objects:
        attributes = rhino3dm.ObjectAttributes()
        for key, value in attr_overrides.items():
            setattr(attributes, key, value)
        if isinstance(geometry, rhino3dm.Mesh):
            model.Objects.AddMesh(geometry, attributes)
        elif isinstance(geometry, rhino3dm.Curve):
            model.Objects.AddCurve(geometry, attributes)
    handle = tempfile.NamedTemporaryFile(suffix=".3dm", delete=False)
    handle.close()
    model.Write(handle.name, 7)
    return Path(handle.name)


class RhinoImportTests(unittest.TestCase):
    def test_reads_a_plain_mesh_object(self) -> None:
        path = _write_model([(_square_mesh(), {"Name": "casco"})])
        try:
            polydata, report = read_3dm_as_polydata(path)
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(polydata.n_points, 4)
        self.assertEqual(report.objects_total, 1)
        self.assertEqual(report.surfaces_shown, 1)
        self.assertEqual(report.reference_images_skipped, 0)
        self.assertFalse(report.has_omissions)

    def test_skips_pasted_reference_images(self) -> None:
        """Uma superfície nomeada como um arquivo de imagem é ignorada."""
        hull = _square_mesh()
        picture = _square_mesh()
        path = _write_model(
            [
                (hull, {"Name": "casco"}),
                (picture, {"Name": "Clipboard-1234.png"}),
            ]
        )
        try:
            polydata, report = read_3dm_as_polydata(path)
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(polydata.n_points, 4)  # só o casco, não a imagem
        self.assertEqual(report.objects_total, 2)
        self.assertEqual(report.surfaces_shown, 1)
        self.assertEqual(report.reference_images_skipped, 1)

    def test_report_carries_the_file_unit_and_a_summary(self) -> None:
        line = rhino3dm.LineCurve(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(1, 0, 0))
        path = _write_model(
            [
                (_square_mesh(), {"Name": "casco"}),
                (_square_mesh(), {"Name": "vista.jpg"}),
                (line, {"Name": "linha"}),
            ],
            unit_system=rhino3dm.UnitSystem.Meters,
        )
        try:
            _, report = read_3dm_as_polydata(path)
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(report.unit, "m")
        self.assertEqual(
            report.summary(),
            "3 objetos lidos · 1 superfície exibida · "
            "1 imagem de referência ignorada · 1 objeto sem superfície ignorado",
        )

    def test_unknown_unit_is_reported_as_none(self) -> None:
        self.assertIsNone(unit_label(rhino3dm.UnitSystem.CustomUnits))
        self.assertIsNone(unit_label(None))
        self.assertEqual(unit_label(rhino3dm.UnitSystem.Millimeters), "mm")

    def test_skips_invisible_objects(self) -> None:
        path = _write_model([(_square_mesh(), {"Name": "oculto", "Visible": False})])
        try:
            with self.assertRaises(RhinoImportError):
                read_3dm_as_polydata(path)
        finally:
            path.unlink(missing_ok=True)

    def test_raises_when_no_surface_is_available(self) -> None:
        """Um arquivo só com curvas não tem nada para desenhar como malha."""
        line = rhino3dm.LineCurve(rhino3dm.Point3d(0, 0, 0), rhino3dm.Point3d(1, 0, 0))
        path = _write_model([(line, {"Name": "linha de referência"})])
        try:
            with self.assertRaises(RhinoImportError):
                read_3dm_as_polydata(path)
        finally:
            path.unlink(missing_ok=True)

    def test_raises_a_clear_error_for_a_corrupted_file(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".3dm", delete=False)
        handle.write(b"isto nao e um arquivo 3dm valido")
        handle.close()
        path = Path(handle.name)
        try:
            with self.assertRaises(RhinoImportError):
                read_3dm_as_polydata(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
