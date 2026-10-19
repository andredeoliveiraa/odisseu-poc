"""Testes dos operadores de forma (Grupos 1 e 2) e dos critérios de qualidade."""

from __future__ import annotations

import unittest

import numpy as np

from app.models import shape_operators as so
from app.models.hull_model import HullParameters
from app.models.hull_types import (
    DISPLACEMENT,
    PLANING,
    SEMI_DISPLACEMENT,
    initial_hull,
)
from tests.test_hull_model import mesh_report

#: Cada operador: (parâmetro, novo valor, parâmetros que também podem mudar).
GROUP_1_CASES = (
    ("Le", 9.0, {"Rek"}),
    ("Lm", 10.0, set()),
    ("Lr", 5.0, set()),
    ("Be", 7.0, {"Res2"}),
    ("Bm", 5.8, {"Rms2"}),
    ("Br", 5.0, {"Rrs2"}),
    ("De", 3.8, {"Rek", "Res2"}),
    ("Dm", 2.9, {"Rms2"}),
    ("Dr", 2.4, {"Rrs2"}),
    ("Fe", 1.8, {"Res1", "Res2"}),
    ("Fm", 1.6, {"Rms1", "Rms2"}),
    ("Fr", 1.1, {"Rrs1", "Rrs2"}),
    ("Fb", 0.9, set()),
    ("Ce", 0.3, {"Res1", "Res2"}),
    ("Cm", 0.05, {"Rms1", "Rms2"}),
    ("Cr", 0.1, {"Rrs1", "Rrs2"}),
    ("K", 0.2, {"Res2", "Rms2", "Rrs2"}),
    ("beta", 90.0, {"Rek"}),
    ("H", 2.0, {"Rek"}),
    ("theta", 42.0, set()),
)


class Group1OperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = initial_hull(SEMI_DISPLACEMENT)
        cls.before = cls.model.parameters()

    def test_each_operator_reaches_the_requested_value(self) -> None:
        for name, value, _ in GROUP_1_CASES:
            with self.subTest(parameter=name):
                result = so.apply_parameters(self.model, {name: value})

                self.assertAlmostEqual(getattr(result.parameters(), name), value, places=4)

    def test_operators_leave_unrelated_parameters_alone(self) -> None:
        """Critério 3: a modificação de um parâmetro não move os demais."""
        for name, value, allowed in GROUP_1_CASES:
            with self.subTest(parameter=name):
                after = so.apply_parameters(self.model, {name: value}).parameters()
                for other in HullParameters.names():
                    if other == name or other in allowed:
                        continue
                    self.assertAlmostEqual(
                        getattr(after, other), getattr(self.before, other), delta=2e-3,
                        msg=f"{other} mudou ao alterar {name}",
                    )

    def test_geometric_continuity_is_kept_at_the_stations(self) -> None:
        """Critério 1: tangentes colineares nas estações (G1), extremidades coincidentes (G0)."""
        for name, value, _ in GROUP_1_CASES:
            with self.subTest(parameter=name):
                result = so.apply_parameters(self.model, {name: value})

                self.assertLess(max(so.continuity_report(result).values()), 1e-6)
                for curves in (result.deck, result.keel, result.chine):
                    for index in range(2):
                        np.testing.assert_allclose(
                            curves[index][3], curves[index + 1][0], atol=1e-9
                        )

    def test_modified_hulls_remain_closed_and_outward(self) -> None:
        for name, value, _ in GROUP_1_CASES:
            with self.subTest(parameter=name):
                mesh = so.apply_parameters(self.model, {name: value}).build_mesh(
                    closed_deck=True
                )
                open_edges, misoriented, volume = mesh_report(mesh)

                self.assertEqual((open_edges, misoriented), (0, 0))
                self.assertGreater(volume, 0.0)

    def test_modified_curves_keep_the_curvature_distribution(self) -> None:
        """Critério 2: a IA mantém a curvatura parecida com a da curva de entrada (F)."""
        result = so.apply_parameters(self.model, {"Lm": 11.0})
        scores = so.curve_similarity(self.model, result)

        # Cosseno centrado: correlação positiva garante preservação da forma.
        # A quina do meio muda de pico de curvatura com a elongação (~0,63).
        self.assertGreater(min(scores.values()), 0.5)

    def test_elongation_moves_only_the_requested_region(self) -> None:
        result = so.apply_parameters(self.model, {"Lm": 11.0}).parameters()

        self.assertAlmostEqual(result.Le, self.before.Le, places=6)
        self.assertAlmostEqual(result.Lr, self.before.Lr, places=6)
        self.assertAlmostEqual(result.Lm, 11.0, places=6)

    def test_widening_keeps_chine_thickness(self) -> None:
        result = so.apply_parameters(self.model, {"Be": 7.4}).parameters()

        self.assertAlmostEqual(result.Ce, self.before.Ce, places=6)
        self.assertAlmostEqual(result.Fe, self.before.Fe, places=6)

    def test_no_change_returns_the_same_hull(self) -> None:
        result = so.apply_parameters(self.model, {"Lm": self.before.Lm, "beta": self.before.beta})

        self.assertIs(result, self.model)

    def test_operators_do_not_modify_their_input(self) -> None:
        snapshot = self.model.copy()
        so.apply_parameters(self.model, {"Be": 7.0, "beta": 80.0, "Rek": 2.0})

        np.testing.assert_allclose(self.model.deck[0], snapshot.deck[0])
        np.testing.assert_allclose(self.model.stations[0].lower, snapshot.stations[0].lower)

    def test_several_operators_are_applied_together(self) -> None:
        result = so.apply_parameters(
            self.model, {"Le": 9.0, "Be": 7.0, "De": 3.8, "beta": 70.0, "alpha": 3.0}
        ).parameters()

        self.assertAlmostEqual(result.Be, 7.0, places=4)
        self.assertAlmostEqual(result.beta, 70.0, places=3)
        self.assertAlmostEqual(result.alpha, 3.0, places=3)

    def test_unknown_parameter_is_rejected(self) -> None:
        with self.assertRaises(so.OperatorError):
            so.apply_parameters(self.model, {"Xyz": 1.0})

    def test_invalid_values_are_rejected(self) -> None:
        invalid = {
            "Le": 0.0,
            "Be": -1.0,
            "Fe": 3.5,  # quina abaixo da quilha
            "Ce": -0.1,
            "K": 50.0,
            "beta": 0.0,
            "theta": 120.0,
            "alpha": 80.0,
            "H": 1.0,  # menor que Fb
        }
        for name, value in invalid.items():
            with self.subTest(parameter=name), self.assertRaises(so.OperatorError):
                so.apply_parameters(self.model, {name: value})


class SheerAngleTests(unittest.TestCase):
    def test_deck_line_lies_in_the_tilted_plane(self) -> None:
        model = so.apply_parameters(initial_hull(SEMI_DISPLACEMENT), {"alpha": 4.0})
        slope = np.tan(np.radians(4.0))
        reference = model.stations[2].upper[0]
        origin_x, origin_z = model.stations[2].x, reference[1]

        for curve in model.deck:
            points = np.vstack(
                [
                    np.array(
                        [curve[0], curve[1], curve[2], curve[3]]
                    )[:, [0, 2]]
                ]
            )
            expected = origin_z + slope * (points[:, 0] - origin_x)
            np.testing.assert_allclose(points[:, 1], expected, atol=1e-9)

    def test_bow_angle_is_unchanged_by_sheer(self) -> None:
        model = initial_hull(SEMI_DISPLACEMENT)
        result = so.apply_parameters(model, {"alpha": 5.0})

        self.assertAlmostEqual(result.parameters().beta, model.parameters().beta, places=4)

    def test_transom_is_the_reference_of_the_plane(self) -> None:
        model = initial_hull(SEMI_DISPLACEMENT)
        result = so.apply_parameters(model, {"alpha": 5.0})

        np.testing.assert_allclose(result.stations[2].upper[0], model.stations[2].upper[0])


class ChineTypeTests(unittest.TestCase):
    def test_each_hull_type_reports_its_chine(self) -> None:
        self.assertEqual(so.chine_type(initial_hull(SEMI_DISPLACEMENT)), so.DOUBLE_CHINE)
        self.assertEqual(so.chine_type(initial_hull(PLANING)), so.DOUBLE_CHINE)
        self.assertEqual(so.chine_type(initial_hull(DISPLACEMENT)), so.NO_CHINE)

    def test_single_chine_removes_the_thickness_but_keeps_the_edge(self) -> None:
        result = so.set_chine_type(initial_hull(SEMI_DISPLACEMENT), so.SINGLE_CHINE)
        parameters = result.parameters()

        self.assertEqual((parameters.Ce, parameters.Cm, parameters.Cr), (0.0, 0.0, 0.0))
        self.assertEqual(so.chine_type(result), so.SINGLE_CHINE)

    def test_no_chine_makes_the_station_lines_tangent(self) -> None:
        result = so.set_chine_type(initial_hull(SEMI_DISPLACEMENT), so.NO_CHINE)

        self.assertEqual(so.chine_type(result), so.NO_CHINE)
        open_edges, misoriented, volume = mesh_report(result.build_mesh(closed_deck=True))
        self.assertEqual((open_edges, misoriented), (0, 0))
        self.assertGreater(volume, 0.0)

    def test_chine_inserter_restores_a_double_chine(self) -> None:
        smooth = so.set_chine_type(initial_hull(DISPLACEMENT), so.DOUBLE_CHINE, (0.2, 0.2, 0.1))
        parameters = smooth.parameters()

        self.assertEqual(so.chine_type(smooth), so.DOUBLE_CHINE)
        self.assertAlmostEqual(parameters.Ce, 0.2, places=6)
        self.assertAlmostEqual(parameters.Cr, 0.1, places=6)

    def test_inserter_needs_positive_thickness(self) -> None:
        with self.assertRaises(so.OperatorError):
            so.set_chine_type(initial_hull(SEMI_DISPLACEMENT), so.DOUBLE_CHINE, (0.0, 0.0, 0.0))

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(so.OperatorError):
            so.set_chine_type(initial_hull(SEMI_DISPLACEMENT), "triple")


class Group2OperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = initial_hull(SEMI_DISPLACEMENT)

    def test_minimum_radius_reaches_the_requested_value(self) -> None:
        for name, value in (("Rek", 2.0), ("Res2", 2.0), ("Rms1", 0.5), ("Rrs2", 1.5)):
            with self.subTest(parameter=name):
                result = so.set_minimum_radius(self.model, name, value)

                self.assertAlmostEqual(getattr(result.parameters(), name), value, delta=0.01)

    def test_unreachable_radius_reports_the_maximum(self) -> None:
        with self.assertRaises(so.RadiusNotAchievable) as context:
            so.set_minimum_radius(self.model, "Rek", 50.0)

        error = context.exception
        self.assertEqual(error.parameter, "Rek")
        self.assertAlmostEqual(error.maximum, so.maximum_radius(self.model, "Rek"))
        self.assertLess(error.maximum, 50.0)
        self.assertIn("limite máximo alcançável", str(error))

    def test_radius_operator_keeps_the_end_points(self) -> None:
        result = so.set_minimum_radius(self.model, "Res2", 1.5)

        np.testing.assert_allclose(
            result.stations[0].lower[[0, 3]], self.model.stations[0].lower[[0, 3]]
        )
        self.assertLess(max(so.continuity_report(result).values()), 1e-6)

    def test_zero_radius_straightens_the_line(self) -> None:
        result = so.set_minimum_radius(self.model, "Res2", 0.0)
        lower = result.stations[0].lower
        chord = lower[3] - lower[0]
        points = np.asarray(
            [
                lower[0] * (1 - u) ** 3
                + 3 * lower[1] * u * (1 - u) ** 2
                + 3 * lower[2] * u**2 * (1 - u)
                + lower[3] * u**3
                for u in np.linspace(0, 1, 40)
            ]
        )
        deviation = np.abs(
            (points - lower[0]) @ (np.array([-chord[1], chord[0]]) / np.linalg.norm(chord))
        ).max()

        self.assertLess(deviation, 0.05)

    def test_negative_radius_is_rejected(self) -> None:
        with self.assertRaises(so.OperatorError):
            so.set_minimum_radius(self.model, "Res1", -1.0)

    def test_concavity_can_be_switched_and_restored(self) -> None:
        for station in range(3):
            for line in ("upper", "lower"):
                with self.subTest(station=station, line=line):
                    original = so.station_concavity(self.model, station, line)
                    other = so.CONCAVE if original == so.CONVEX else so.CONVEX
                    switched = so.set_station_concavity(self.model, station, line, other)
                    self.assertEqual(so.station_concavity(switched, station, line), other)
                    restored = so.set_station_concavity(switched, station, line, original)
                    self.assertEqual(so.station_concavity(restored, station, line), original)

    def test_same_concavity_returns_the_same_hull(self) -> None:
        self.assertIs(
            so.set_station_concavity(self.model, 0, "lower", so.CONVEX), self.model
        )

    def test_concavity_swaps_the_side_of_the_inner_control_points(self) -> None:
        concave = so.set_station_concavity(self.model, 0, "lower", so.CONCAVE)
        original = self.model.stations[0].lower
        flipped = concave.stations[0].lower
        chord = original[3] - original[0]
        normal = np.array([-chord[1], chord[0]])

        side_before = (original[1] - original[0]) @ normal
        side_after = (flipped[1] - flipped[0]) @ normal
        self.assertLess(side_before * side_after, 0.0)
        np.testing.assert_allclose(original[[0, 3]], flipped[[0, 3]])

    def test_concave_hull_is_still_a_valid_closed_surface(self) -> None:
        concave = so.set_station_concavity(self.model, 0, "lower", so.CONCAVE)
        open_edges, misoriented, volume = mesh_report(concave.build_mesh(closed_deck=True))

        self.assertEqual((open_edges, misoriented), (0, 0))
        self.assertGreater(volume, 0.0)

    def test_unknown_concavity_is_rejected(self) -> None:
        with self.assertRaises(so.OperatorError):
            so.set_station_concavity(self.model, 0, "upper", "plana")


class ApplicationOrderTests(unittest.TestCase):
    """Parâmetros que dependem uns dos outros são aplicados na ordem em que são possíveis."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.model = initial_hull(SEMI_DISPLACEMENT)

    def test_depth_below_the_current_chine_lowers_the_chine_first(self) -> None:
        result = so.apply_parameters(self.model, {"De": 2.5, "Fe": 1.5})
        parameters = result.parameters()

        self.assertAlmostEqual(parameters.De, 2.5, places=3)
        self.assertAlmostEqual(parameters.Fe, 1.5, places=3)

    def test_every_station_orders_depth_and_chine(self) -> None:
        result = so.apply_parameters(
            self.model, {"De": 2.5, "Dm": 2.0, "Dr": 1.5, "Fe": 1.5, "Fm": 1.0, "Fr": 0.9}
        )
        parameters = result.parameters()

        for name, value in (("De", 2.5), ("Dm", 2.0), ("Dr", 1.5), ("Fe", 1.5), ("Fm", 1.0), ("Fr", 0.9)):
            self.assertAlmostEqual(getattr(parameters, name), value, places=3, msg=name)

    def test_bow_chine_below_the_current_bow_height_lengthens_it_first(self) -> None:
        result = so.apply_parameters(self.model, {"Fb": 2.2, "H": 2.5})
        parameters = result.parameters()

        self.assertAlmostEqual(parameters.H, 2.5, places=3)
        self.assertAlmostEqual(parameters.Fb, 2.2, places=3)

    def test_depth_without_a_lower_chine_is_still_rejected(self) -> None:
        with self.assertRaises(so.OperatorError):
            so.apply_parameters(self.model, {"De": 2.0})


class HullTypeTransformationTests(unittest.TestCase):
    """Figura 3.16: sequências de operadores que trocam o tipo do casco."""

    def test_semi_displacement_becomes_a_straight_sided_hull(self) -> None:
        model = initial_hull(SEMI_DISPLACEMENT)
        for name in ("Res1", "Res2", "Rms1", "Rms2", "Rrs1", "Rrs2"):
            model = so.set_minimum_radius(model, name, 0.0)
        model = so.apply_parameters(model, {"De": 3.0, "Dm": 2.8, "Dr": 1.9})
        parameters = model.parameters()

        self.assertLess(parameters.Res2, 0.2)  # raio nulo preservado
        self.assertAlmostEqual(parameters.De, 3.0, places=4)
        open_edges, misoriented, volume = mesh_report(model.build_mesh(closed_deck=True))
        self.assertEqual((open_edges, misoriented), (0, 0))
        self.assertGreater(volume, 0.0)

    def test_figure_3_16a_double_chine_shallow_vee(self) -> None:
        """Raios nulos nas estações e, depois, o aprofundamento da Figura 3.16(a).

        A tese dá De = Dm = 2,5 m e Dr = 1,5 m, que coincidem com Fe e Dr = Fr
        da Tabela 3.4; as quinas descem junto (Fe = Fm = 1,5 m, Fr = 0,9 m).
        """
        model = initial_hull(SEMI_DISPLACEMENT)
        model = so.apply_parameters(
            model, {"Res1": 0.0, "Res2": 0.0, "Rms1": 0.0, "Rms2": 0.0, "Rrs1": 0.0, "Rrs2": 0.0}
        )
        model = so.apply_parameters(
            model, {"De": 2.5, "Dm": 2.5, "Dr": 1.5, "Fe": 1.5, "Fm": 1.5, "Fr": 0.9}
        )
        parameters = model.parameters()

        for name, value in (("De", 2.5), ("Dm", 2.5), ("Dr", 1.5), ("Fe", 1.5), ("Fm", 1.5), ("Fr", 0.9)):
            self.assertAlmostEqual(getattr(parameters, name), value, places=3, msg=name)
        for name in ("Res1", "Res2", "Rms1", "Rms2", "Rrs1", "Rrs2"):
            self.assertLess(getattr(parameters, name), 0.2, msg=name)
        self.assertEqual(so.chine_type(model), so.DOUBLE_CHINE)
        self.assertLess(max(so.continuity_report(model).values()), 1e-6)
        open_edges, misoriented, volume = mesh_report(model.build_mesh(closed_deck=True))
        self.assertEqual((open_edges, misoriented), (0, 0))
        self.assertGreater(volume, 0.0)

    def test_figure_3_16b_rounded_hull_with_the_thesis_values(self) -> None:
        """Sem quina, De = 4 m, raios 3,8 / 3,5 / 2,2 m, β = 80° e Rek = 5 m."""
        model = initial_hull(SEMI_DISPLACEMENT)
        model = so.set_chine_type(model, so.NO_CHINE)
        model = so.apply_parameters(model, {"De": 4.0})
        model = so.apply_parameters(model, {"Res2": 3.8, "Rms2": 3.5, "Rrs2": 2.2})
        model = so.apply_parameters(model, {"beta": 80.0})
        model = so.apply_parameters(model, {"Rek": 5.0})
        parameters = model.parameters()

        self.assertEqual(so.chine_type(model), so.NO_CHINE)
        for name, value in (("De", 4.0), ("Res2", 3.8), ("Rms2", 3.5), ("Rrs2", 2.2), ("beta", 80.0), ("Rek", 5.0)):
            self.assertAlmostEqual(getattr(parameters, name), value, delta=0.02, msg=name)
        self.assertLess(max(so.continuity_report(model).values()), 1e-6)
        open_edges, misoriented, volume = mesh_report(model.build_mesh(closed_deck=True))
        self.assertEqual((open_edges, misoriented), (0, 0))
        self.assertGreater(volume, 0.0)

    def test_semi_displacement_becomes_a_rounded_hull(self) -> None:
        model = initial_hull(SEMI_DISPLACEMENT)
        model = so.set_chine_type(model, so.NO_CHINE)
        model = so.apply_parameters(model, {"De": 4.0})
        model = so.apply_parameters(model, {"beta": 80.0})
        parameters = model.parameters()

        self.assertEqual(so.chine_type(model), so.NO_CHINE)
        self.assertAlmostEqual(parameters.beta, 80.0, places=3)
        self.assertLess(max(so.continuity_report(model).values()), 1e-6)


class ComputationTimeTests(unittest.TestCase):
    def test_each_operator_runs_within_the_reported_time(self) -> None:
        import time

        model = initial_hull(SEMI_DISPLACEMENT)
        for name, value, _ in GROUP_1_CASES:
            started = time.perf_counter()
            so.apply_parameters(model, {name: value})
            # A tese informa menos de 4 s por operador (PC de 2017).
            self.assertLess(time.perf_counter() - started, 4.0, msg=name)


if __name__ == "__main__":
    unittest.main()
