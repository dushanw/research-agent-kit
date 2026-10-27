import math
import random
import unittest

from research_demo.synthetic import make_measurements


class MakeMeasurementsTest(unittest.TestCase):
    def test_same_seed_is_reproducible(self):
        self.assertEqual(make_measurements(50, seed=7), make_measurements(50, seed=7))

    def test_different_seed_differs(self):
        self.assertNotEqual(make_measurements(50, seed=7), make_measurements(50, seed=8))

    def test_does_not_touch_global_random_state(self):
        random.seed(123)
        expected = random.random()
        random.seed(123)
        make_measurements(10, seed=1)
        self.assertEqual(random.random(), expected)

    def test_nan_positions(self):
        values = make_measurements(5, seed=1, nan_positions=[0, 3])
        self.assertTrue(math.isnan(values[0]) and math.isnan(values[3]))
        self.assertEqual(sum(math.isnan(v) for v in values), 2)

    def test_rejects_invalid_arguments(self):
        with self.assertRaises(ValueError):
            make_measurements(-1, seed=0)
        with self.assertRaises(IndexError):
            make_measurements(3, seed=0, nan_positions=[3])

    def test_large_sample_moments_within_tolerance(self):
        values = make_measurements(20000, seed=2024, mean=10.0, sd=2.0)
        mean = sum(values) / len(values)
        # Tolerance ~ 5 standard errors (2 / sqrt(20000) ~= 0.014); fixed seed => deterministic.
        self.assertAlmostEqual(mean, 10.0, delta=0.07)


if __name__ == "__main__":
    unittest.main()
