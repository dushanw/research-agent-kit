# research_demo (example package)

A deliberately small, standard-library-only research package used to try the agent
workflow safely. It contains **only synthetic data** generated from explicit seeds.

```bash
cd examples/research_demo
python3 -m unittest discover -s tests -t . -v
```

In a sandbox created by `scripts/make_sandbox.py`, this package sits at the repository
root and the example task in `tasks/current.md` asks the agent to add a
`research_demo/normalize.py` helper with tests.
