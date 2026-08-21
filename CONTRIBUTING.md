# Contributing

Thanks for looking under the hood. This repo is small on purpose; keeping it
green is the whole point.

## Setup and tests (the same sequence CI runs)

```
git clone https://github.com/LZBiala/agent-mutation-lab
cd agent-mutation-lab
pip install -e ".[dev]"       # runtime is stdlib-only; the dev extra is pytest
pytest -q                     # contract suite
python tools/blocklist_check.py   # repo hygiene gate
python -m mutationlab demo --quiet    # regenerate every published artifact
git diff --exit-code          # any drift between claims and the fresh run fails
```

Run all five before opening a PR. CI runs exactly this on Windows and Linux
with Python 3.12 pinned - byte-identity guarantees are version-scoped, so use
3.12 locally if you touch generated artifacts.

## What PRs are welcome

- **New defect classes.** Each needs: a documented real-world incident story
  in `defects.py`, a mutator that honors the engine contract (**mutate or
  refuse, never no-op** - tested against every non-target fixture), and
  ideally an executable behavioral probe that passes on clean and misbehaves
  on the mutant.
- **New behavioral probes** for the classes currently proven only by
  documentation.
- **A second fixture domain** - self-contained, stdlib-only, executable in
  isolation, boring by design.
- **Reviewer implementations** against the `reviewer.Reviewer` seam. Keep
  live-model results in your own fork or a separate labeled study; see the
  house law below.
- Fixes to scoring, docs, or the walkthrough page.

## House law

Every published number must regenerate in CI - the build fails if a claim
drifts. Live-model results never enter drift-gated sections. The hygiene gate
must pass.

Practical consequences: never hand-edit anything between the `AUTOGEN`
markers in README.md (CI regenerates those blocks and fails on mismatch), and
never commit absolute paths or contact addresses - the hygiene gate fails
closed on both.
