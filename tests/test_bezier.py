"""Testes das curvas de Bézier e da abordagem iterativa (IA)."""

from __future__ import annotations

import unittest

import numpy as np

from app.models import bezier as bz

KEEL = np.array([[0.0, 0.0], [1.0, -1.2], [5.0, -1.8], [8.0, -1.84]])
PLANAR_3D = np.array([[0.0, 0, 0], [1.0, 0.5, 0], [4.0, 1.0, 0.0], [8.0, 1.2, 0.0]])


class BezierBasicsTests(unittest.TestCase):
    def test_curve_interpolates_its_end_points(self) -> None:
        points = bz.evaluate(KEEL, np.array([0.0, 1.0]))

        np.testing.assert_allclose(points, [KEEL[0], KEEL[3]])

    def test_straight_curve_has_no_curvature(self) -> None:
        line = np.array([[0.0, 0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])

        self.assertLess(bz.curvature_distribution(line).max(), 1e-9)
        self.assertEqual(bz.minimum_radius(line), float("inf"))

    def test_circle_like_arc_has_expected_radius(self) -> None:
        # Aproximação clássica de um quarto de círculo de raio 2 por uma cúbica.
        radius, k = 2.0, 0.5522847498
        arc = np.array(
            [[radius, 0], [radius, k * radius], [k * radius, radius], [0, radius]]
        )

        self.assertAlmostEqual(bz.minimum_radius(arc), radius, delta=0.03)

    def test_curvature_works_in_three_dimensions(self) -> None:
        flat = bz.curvature_distribution(PLANAR_3D)
        lifted = bz.curvature_distribution(PLANAR_3D[:, :2])

        np.testing.assert_allclose(flat, lifted, atol=1e-9)

    def test_end_directions_follow_the_control_polygon(self) -> None:
        first, last = bz.end_directions(KEEL)

        np.testing.assert_allclose(first, bz.unit(KEEL[1] - KEEL[0]))
        np.testing.assert_allclose(last, bz.unit(KEEL[2] - KEEL[3]))


class IterativeApproachTests(unittest.TestCase):
    def test_refit_keeps_end_points_and_end_tangents(self) -> None:
        new_start = np.array([2.0, 0.0])
        refit = bz.refit_curve(KEEL, new_start, KEEL[3])
        old_first, old_last = bz.end_directions(KEEL)
        first, last = bz.end_directions(refit)

        np.testing.assert_allclose(refit[0], new_start)
        np.testing.assert_allclose(refit[3], KEEL[3])
        np.testing.assert_allclose(first, old_first, atol=1e-9)
        np.testing.assert_allclose(last, old_last, atol=1e-9)

    def test_refit_without_change_returns_a_similar_curve(self) -> None:
        refit = bz.refit_curve(KEEL, KEEL[0], KEEL[3])
        score = bz.similarity(
            bz.curvature_distribution(KEEL), bz.curvature_distribution(refit)[None, :]
        )[0]

        self.assertGreater(score, 0.999)

    def test_refit_preserves_the_curvature_distribution(self) -> None:
        refit = bz.refit_curve(KEEL, np.array([-2.0, 0.0]), KEEL[3])
        score = bz.similarity(
            bz.curvature_distribution(KEEL), bz.curvature_distribution(refit)[None, :]
        )[0]

        self.assertGreater(score, 0.95)

    def test_objective_is_between_zero_and_one_for_similar_curves(self) -> None:
        reference = bz.curvature_distribution(KEEL)
        scores = bz.similarity(reference, np.vstack((reference, 2.0 * reference)))

        np.testing.assert_allclose(scores, [1.0, 1.0])

    def test_refit_works_for_three_dimensional_curves(self) -> None:
        refit = bz.refit_curve(PLANAR_3D, np.array([1.0, 0.0, 0.0]), PLANAR_3D[3])

        self.assertEqual(refit.shape, (4, 3))
        np.testing.assert_allclose(refit[:, 2], 0.0, atol=1e-12)

    def test_degenerate_curve_collapses_to_a_point(self) -> None:
        point = np.array([1.0, 2.0])
        refit = bz.refit_curve(KEEL, point, point)

        np.testing.assert_allclose(refit, np.tile(point, (4, 1)))


class MaximumCurvatureTests(unittest.TestCase):
    def test_two_stage_search_matches_the_uniform_grid(self) -> None:
        rng = np.random.default_rng(0)
        controls = rng.normal(size=(40, 4, 2)) * 3.0

        refined = bz._max_curvature(controls, 10000)
        uniform = bz._curvature_batch(controls, 10000).max(axis=1)

        np.testing.assert_allclose(refined, uniform, rtol=2e-3)
        self.assertTrue(np.all(refined >= bz._curvature_batch(controls, 1000).max(axis=1) - 1e-12))

    def test_works_in_three_dimensions_and_for_straight_curves(self) -> None:
        line = np.array([[[0.0, 0, 0], [1.0, 1, 1], [2.0, 2, 2], [3.0, 3, 3]]])

        self.assertLess(float(bz._max_curvature(line, 10000)[0]), 1e-9)
        self.assertAlmostEqual(
            float(bz._max_curvature(PLANAR_3D[None], 10000)[0]),
            float(bz._curvature_batch(PLANAR_3D[None], 10000).max()),
            places=6,
        )


class MinimumRadiusTests(unittest.TestCase):
    def test_radius_grows_then_decays_along_the_family(self) -> None:
        first, last = bz.end_directions(KEEL)
        fractions = np.linspace(0.02, 1.0, 60)
        family = bz.radius_family(KEEL[0], KEEL[3], first, last, fractions)
        radii = bz._minimum_radius_batch(family, 2000)
        peak = int(np.argmax(radii))

        self.assertTrue(np.all(np.diff(radii[: peak + 1]) >= -1e-9))
        self.assertLess(radii[-1], radii[peak])
        self.assertGreater(peak, 0)

    def test_requested_radius_is_reached(self) -> None:
        maximum = bz.maximum_achievable_radius(KEEL)
        curve, reported = bz.set_minimum_radius(KEEL, 0.5 * maximum)

        self.assertAlmostEqual(reported, maximum)
        self.assertAlmostEqual(bz.minimum_radius(curve, 10000), 0.5 * maximum, delta=0.01)

    def test_coarse_sweep_agrees_with_the_full_resolution_search(self) -> None:
        """A varredura grossa só localiza o pico: o resultado tem a precisão de ξ = 10000."""
        family = bz.radius_family(
            KEEL[0], KEEL[3], *bz.end_directions(KEEL),
            np.linspace(bz.MINIMUM_HANDLE_FRACTION, 1.0, bz.RADIUS_DIVISION_CONSTANT),
        )
        kappa = bz._curvature_batch(family, bz.RADIUS_CURVATURE_SAMPLES).max(axis=1)
        exhaustive = 1.0 / kappa

        self.assertAlmostEqual(bz.maximum_achievable_radius(KEEL), float(exhaustive.max()), delta=0.005)
        for target in (0.4, 1.0, 2.0):
            curve, _ = bz.set_minimum_radius(KEEL, target)
            self.assertAlmostEqual(bz.minimum_radius(curve, bz.RADIUS_CURVATURE_SAMPLES), target, delta=0.01)

    def test_radius_beyond_the_maximum_is_clamped(self) -> None:
        maximum = bz.maximum_achievable_radius(KEEL)
        curve, reported = bz.set_minimum_radius(KEEL, 10.0 * maximum)

        self.assertAlmostEqual(bz.minimum_radius(curve, 10000), maximum, delta=1e-3)
        self.assertAlmostEqual(reported, maximum)

    def test_zero_radius_gives_an_almost_straight_curve(self) -> None:
        curve, _ = bz.set_minimum_radius(KEEL, 0.0)
        chord = bz.unit(KEEL[3] - KEEL[0])
        points = bz.evaluate(curve, np.linspace(0, 1, 50))
        deviation = np.abs(
            (points - KEEL[0]) @ np.array([-chord[1], chord[0]])
        ).max()

        self.assertLess(deviation, 0.05)

    def test_set_radius_keeps_the_end_points_and_tangents(self) -> None:
        curve, _ = bz.set_minimum_radius(KEEL, 2.0)
        old_first, old_last = bz.end_directions(KEEL)
        first, last = bz.end_directions(curve)

        np.testing.assert_allclose(curve[[0, 3]], KEEL[[0, 3]])
        np.testing.assert_allclose(first, old_first, atol=1e-9)
        np.testing.assert_allclose(last, old_last, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
