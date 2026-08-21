"""mutationlab - mutation testing where the subject is an AI code reviewer.

The premise, stated so it can be attacked: you do not learn whether a smoke
alarm works by waiting for a fire. This harness takes clean source files,
plants exactly ONE known defect from a documented incident class, mixes the
mutants with byte-identical clean control files, and scores a reviewer on
finding THAT defect at THAT line - where a reviewer that cries wolf at
everything scores zero on the clean arm.

What this package deliberately CANNOT measure:
- any live model's catch rate (the bundled reviewer is rule-based and
  deterministic; its numbers are HARNESS CONFORMANCE, proving the pipeline
  scores correctly - they say nothing about any AI);
- open-ended review quality on defects nobody catalogued (recall on a closed
  catalogue is a floor, not a ceiling);
- whether a reviewer's prose helps a human think.

Those limits are printed into the report and the README. The honest product
is the injection engine, the sealed answer key, the false-alarm arm, and a
scoring pipeline that regenerates every published number from a fixed seed.
"""
from __future__ import annotations

__version__ = "1.0.0"
