"""Testes do modelo paramétrico do casco e dos cascos iniciais."""

from __future__ import annotations

import unittest

import numpy as np

from app.models.hull_model import HullParameters, MeshResolution
from app.models.hull_types import (
    DISPLACEMENT,
    INITIAL_PARAMETERS,
    PLANING,
    SEMI_DISPLACEMENT,
    build_hull,
    initial_hull,
    validate_parameters,
)
from app.models.mesh import HullMesh


def mesh_report(mesh: HullMesh) -> tuple[int, int, float]:
    """Retorna (arestas abertas, arestas mal orientadas, volume)."""
    triangles = mesh.triangulated()
    directed = np.vstack(
        (triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])
    )
    undirected = np.sort(directed, axis=1)
    _, counts = np.unique(undirected, axis=0, return_counts=True)
    _, directed_counts = np.unique(directed, axis=0, return_counts=True)
    corners = mesh.vertices[triangles]
    volume = np.einsum(
        "ij,ij->i", corners[:, 0], np.cross(corners[:, 1], corners[:, 2])
    ).sum() / 6.0
    return int((counts != 2).sum()), int((directed_counts > 1).sum()), float(volume)


class InitialHullTests(unittest.TestCase):
    def test_semi_displacement_reproduces_table_3_4(self) -> None:
        measured = initial_hull(SEMI_DISPLACEMENT).parameters()
        expected = INITIAL_PARAMETERS[SEMI_DISPLACEMENT]

        for name in HullParameters.names():
            with self.subTest(parameter=name):
                self.assertAlmostEqual(
                    getattr(measured, name), getattr(expected, name), delta=0.015
                )

    def test_every_initial_hull_is_a_closed_outward_surface(self) -> None:
        for hull_type in (SEMI_DISPLACEMENT, PLANING, DISPLACEMENT):
            for closed_deck in (False, True):
                with self.subTest(hull=hull_type, closed_deck=closed_deck):
                    mesh = initial_hull(hull_type).build_mesh(closed_deck=closed_deck)
                    open_edges, misoriented, volume = mesh_report(mesh)

                    self.assertGreater(volume, 0.0)
                    self.assertEqual(misoriented, 0)
                    # Sem convés, as únicas arestas abertas são as da borda do convés.
                    if closed_deck:
                        self.assertEqual(open_edges, 0)
                    else:
                        self.assertGreater(open_edges, 0)

    def test_planing_has_straight_sections_and_displacement_is_smooth(self) -> None:
        planing = initial_hull(PLANING).parameters()
        displacement = initial_hull(DISPLACEMENT).parameters()

        self.assertGreater(planing.Ce, 0.0)
        self.assertEqual(displacement.Ce, 0.0)
        self.assertGreater(planing.Res2, 100.0)  # linha inferior reta
        self.assertLess(displacement.Res2, 5.0)  # bojo arredondado

    def test_model_is_mirrored_about_the_centre_plane(self) -> None:
        vertices = initial_hull(SEMI_DISPLACEMENT).build_mesh().vertices
        mirrored = vertices * np.array([1.0, -1.0, 1.0])
        keys = {tuple(np.round(row, 6)) for row in vertices}

        self.assertTrue(all(tuple(np.round(row, 6)) in keys for row in mirrored))

    def test_mesh_starts_at_the_transom_and_the_baseline(self) -> None:
        vertices = initial_hull(SEMI_DISPLACEMENT).build_mesh().vertices
        parameters = INITIAL_PARAMETERS[SEMI_DISPLACEMENT]

        self.assertAlmostEqual(vertices[:, 0].min(), 0.0, places=6)
        self.assertAlmostEqual(vertices[:, 2].min(), 0.0, places=6)
        self.assertAlmostEqual(
            np.ptp(vertices[:, 0]), parameters.total_length, delta=0.05
        )
        self.assertAlmostEqual(np.ptp(vertices[:, 1]), parameters.Be, delta=0.1)

    def test_finer_mesh_has_more_faces(self) -> None:
        model = initial_hull(SEMI_DISPLACEMENT)
        coarse = model.build_mesh(MeshResolution.coarse())
        fine = model.build_mesh(MeshResolution(longitudinal=96, upper=16, lower=24))

        self.assertGreater(len(fine.faces), 3 * len(coarse.faces))

    def test_curves_are_connected_at_the_stations(self) -> None:
        model = initial_hull(SEMI_DISPLACEMENT)

        for curves in (model.deck, model.keel, model.chine):
            for index in range(2):
                np.testing.assert_allclose(curves[index][3], curves[index + 1][0])

    def test_copy_is_independent(self) -> None:
        model = initial_hull(SEMI_DISPLACEMENT)
        clone = model.copy()
        clone.stations[0].upper[0, 0] += 1.0
        clone.deck[0][1] += 1.0

        self.assertNotEqual(model.stations[0].upper[0, 0], clone.stations[0].upper[0, 0])
        self.assertFalse(np.allclose(model.deck[0], clone.deck[0]))

    def test_sheer_plane_parameters_build_a_valid_hull(self) -> None:
        parameters = INITIAL_PARAMETERS[SEMI_DISPLACEMENT].replace(alpha=4.0)
        model = build_hull(parameters, SEMI_DISPLACEMENT)

        self.assertAlmostEqual(model.parameters().alpha, 4.0, places=3)


class ParameterValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = INITIAL_PARAMETERS[SEMI_DISPLACEMENT]

    def test_invalid_combinations_are_rejected(self) -> None:
        invalid = [
            {"Le": 0.0},
            {"Be": -1.0},
            {"Fe": 4.0},  # quina abaixo da quilha
            {"Ce": -0.1},
            {"beta": 0.0},
            {"theta": 90.0},
            {"H": 1.0, "Fb": 1.3},  # quina na proa fora da roda de proa
        ]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_parameters(self.base.replace(**changes))

    def test_base_parameters_are_valid(self) -> None:
        for parameters in INITIAL_PARAMETERS.values():
            validate_parameters(parameters)


if __name__ == "__main__":
    unittest.main()
