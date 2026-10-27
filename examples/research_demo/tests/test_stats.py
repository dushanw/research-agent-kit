import math
import unittest

from research_demo.stats import summarize
from research_demo.synthetic import make_measurements


class SummarizeTest(unittest.TestCase):
    def test_known_values(self):
        out = summarize([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(out["count"], 4)
        self.assertTrue(math.isclose(out["mean"], 2.5, rel_tol=0, abs_tol=1e-12))
        self.assertTrue(math.isclose(out["sd"], math.sqrt(5 / 3), rel_tol=1e-12))

    def test_does_not_mutate_input(self):
        data = make_measurements(10, seed=3)
        copy = list(data)
        summarize(data)
        self.assertEqual(data, copy)

    def test_empty_is_explicit(self):
        out = summarize([])
        self.assertEqual(out["count"], 0)
        self.assertTrue(math.isnan(out["mean"]) and math.isnan(out["sd"]))

    def test_single_value_has_undefined_sd(self):
        out = summarize([5.0])
        self.assertEqual(out["mean"], 5.0)
        self.assertTrue(math.isnan(out["sd"]))

    def test_nan_policies(self):
        data = make_measurements(6, seed=4, nan_positions=[2])
        with self.assertRaises(ValueError):
            summarize(data)
        self.assertEqual(summarize(data, nan_policy="omit")["count"], 5)
        self.assertTrue(math.isnan(summarize(data, nan_policy="propagate")["mean"]))
        with self.assertRaises(ValueError):
            summarize(data, nan_policy="ignore")


if __name__ == "__main__":
    unittest.main()
