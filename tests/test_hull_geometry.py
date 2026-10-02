"""Testes da geometria e das restrições independentes da interface Qt."""

from __future__ import annotations

import unittest

import numpy as np

from app.hull_generator import HullGenerator
from app.models.constraints import HullConstraintValidator
from app.models.profiles import HULL_PROFILES
from app.models.transforms import TransformParameters, transformation_matrix


class HullGeneratorTests(unittest.TestCase):
    def test_default_mesh_has_expected_topology(self) -> None:
        generator = HullGenerator()
        mesh = generator.generate_mesh()
        width = generator.points_per_station

        self.assertEqual(mesh.vertices.shape, (32 * width, 3))
        self.assertEqual(mesh.faces.shape, ((32 - 1) * (width - 1), 4))
        self.assertGreaterEqual(int(mesh.faces.min()), 0)
        self.assertLess(int(mesh.faces.max()), len(mesh.vertices))

    def test_declared_dimensions_are_reached(self) -> None:
        generator = HullGenerator(total_length=12.0, beam=4.0, draft=1.8)
        mesh = generator.generate_mesh()

        np.testing.assert_allclose(np.ptp(mesh.vertices[:, 0]), 12.0)
        np.testing.assert_allclose(np.ptp(mesh.vertices[:, 1]), 4.0)
        np.testing.assert_allclose(mesh.vertices[:, 2].min(), -1.8)
        np.testing.assert_allclose(mesh.vertices[:, 2].max(), 0.0)

    def test_sections_never_exceed_the_declared_beam(self) -> None:
        """O arco de bojo não pode estufar a seção além da boca informada."""
        for beam, draft in ((4.0, 1.8), (0.1, 0.1), (5.0, 0.4), (3.0, 90.0)):
            limit = HullGenerator.maximum_station_radius(beam / 2.0, draft)
            for fraction in (0.1, 0.5, 1.0):
                with self.subTest(beam=beam, draft=draft, fraction=fraction):
                    mesh = HullGenerator(
                        beam=beam,
                        draft=draft,
                        minimum_radius=max(0.01, limit * fraction),
                    ).generate_mesh()
                    widest = float(np.abs(mesh.vertices[:, 1]).max())
                    self.assertLessEqual(widest, beam / 2.0 + 1e-9)
                    self.assertTrue(np.isfinite(mesh.vertices).all())

    def test_invalid_dimensions_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            HullGenerator(total_length=5.0, midship_length=6.0)
        with self.assertRaises(ValueError):
            HullGenerator(beam=0.0)
        with self.assertRaises(ValueError):
            HullGenerator(station_concavity=1.1)
        with self.assertRaises(ValueError):
            HullGenerator(minimum_radius=0.0)


class StationProfileShapeTests(unittest.TestCase):
    """A seção nunca pode dobrar sobre si mesma, senão a malha se autointersecciona."""

    def test_profile_is_never_folded(self) -> None:
        import itertools

        for beam, draft, concavity, radius_fraction in itertools.product(
            (0.2, 4.0, 5.5, 1000.0),
            (0.1, 1.4, 1.8, 900.0),
            (0.0, 0.5, 0.85, 1.0),
            (0.05, 0.6, 0.95, 1.0),
        ):
            half_width = beam / 2.0
            limit = HullGenerator.maximum_station_radius(half_width, draft)
            radius = max(0.01, limit * radius_fraction)
            try:
                generator = HullGenerator(
                    beam=beam, draft=draft,
                    station_concavity=concavity, minimum_radius=radius,
                )
            except ValueError:
                continue
            with self.subTest(beam=beam, draft=draft, concavity=concavity, radius=radius):
                profile = generator._half_station(half_width, draft)
                self.assertTrue(
                    np.all(np.diff(profile[:, 0]) >= -1e-9),
                    "a meia-boca deixou de crescer monotonicamente da quilha à borda livre",
                )

    def test_high_concavity_near_the_radius_limit_does_not_fold(self) -> None:
        """Caso que reproduziu a dobra original: raio perto do limite e concavidade alta."""
        generator = HullGenerator(
            beam=5.5, draft=1.4, bow_angle=55.0,
            station_concavity=0.85, minimum_radius=2.5,
        )
        profile = generator._half_station(generator.beam / 2.0, generator.draft)
        np.testing.assert_array_less(-np.diff(profile[:, 0]), 1e-9)


class MinimumRadiusTests(unittest.TestCase):
    """O raio mínimo precisa moldar a malha, e não apenas validá-la."""

    def test_radius_changes_the_generated_mesh(self) -> None:
        sharp = HullGenerator(minimum_radius=0.4).generate_mesh()
        round_keel = HullGenerator(minimum_radius=1.9).generate_mesh()

        self.assertFalse(np.allclose(sharp.vertices, round_keel.vertices))

    def test_midship_keel_follows_the_requested_radius(self) -> None:
        radius = 1.5
        generator = HullGenerator(beam=4.0, draft=1.8, minimum_radius=radius)
        profile = generator._half_station(generator.beam / 2.0, generator.draft)

        center = np.array([0.0, -generator.draft + radius])
        on_arc = profile[:4]
        distances = np.linalg.norm(on_arc - center, axis=1)

        np.testing.assert_allclose(distances, radius, atol=1e-9)

    def test_station_profile_starts_at_keel_and_ends_at_sheer(self) -> None:
        generator = HullGenerator(beam=5.0, draft=2.0, minimum_radius=1.0)
        profile = generator._half_station(2.5, 2.0)

        np.testing.assert_allclose(profile[0], (0.0, -2.0))
        np.testing.assert_allclose(profile[-1], (2.5, 0.0))

    def test_larger_radius_flattens_the_bottom(self) -> None:
        keel_depth = []
        for radius in (0.3, 1.9):
            generator = HullGenerator(beam=4.0, draft=1.8, minimum_radius=radius)
            profile = generator._half_station(2.0, 1.8)
            # Altura do perfil a meia-boca: um fundo mais chato sobe menos.
            keel_depth.append(float(np.interp(1.0, profile[:, 0], profile[:, 1])))

        self.assertLess(keel_depth[1], keel_depth[0])


class BowAngleTests(unittest.TestCase):
    def test_bow_angle_does_not_reshape_the_stern(self) -> None:
        sections = []
        for angle in (12.0, 80.0):
            mesh = HullGenerator(bow_angle=angle).generate_mesh()
            x = mesh.vertices[:, 0]
            sections.append(float(np.ptp(mesh.vertices[x < -4.5, 1])))

        self.assertAlmostEqual(sections[0], sections[1], places=9)

    def test_bow_angle_reshapes_the_bow(self) -> None:
        widths = []
        for angle in (12.0, 80.0):
            mesh = HullGenerator(bow_angle=angle).generate_mesh()
            x = mesh.vertices[:, 0]
            widths.append(float(np.ptp(mesh.vertices[x > 4.5, 1])))

        self.assertNotAlmostEqual(widths[0], widths[1], places=3)


class HullConstraintValidatorTests(unittest.TestCase):
    def test_limit_is_the_half_beam_of_the_midship_section(self) -> None:
        validator = HullConstraintValidator()

        for beam, draft in ((4.0, 1.8), (4.0, 0.6), (3.0, 90.0)):
            with self.subTest(beam=beam, draft=draft):
                generator = HullGenerator(beam=beam, draft=draft)
                self.assertAlmostEqual(
                    validator.maximum_achievable_radius(generator), beam / 2.0
                )

    def test_constructibility_bound_never_binds(self) -> None:
        """A meia-boca é sempre o limite mais apertado dos dois."""
        for half_width in (0.05, 2.0, 500.0):
            for depth in (0.05, 1.8, 450.0):
                with self.subTest(half_width=half_width, depth=depth):
                    constructible = (half_width**2 + depth**2) / (2.0 * depth)
                    self.assertGreaterEqual(constructible, half_width - 1e-12)
                    self.assertAlmostEqual(
                        HullGenerator.maximum_station_radius(half_width, depth),
                        half_width,
                    )

    def test_radius_above_limit_is_rejected(self) -> None:
        generator = HullGenerator(beam=4.0, draft=1.8)
        result = HullConstraintValidator().validate(
            generator, concavity=0.2, minimum_radius=9.0
        )

        self.assertFalse(result.valid)
        self.assertIn("limite", result.message)

    def test_valid_radius_is_accepted(self) -> None:
        generator = HullGenerator()
        result = HullConstraintValidator().validate(
            generator, concavity=0.2, minimum_radius=1.9
        )

        self.assertTrue(result.valid)

    def test_every_profile_is_buildable(self) -> None:
        validator = HullConstraintValidator()
        for profile in HULL_PROFILES:
            with self.subTest(profile=profile.name):
                generator = HullGenerator(
                    total_length=profile.total_length,
                    midship_length=profile.midship_length,
                    beam=profile.beam,
                    draft=profile.draft,
                    bow_angle=profile.bow_angle,
                    station_concavity=profile.concavity,
                    minimum_radius=profile.minimum_radius,
                )
                result = validator.validate(
                    generator, profile.concavity, profile.minimum_radius
                )
                self.assertTrue(result.valid, result.message)
                self.assertGreater(len(generator.generate_mesh().vertices), 0)


class ExportPathTests(unittest.TestCase):
    def test_extension_is_added_to_names_containing_dots(self) -> None:
        from pathlib import Path

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
