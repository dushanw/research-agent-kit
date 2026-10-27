# Task: deterministic normalization helper

<!-- Migrated from the original example task (kit v1); wording of the goal and
acceptance criteria is preserved below. Replace this example before a production run. -->

## Owner
example-owner (replace before a production run)

## Scope
Goal: implement a small array-normalization helper appropriate to this project's Python
stack. In the bundled example package this means a new `research_demo/normalize.py`
with a z-score helper and `tests/test_normalize.py`.

## Out of scope
- No changes to raw data, modeling results, or unrelated modules.
- No new dependencies.

## Success criteria
- It does not mutate input arrays.
- Constant arrays and empty arrays are handled explicitly.
- Inputs containing NaN have a documented policy.
- Tests exercise normal, constant, empty, and NaN cases using synthetic data.
- No changes to raw data, modeling results, or unrelated modules.

## Test command
`.venv/bin/python -m unittest discover -s tests -t .`

## Reproducibility
- Synthetic inputs come from `research_demo.synthetic.make_measurements(seed=...)` with explicit seeds.
- Float comparisons use explicit tolerances (`math.isclose`).
- No external datasets; no network access needed.

## Data and privacy
Synthetic data only.
