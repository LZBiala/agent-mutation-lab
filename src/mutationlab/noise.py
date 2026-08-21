"""The noise model: a reviewer that misses and cries wolf on a seeded schedule.

Best-of-k only means something if the members are IMPERFECT and INDEPENDENT.
`NoisyReviewer` manufactures exactly that, on top of any base reviewer, with
two knobs: each base finding survives with probability `1 - miss_rate`, and
with probability `fa_rate` the member invents one finding that was never there.

Two properties make the study trustworthy, and both are tested:

KEY-BLIND. The wrapper sees a source name and a text — never the item kind,
never the planted class, never the answer key. It cannot import the batch
module or the runner, and a test parses this file's AST to keep it that way.
Noise that fires only on clean files would hand the panel a signal no real
reviewer gets. So false alarms fire on EVERY file at the same rate, and the
invented class is drawn from the base reviewer's own rule-backed classes —
reviewer-side knowledge, the classes it could plausibly mistake something for.

ORDER-INDEPENDENT. The random stream is derived per (run seed, trial, member,
file hash), so a member's verdict on a file is a pure function of that file.
Reviewing the batch forwards, backwards, or in parallel gives byte-identical
results, on any platform, under any hash seed — the artifacts are committed
and drift-gated, so "usually the same" would not survive CI.

Draw order per (member, file) stream, all uniforms from `Random.random()` and
every choice derived arithmetically (`int(u * n)`) so no helper's internal
draw pattern can silently change a published number:
  1. one uniform per base finding, in the base reviewer's order — the finding
     is DROPPED when u < miss_rate;
  2. one uniform for the false alarm — it fires when u < fa_rate;
  3. when it fires, one uniform picks the line, one picks the class.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from mutationlab.reviewer import Finding, Reviewer

FALSE_ALARM_NOTE = "invented by the noise model — this file has no such defect"


def stream_seed(run_seed: str, trial: int, member_index: int, text: str) -> int:
    """The per-(member, file) stream seed: first 8 bytes of a digest over the
    run seed, the trial, the member index, and the file's own hash.

    The trial belongs in here. Without it every trial replays one stream, the
    sample size collapses from n trials to 1, and every error bar downstream
    is fiction while still looking perfectly deterministic.
    """
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    material = f"{run_seed}|{trial}|{member_index}|{text_hash}"
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")


@dataclass(frozen=True)
class NoisyReviewer(Reviewer):
    """Wraps `base`, dropping findings and inventing them on a seeded schedule."""

    base: Reviewer
    run_seed: str
    trial: int
    member_index: int
    miss_rate: float
    fa_rate: float
    class_ids: tuple[str, ...]
    name: str = "NoisyReviewer"

    def review(self, source_name: str, text: str) -> list[Finding]:
        rng = random.Random(  # noqa: S311 — a seeded study stream, not a secret
            stream_seed(self.run_seed, self.trial, self.member_index, text)
        )
        kept = [f for f in self.base.review(source_name, text) if rng.random() >= self.miss_rate]
        if rng.random() < self.fa_rate and self.class_ids:
            kept.append(self._invent(rng, text))
        return kept

    def _invent(self, rng: random.Random, text: str) -> Finding:
        lines = max(len(text.splitlines()), 1)
        line = 1 + int(rng.random() * lines)
        class_id = self.class_ids[int(rng.random() * len(self.class_ids))]
        return Finding(line=line, class_id=class_id, note=FALSE_ALARM_NOTE)
