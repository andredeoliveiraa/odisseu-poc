"""Testes dos modelos de atributo e da amostragem S-TLBO."""

from __future__ import annotations

import unittest

from app.hull_generator import HullGenerator
from app.models.attributes import (
    ATTRIBUTE_MODELS,
    ATTRIBUTE_THRESHOLD,
    FEATURE_RANGES,
    HullDesign,
    evaluate_attributes,
    expressed_attributes,
    standardized_features,
)
from app.models.constraints import HullConstraintValidator
from app.models.profiles import HULL_PROFILES
from app.models.sampling import DEFAULT_MINIMUM_RADIUS, AttributeSampler


def profile_design(profile) -> HullDesign:
    return HullDesign(
        profile.total_length,
        profile.midship_length,
        profile.beam,
        profile.draft,
        profile.bow_angle,
        profile.concavity,
    )


class AttributeModelTests(unittest.TestCase):
    def test_standardization_centers_the_design_space(self) -> None:
        feature_range = FEATURE_RANGES["concavity"]

        self.assertAlmostEqual(feature_range.standardize(0.5), 0.0)
        self.assertAlmostEqual(feature_range.standardize(1.0), 3**0.5)

    def test_each_profile_expresses_its_own_attribute(self) -> None:
        self.assertEqual(len(HULL_PROFILES), len(ATTRIBUTE_MODELS))
        for profile, model in zip(HULL_PROFILES, ATTRIBUTE_MODELS):
            with self.subTest(profile=profile.name):
                self.assertEqual(profile.name, model.label)
                self.assertIn(model.key, expressed_attributes(profile_design(profile)))

    def test_slender_sharp_hull_is_faster_than_short_blunt_hull(self) -> None:
        slender = HullDesign(20.0, 7.0, 3.2, 1.3, 12.0, 0.1)
        blunt = HullDesign(9.0, 6.0, 4.6, 1.5, 55.0, 0.8)

        self.assertGreater(
            evaluate_attributes(slender)["speedy"],
            evaluate_attributes(blunt)["speedy"],
        )
        self.assertGreater(
            evaluate_attributes(blunt)["compact"],
            evaluate_attributes(slender)["compact"],
        )

    def test_usual_peaks_at_the_center_of_the_design_space(self) -> None:
        center = HullDesign(15.0, 7.875, 15.0 / 4.15, 15.0 / 4.15 / 2.7, 32.5, 0.5)
        inputs = standardized_features(center)
        for value in inputs.values():
            self.assertAlmostEqual(value, 0.0, places=6)

        extreme = HullDesign(24.0, 18.0, 3.7, 1.03, 60.0, 1.0)
        scores = evaluate_attributes(center)
        self.assertGreater(scores["usual"], ATTRIBUTE_THRESHOLD)
        self.assertGreater(scores["usual"], evaluate_attributes(extreme)["usual"])


class AttributeSamplerTests(unittest.TestCase):
    def test_samples_satisfy_the_selected_attributes(self) -> None:
        samples = AttributeSampler(seed=7, iterations=25).sample(
            ["compact", "modern"], 4
        )

        self.assertEqual(len(samples), 4)
        for sample in samples:
            self.assertTrue(sample.feasible)
            self.assertGreater(sample.scores["compact"], ATTRIBUTE_THRESHOLD)
            self.assertGreater(sample.scores["modern"], ATTRIBUTE_THRESHOLD)

    def test_samples_are_valid_generator_inputs(self) -> None:
        validator = HullConstraintValidator()
        for sample in AttributeSampler(seed=3, iterations=15).sample(["speedy"], 3):
            design = sample.design
            generator = HullGenerator(
                total_length=design.total_length,
                midship_length=design.midship_length,
                beam=design.beam,
                draft=design.draft,
                bow_angle=design.bow_angle,
                station_concavity=design.concavity,
            )
            result = validator.validate(
                generator, design.concavity, DEFAULT_MINIMUM_RADIUS
            )
            self.assertTrue(result.valid, result.message)

    def test_samples_are_distinct(self) -> None:
        samples = AttributeSampler(seed=11, iterations=15).sample(["cute"], 5)
        lengths = {round(sample.design.total_length, 3) for sample in samples}

        self.assertEqual(len(lengths), 5)

    def test_invalid_requests_are_rejected(self) -> None:
        sampler = AttributeSampler(seed=0, iterations=1)
        with self.assertRaises(ValueError):
            sampler.sample([], 3)
        with self.assertRaises(ValueError):
            sampler.sample(["unknown"], 3)
        with self.assertRaises(ValueError):
            sampler.sample(["speedy"], 0)


if __name__ == "__main__":
    unittest.main()
