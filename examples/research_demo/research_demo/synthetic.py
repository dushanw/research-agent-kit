"""Deterministic synthetic fixtures. Never a substitute for real experimental data."""
from __future__ import annotations

import math
import random
from typing import List, Sequence


def make_measurements(n: int, *, seed: int, mean: float = 10.0, sd: float = 2.0,
                      nan_positions: Sequence[int] = ()) -> List[float]:
    """Return `n` Gaussian draws from an isolated, explicitly seeded generator.

    `nan_positions` inserts NaN at the given indices to exercise missing-data policies.
    The global `random` state is never touched.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if sd < 0:
        raise ValueError("sd must be non-negative")
    rng = random.Random(seed)
    values = [rng.gauss(mean, sd) for _ in range(n)]
    for i in nan_positions:
        if not 0 <= i < n:
            raise IndexError(f"nan position {i} outside 0..{n - 1}")
        values[i] = math.nan
    return values
