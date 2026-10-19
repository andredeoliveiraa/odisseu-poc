"""Testes da amostragem de projetos com S-TLBO (capítulo 4)."""

from __future__ import annotations

import unittest

import numpy as np

from app.models.attributes import ATTRIBUTE_THRESHOLD, DESIGN_VARIABLES, HullDesign
from app.models.hull_types import SEMI_DISPLACEMENT, build_hull
from app.models.sampling import (
    PARTICIPANT_CONSTRAINTS,
    STLBO,
    WINE_GLASS_CONSTRAINTS,
    WINE_GLASS_SPACE,
    YACHT_HULL_SPACE,
    AttributeSampler,
    DesignSpace,
    collapse_penalty,
    collapsing_designs,
    levels,
    maximin_distance,
    potential_energy,
)


class CostTermTests(unittest.TestCase):
    def test_potential_energy_matches_equation_4_6(self) -> None:
        designs = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 2.0]])
        expected = 1.0 / 1.0 + 1.0 / 4.0 + 1.0 / 5.0

        self.assertAlmostEqual(potential_energy(designs), expected)

    def test_energy_is_lower_for_spread_out_designs(self) -> None:
        spread = np.array([[0.1, 0.1], [0.9, 0.9], [0.1, 0.9], [0.9, 0.1]])
        clustered = np.array([[0.4, 0.4], [0.5, 0.5], [0.4, 0.5], [0.5, 0.4]])

        self.assertLess(potential_energy(spread), potential_energy(clustered))

    def test_levels_split_each_axis_into_n_intervals(self) -> None:
        designs = np.array([[0.0, 0.49], [0.99, 1.0]])

        np.testing.assert_array_equal(levels(designs, 2), [[1, 1], [2, 2]])

    def test_collapse_counts_shared_coordinates(self) -> None:
        # Pares (a, b): compartilham o nível 1 no eixo x e o nível 2 no eixo y.
        designs = np.array([[0.1, 0.9], [0.2, 0.8]])

        self.assertEqual(collapse_penalty(designs), 1 + 1)
        self.assertEqual(collapsing_designs(designs), 2)

    def test_latin_hypercube_does_not_collapse(self) -> None:
        count = 8
        rng = np.random.default_rng(0)
        design = np.column_stack(
            [(rng.permutation(count) + 0.5) / count for _ in range(3)]
        )

        self.assertEqual(collapse_penalty(design), 0)
        self.assertEqual(collapsing_designs(design), 0)

    def test_maximin_distance_is_the_smallest_pair_distance(self) -> None:
        designs = np.array([[0.0, 0.0], [3.0, 4.0], [0.0, 1.0]])

        self.assertAlmostEqual(maximin_distance(designs), 1.0)


class UnconstrainedSamplingTests(unittest.TestCase):
    def test_designs_stay_inside_the_bounds(self) -> None:
        result = STLBO(YACHT_HULL_SPACE, population_size=12, max_iterations=20, seed=1).sample(8)

        self.assertEqual(len(result.designs), 8)
        for design in result.designs:
            for name, low, high in zip(
                YACHT_HULL_SPACE.names, YACHT_HULL_SPACE.lower, YACHT_HULL_SPACE.upper
            ):
                self.assertTrue(low <= design[name] <= high)

    def test_sampling_is_reproducible_with_a_seed(self) -> None:
        first = STLBO(YACHT_HULL_SPACE, population_size=10, max_iterations=10, seed=4).sample(5)
        second = STLBO(YACHT_HULL_SPACE, population_size=10, max_iterations=10, seed=4).sample(5)

        np.testing.assert_allclose(first.unit_designs, second.unit_designs)

    def test_optimisation_lowers_the_cost_and_spreads_designs(self) -> None:
        sampler = STLBO(YACHT_HULL_SPACE, population_size=20, max_iterations=60, seed=2)
        result = sampler.sample(12)
        random_designs = np.random.default_rng(2).random((12, 11))

        self.assertLess(result.cost, result.cost_history[0])
        self.assertLess(result.cost, sampler.total_cost(random_designs))
        self.assertLess(
            potential_energy(result.unit_designs), potential_energy(random_designs)
        )

    def test_samples_are_mostly_non_collapsing(self) -> None:
        sampler = STLBO(YACHT_HULL_SPACE, population_size=30, max_iterations=120, seed=3)
        result = sampler.sample(10)
        random_designs = np.random.default_rng(3).random((10, 11))

        self.assertLess(
            collapse_penalty(result.unit_designs), collapse_penalty(random_designs)
        )

    def test_thirty_designs_do_not_collapse_and_match_the_thesis_energy(self) -> None:
        """Capítulo 5: N = 30 sem colapso e com U1 da ordem de 241,78."""
        result = STLBO(YACHT_HULL_SPACE, population_size=15, seed=1).sample(30)

        self.assertEqual(collapse_penalty(result.unit_designs), 0)
        self.assertEqual(collapsing_designs(result.unit_designs), 0)
        self.assertLess(potential_energy(result.unit_designs), 300.0)

    def test_collapse_repair_never_raises_the_cost(self) -> None:
        sampler = STLBO(YACHT_HULL_SPACE, population_size=12, max_iterations=15, seed=3)
        designs = np.random.default_rng(3).random((10, 11))
        before = sampler.total_cost(designs)

        sampler._repair_collapse(designs, 10)

        self.assertLessEqual(sampler.total_cost(designs), before)
        self.assertLess(collapse_penalty(designs), 10 * 11)

    def test_repair_can_be_turned_off(self) -> None:
        raw = STLBO(
            YACHT_HULL_SPACE, population_size=8, max_iterations=5, seed=2, repair=False
        ).sample(12)
        repaired = STLBO(
            YACHT_HULL_SPACE, population_size=8, max_iterations=5, seed=2
        ).sample(12)

        self.assertLessEqual(
            collapse_penalty(repaired.unit_designs), collapse_penalty(raw.unit_designs)
        )

    def test_cost_matches_the_three_terms_of_equation_4_15(self) -> None:
        sampler = STLBO(
            WINE_GLASS_SPACE, WINE_GLASS_CONSTRAINTS, alpha=7.0, beta=11.0, seed=0
        )
        designs = np.random.default_rng(0).random((5, 5))
        violated = sum(sampler.violations(row) for row in designs)

        self.assertAlmostEqual(
            sampler.total_cost(designs),
            potential_energy(designs) + 7.0 * collapse_penalty(designs) + 11.0 * violated,
        )

    def test_progress_callback_can_stop_the_search(self) -> None:
        calls = []

        def progress(iteration: int, cost: float) -> bool:
            calls.append(iteration)
            return iteration < 3

        result = STLBO(YACHT_HULL_SPACE, population_size=8, max_iterations=50, seed=0).sample(
            4, progress
        )

        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(result.iterations, 3)

    def test_invalid_arguments_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            STLBO(YACHT_HULL_SPACE, population_size=1)
        with self.assertRaises(ValueError):
            STLBO(YACHT_HULL_SPACE, max_iterations=0)
        with self.assertRaises(ValueError):
            STLBO(YACHT_HULL_SPACE).sample(0)

    def test_single_design_is_supported(self) -> None:
        result = STLBO(YACHT_HULL_SPACE, population_size=6, max_iterations=3, seed=0).sample(1)

        self.assertEqual(len(result.designs), 1)

    def test_termination_follows_the_change_in_cost(self) -> None:
        result = STLBO(
            YACHT_HULL_SPACE, population_size=10, tolerance=1.0, patience=2, seed=0
        ).sample(4)

        self.assertLess(result.iterations, 400)


class ConstrainedSamplingTests(unittest.TestCase):
    def test_wine_glass_designs_satisfy_the_constraints(self) -> None:
        """Tabela 4.2: Hl ≥ Hu, Wm ≤ Wu/2 e Wm ≤ Wl."""
        result = STLBO(
            WINE_GLASS_SPACE,
            WINE_GLASS_CONSTRAINTS,
            population_size=20,
            max_iterations=80,
            seed=5,
        ).sample(12)

        self.assertEqual(sum(result.violations), 0)
        for design in result.designs:
            self.assertGreaterEqual(design["Hl"], design["Hu"])
            self.assertLessEqual(design["Wm"], design["Wu"] / 2.0)
            self.assertLessEqual(design["Wm"], design["Wl"])

    def test_violations_count_each_broken_constraint(self) -> None:
        space = DesignSpace.from_bounds({"a": (0.0, 1.0), "b": (0.0, 1.0)})
        sampler = STLBO(space, [lambda d: d["a"] > 0.5, lambda d: d["b"] > 0.5])

        self.assertEqual(sampler.violations(np.array([0.9, 0.9])), 0)
        self.assertEqual(sampler.violations(np.array([0.1, 0.9])), 1)
        self.assertEqual(sampler.violations(np.array([0.1, 0.1])), 2)

    def test_infeasible_candidates_cost_more_than_feasible_ones(self) -> None:
        space = DesignSpace.from_bounds({"a": (0.0, 1.0), "b": (0.0, 1.0)})
        sampler = STLBO(space, [lambda d: d["a"] > 0.5], beta=1000.0)
        feasible = np.array([[0.9, 0.1], [0.7, 0.9]])
        infeasible = np.array([[0.1, 0.1], [0.7, 0.9]])

        self.assertGreater(
            sampler.total_cost(infeasible) - sampler.total_cost(feasible), 800.0
        )

    def test_circular_hole_is_avoided(self) -> None:
        """Exemplo 2 da tese (Fuerle e Sienz): região circular proibida (Eq. 4.16)."""
        space = DesignSpace.from_bounds({"x1": (0.0, 1.0), "x2": (0.0, 1.0)})
        sampler = STLBO(
            space,
            [lambda d: (d["x1"] - 0.5) ** 2 + (d["x2"] - 0.5) ** 2 >= 0.25],
            population_size=20,
            max_iterations=80,
            seed=1,
        )
        result = sampler.sample(15)

        self.assertEqual(sum(result.violations), 0)


class AttributeSamplingTests(unittest.TestCase):
    def test_samples_satisfy_the_selected_attributes(self) -> None:
        samples = AttributeSampler(population_size=20, max_iterations=60, seed=7).sample(
            ["compact", "modern"], 4
        )

        self.assertEqual(len(samples), 4)
        for sample in samples:
            self.assertTrue(sample.feasible)
            self.assertGreater(sample.scores["compact"], ATTRIBUTE_THRESHOLD)
            self.assertGreater(sample.scores["modern"], ATTRIBUTE_THRESHOLD)

    def test_compact_modern_speedy_can_be_combined(self) -> None:
        """Figura 5.9: casco compacto, moderno e rápido ao mesmo tempo."""
        samples = AttributeSampler(population_size=20, max_iterations=60, seed=2).sample(
            ["compact", "modern", "speedy"], 3
        )

        self.assertTrue(all(sample.feasible for sample in samples))

    def test_every_attribute_can_be_sampled_alone(self) -> None:
        from app.models.attributes import ATTRIBUTE_MODELS

        for model in ATTRIBUTE_MODELS:
            with self.subTest(attribute=model.key):
                samples = AttributeSampler(
                    population_size=20, max_iterations=40, seed=3
                ).sample([model.key], 3)

                self.assertTrue(all(sample.feasible for sample in samples))

    def test_samples_build_valid_hulls(self) -> None:
        samples = AttributeSampler(population_size=12, max_iterations=30, seed=3).sample(
            ["speedy"], 3
        )
        for sample in samples:
            model = build_hull(sample.design.to_parameters(), SEMI_DISPLACEMENT)

            self.assertGreater(len(model.build_mesh().faces), 0)

    def test_samples_are_distinct(self) -> None:
        samples = AttributeSampler(population_size=12, max_iterations=30, seed=11).sample(
            ["cute"], 5
        )

        designs = {tuple(round(v, 3) for v in s.design.as_dict().values()) for s in samples}

        self.assertEqual(len(designs), 5)

    def test_participant_preferences_are_respected(self) -> None:
        """Tabela 4.1: restrições geométricas dos participantes."""
        for name, constraints in PARTICIPANT_CONSTRAINTS.items():
            with self.subTest(participant=name):
                sampler = AttributeSampler(population_size=20, max_iterations=80, seed=4)
                samples = sampler.sample(["strong"], 5, extra_constraints=constraints)
                feasible = [s for s in samples if s.feasible]

                self.assertGreaterEqual(len(feasible), 3)
                for sample in feasible:
                    values = sample.design.as_dict()
                    self.assertTrue(all(constraint(values) for constraint in constraints))

    def test_invalid_requests_are_rejected(self) -> None:
        sampler = AttributeSampler(seed=0, max_iterations=1)
        with self.assertRaises(ValueError):
            sampler.sample([], 3)
        with self.assertRaises(ValueError):
            sampler.sample(["unknown"], 3)
        with self.assertRaises(ValueError):
            sampler.sample(["speedy"], 0)

    def test_sampled_designs_use_the_yacht_design_variables(self) -> None:
        sample = AttributeSampler(population_size=8, max_iterations=5, seed=0).sample(["cute"], 2)[0]

        self.assertEqual(set(sample.design.as_dict()), set(DESIGN_VARIABLES))
        self.assertIsInstance(sample.design, HullDesign)


if __name__ == "__main__":
    unittest.main()
