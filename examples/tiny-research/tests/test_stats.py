import unittest
from stats import normalize

class NormalizeTest(unittest.TestCase):
    def test_known_answer(self):
        self.assertEqual(normalize([2, 4, 6]), [0.0, 0.5, 1.0])
    def test_negative_values(self):
        self.assertEqual(normalize([-2, 0, 2]), [0.0, 0.5, 1.0])
    def test_constant_rejected(self):
        with self.assertRaises(ValueError):
            normalize([3, 3])
    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            normalize([])
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            normalize([0, float('nan')])
