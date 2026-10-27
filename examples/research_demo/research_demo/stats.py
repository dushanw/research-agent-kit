"""Summary statistics with an explicit missing-data (NaN) policy."""
from __future__ import annotations

import math
from typing import Dict, Iterable, List

NAN_POLICIES = ("raise", "omit", "propagate")


def _clean(values: Iterable[float], nan_policy: str) -> List[float]:
    if nan_policy not in NAN_POLICIES:
        raise ValueError(f"nan_policy must be one of {NAN_POLICIES}")
    data = [float(v) for v in values]
    has_nan = any(math.isnan(v) for v in data)
    if has_nan and nan_policy == "raise":
        raise ValueError("input contains NaN (choose nan_policy='omit' or 'propagate')")
    if nan_policy == "omit":
        data = [v for v in data if not math.isnan(v)]
    return data


def summarize(values: Iterable[float], *, nan_policy: str = "raise") -> Dict[str, float]:
    """Return count, mean and sample standard deviation (ddof=1).

    Empty input returns count 0 and NaN statistics instead of raising, so callers must
    handle it explicitly. With nan_policy='propagate', any NaN makes mean/sd NaN.
    The input is never mutated.
    """
    data = _clean(values, nan_policy)
    n = len(data)
    if n == 0:
        return {"count": 0, "mean": math.nan, "sd": math.nan}
    mean = math.fsum(data) / n
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in data) / (n - 1)) if n > 1 else math.nan
    return {"count": n, "mean": mean, "sd": sd}
