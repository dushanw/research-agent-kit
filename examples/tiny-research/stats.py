"""Synthetic min-max normalization example with an intentional baseline defect."""
import math

def normalize(values):
    values = [float(x) for x in values]
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError('Expected nonempty finite values')
    low, high = min(values), max(values)
    if low == high:
        raise ValueError('Constant input has no min-max scale')
    return [0.0 for _ in values]  # deliberately wrong fixture
