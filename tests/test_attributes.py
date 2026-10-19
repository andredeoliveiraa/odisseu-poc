"""Testes dos modelos de atributo (Figura 5.6)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from app.models import attributes
from app.models.attributes import (
    ATTRIBUTE_MODELS,
    ATTRIBUTES_BY_KEY,
    ATTRIBUTE_THRESHOLD,
    DESIGN_VARIABLES,
    FEATURE_RANGES,
    HullDesign,
    evaluate_attributes,
    expressed_attributes,
    standardize_values,
    standardized_features,
)
from app.models.hull_types import SEMI_DISPLACEMENT, INITIAL_PARAMETERS, build_hull


def center_design() -> HullDesign:
    return HullDesign.from_dict({n: FEATURE_RANGES[n].mean for n in DESIGN_VARIABLES})


class FeatureRangeTests(unittest.TestCase):
    def test_ranges_follow_table_4_1(self) -> None:
        expected = {
            "Le": (6.0, 12.0), "Lm": (6.0, 12.0), "Lr": (2.5, 8.0),
            "Be": (4.80, 10.80), "Bm": (4.64, 10.64), "Br": (3.0, 9.0),
            "De": (2.34, 4.34), "Dm": (2.21, 4.21), "Dr": (1.75, 3.50),
            "beta": (30.0, 120.0), "theta": (25.0, 70.0),
        }
        for name, (low, high) in expected.items():
            self.assertEqual(
                (FEATURE_RANGES[name].minimum, FEATURE_RANGES[name].maximum), (low, high)
            )
        self.assertEqual(set(expected), set(DESIGN_VARIABLES))

    def test_standardization_centers_the_design_space(self) -> None:
        for value in standardized_features(center_design()).values():
            self.assertAlmostEqual(value, 0.0, places=9)
        self.assertAlmostEqual(FEATURE_RANGES["beta"].standardize(120.0), 3**0.5)

    def test_matrix_standardization_matches_the_scalar_one(self) -> None:
        design = HullDesign.from_dict({n: FEATURE_RANGES[n].minimum for n in DESIGN_VARIABLES})
        row = np.array([[getattr(design, n) for n in DESIGN_VARIABLES]])

        np.testing.assert_allclose(
            standardize_values(row)[0],
            [standardized_features(design)[n] for n in DESIGN_VARIABLES],
        )


class AttributeModelTests(unittest.TestCase):
    def test_there_are_the_ten_attributes_of_the_thesis(self) -> None:
        self.assertEqual(
            [model.key for model in ATTRIBUTE_MODELS],
            ["strong", "speedy", "comfortable", "aesthetic", "usual",
             "aggressive", "compact", "modern", "charismatic", "cute"],
        )

    def test_matrix_evaluation_matches_the_scalar_evaluation(self) -> None:
        rng = np.random.default_rng(0)
        low = np.array([FEATURE_RANGES[n].minimum for n in DESIGN_VARIABLES])
        high = np.array([FEATURE_RANGES[n].maximum for n in DESIGN_VARIABLES])
        values = low + rng.random((20, 11)) * (high - low)
        standardized = standardize_values(values)
        for model in ATTRIBUTE_MODELS:
            scalar = [
                model.evaluate(HullDesign.from_dict(dict(zip(DESIGN_VARIABLES, row))))
                for row in values
            ]
            np.testing.assert_allclose(model.evaluate_matrix(standardized), scalar)

    def test_each_attribute_is_reachable_in_the_design_space(self) -> None:
        rng = np.random.default_rng(1)
        low = np.array([FEATURE_RANGES[n].minimum for n in DESIGN_VARIABLES])
        high = np.array([FEATURE_RANGES[n].maximum for n in DESIGN_VARIABLES])
        standardized = standardize_values(low + rng.random((4000, 11)) * (high - low))
        for model in ATTRIBUTE_MODELS:
            with self.subTest(attribute=model.key):
                share = float((model.evaluate_matrix(standardized) > ATTRIBUTE_THRESHOLD).mean())
                self.assertGreater(share, 0.05)
                self.assertLess(share, 0.6)

    def test_usual_peaks_at_the_center_of_the_design_space(self) -> None:
        center = center_design()
        extreme = HullDesign.from_dict({n: FEATURE_RANGES[n].maximum for n in DESIGN_VARIABLES})

        self.assertGreater(evaluate_attributes(center)["usual"], ATTRIBUTE_THRESHOLD)
        self.assertGreater(
            evaluate_attributes(center)["usual"], evaluate_attributes(extreme)["usual"]
        )

    def test_short_hull_is_more_compact_and_long_hull_faster(self) -> None:
        short = HullDesign.from_dict(
            {**center_design().as_dict(), "Le": 6.0, "Lm": 6.0, "Lr": 2.5}
        )
        long = HullDesign.from_dict(
            {**center_design().as_dict(), "Le": 12.0, "Lm": 12.0, "Lr": 8.0, "theta": 25.0}
        )

        self.assertGreater(evaluate_attributes(short)["compact"], evaluate_attributes(long)["compact"])
        self.assertGreater(evaluate_attributes(long)["speedy"], evaluate_attributes(short)["speedy"])

    def test_expressed_attributes_lists_models_above_the_threshold(self) -> None:
        design = center_design()
        scores = evaluate_attributes(design)

        self.assertEqual(
            expressed_attributes(design),
            [key for key, value in scores.items() if value > ATTRIBUTE_THRESHOLD],
        )


class CustomCoefficientTests(unittest.TestCase):
    """Os coeficientes reais de Dogan podem ser carregados de um arquivo JSON."""

    def setUp(self) -> None:
        self.defaults = list(attributes._DEFAULT_MODELS)
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "models.json"

    def tearDown(self) -> None:
        attributes.set_attribute_models(self.defaults)
        self.folder.cleanup()

    def test_export_and_load_round_trip(self) -> None:
        attributes.export_attribute_models(self.path)
        before = evaluate_attributes(center_design())

        attributes.load_attribute_models(self.path)

        self.assertEqual(evaluate_attributes(center_design()), before)
        self.assertEqual([m.key for m in ATTRIBUTE_MODELS], [m.key for m in self.defaults])

    def test_loaded_coefficients_replace_the_models_in_place(self) -> None:
        payload = {"models": [{
            "key": "tall", "label": "Tall", "intercept": 0.2,
            "linear": {"De": 0.1}, "interaction": [["Be", "Bm", 0.05]],
        }]}
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        collection = ATTRIBUTE_MODELS

        attributes.load_attribute_models(self.path)

        self.assertIs(collection, ATTRIBUTE_MODELS)
        self.assertEqual(list(ATTRIBUTES_BY_KEY), ["tall"])
        self.assertEqual(list(evaluate_attributes(center_design())), ["tall"])
        self.assertAlmostEqual(evaluate_attributes(center_design())["tall"], 0.2)

    def test_unknown_variables_and_duplicate_keys_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            attributes.model_from_dict({"key": "x", "intercept": 0, "linear": {"Zz": 1.0}})
        with self.assertRaises(ValueError):
            attributes.model_from_dict({"intercept": 0})
        with self.assertRaises(ValueError):
            attributes.set_attribute_models(self.defaults[:1] * 2)
        with self.assertRaises(ValueError):
            attributes.set_attribute_models([])

    def test_sampler_uses_the_loaded_models(self) -> None:
        from app.models.sampling import AttributeSampler

        payload = {"models": [{
            "key": "narrow", "label": "Narrow", "intercept": 0.5, "linear": {"Bm": -0.3},
        }]}
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        attributes.load_attribute_models(self.path)

        samples = AttributeSampler(population_size=10, max_iterations=20, seed=0).sample(["narrow"], 3)

        self.assertTrue(all(sample.feasible for sample in samples))
        self.assertTrue(all(sample.scores["narrow"] > ATTRIBUTE_THRESHOLD for sample in samples))


class DesignToHullTests(unittest.TestCase):
    def test_design_round_trips_through_the_parameters(self) -> None:
        parameters = INITIAL_PARAMETERS[SEMI_DISPLACEMENT]

        rebuilt = HullDesign.from_parameters(parameters).to_parameters()

        for name, value in parameters.as_dict().items():
            self.assertAlmostEqual(getattr(rebuilt, name), value, places=9, msg=name)

    def test_every_corner_of_the_design_space_builds_a_hull(self) -> None:
        rng = np.random.default_rng(5)
        low = np.array([FEATURE_RANGES[n].minimum for n in DESIGN_VARIABLES])
        high = np.array([FEATURE_RANGES[n].maximum for n in DESIGN_VARIABLES])
        corners = [low, high]
        corners += [low + rng.random(11) * (high - low) for _ in range(3)]
        for row in corners:
            design = HullDesign.from_dict(dict(zip(DESIGN_VARIABLES, row)))
            with self.subTest(design=design):
                model = build_hull(design.to_parameters(), SEMI_DISPLACEMENT)

                self.assertGreater(len(model.build_mesh().vertices), 0)
                measured = model.parameters()
                for name in DESIGN_VARIABLES:
                    self.assertAlmostEqual(getattr(measured, name), getattr(design, name), delta=0.02)


if __name__ == "__main__":
    unittest.main()
