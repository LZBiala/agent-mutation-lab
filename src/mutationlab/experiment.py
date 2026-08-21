"""The inference-compute study: spend more reviews per file, measure what it buys.

The move under test is self-consistency — ask k noisy reviewers instead of one
and keep what a majority agrees on. Three arms run over the SAME batch, the
same seeds, and the same scoring function the v1.0 pipeline uses, so the only
thing that varies between them is where the members' errors come from:

  A1 independent   — k members with independent error streams. The winning
                     exhibit: catch climbs with k, false alarms collapse.
  A2 correlated    — k seats sharing ONE stream. The placebo: nine times the
                     reviews, byte-identical output, exactly zero gain.
                     Independence is the active ingredient, not the count.
  A3 below-chance  — independent members whose accuracy is under one half.
                     Voting AMPLIFIES their error: the same arithmetic that
                     builds the winning curve runs backwards.

And through every arm, at every k: THE WALL. The defect classes the base
reviewer carries no rule for are derived from its rule table, never listed by
hand, and scored as their own rows. No member ever finds them, so no majority
ever does — inference compute multiplies existing capability and cannot
manufacture absent capability. Detectable-only catch is therefore published
separately from overall catch, so the wall never quietly deflates the number
the Condorcet comparison is made on.

PRE-REGISTERED. The constants below and the ten gates in
tests/test_ttc_experiment.py were frozen before the first run. Nothing here
reads a clock or the network, every float is published at fixed precision, and
the whole thing replays byte-identically in CI.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mutationlab.batch import BatchItem, build_batch
from mutationlab.defects import MUTATORS, EngineError
from mutationlab.noise import NoisyReviewer
from mutationlab.panel import condorcet_prediction, majority_vote
from mutationlab.reviewer import RULE_CLASSES, Finding, MockReviewer, Reviewer
from mutationlab.runner import LINE_TOLERANCE, match_findings

# --- pre-registered constants (frozen before the first run) -----------------
RUN_SEED = "ttc-v1"
MISS_RATE = 0.30  # A1/A2 member accuracy 0.70 — above the Condorcet threshold
MISS_RATE_BELOW = 0.65  # A3 member accuracy 0.35 — below it, on purpose
FA_RATE = 0.10  # key-blind: fires on every file, clean or mutant
K_VALUES: tuple[int, ...] = (1, 3, 5, 7, 9)
N_TRIALS = 200  # trial seeds 0..199
MEMBERS = max(K_VALUES)

ARM_INDEPENDENT = "independent"
ARM_CORRELATED = "correlated"
ARM_BELOW_CHANCE = "below-chance"
ARMS: tuple[str, ...] = (ARM_INDEPENDENT, ARM_CORRELATED, ARM_BELOW_CHANCE)

# Member accuracy per arm — the p the published binomial prediction uses. The
# correlated arm's members are as good as A1's; only their independence differs,
# which is exactly the gap the placebo exhibit puts on screen.
ARM_ACCURACY: dict[str, float] = {
    ARM_INDEPENDENT: 1.0 - MISS_RATE,
    ARM_CORRELATED: 1.0 - MISS_RATE,
    ARM_BELOW_CHANCE: 1.0 - MISS_RATE_BELOW,
}

DECIMALS = 4  # every published float, fixed — byte-stable artifacts


def wall_classes() -> tuple[str, ...]:
    """Defect classes the base reviewer has no detection rule for.

    DERIVED, never hand-listed: a class that ships without a rule joins the
    wall automatically, and a class that gains one leaves it. Hardcoding this
    set would let a future defect pack silently publish a wall row for a class
    the reviewer can now see.
    """
    return tuple(sorted({m.class_id for m in MUTATORS} - RULE_CLASSES))


@dataclass(frozen=True)
class CurvePoint:
    """One published (arm, k) point: catch, false alarms, spurious findings."""

    arm: str
    k: int
    member_accuracy: float
    condorcet: float
    detectable_reviews: int
    detectable_hits: int
    detectable_catch: float
    overall_reviews: int
    overall_hits: int
    overall_catch: float
    clean_reviews: int
    false_alarms: int
    fa_per_clean_review: float
    mutant_reviews: int
    spurious: int
    spurious_per_mutant_review: float

    def to_row(self) -> dict[str, object]:
        return {
            "kind": "curve",
            "arm": self.arm,
            "k": self.k,
            "member_accuracy": round(self.member_accuracy, DECIMALS),
            "condorcet": round(self.condorcet, DECIMALS),
            "detectable_reviews": self.detectable_reviews,
            "detectable_hits": self.detectable_hits,
            "detectable_catch": round(self.detectable_catch, DECIMALS),
            "overall_reviews": self.overall_reviews,
            "overall_hits": self.overall_hits,
            "overall_catch": round(self.overall_catch, DECIMALS),
            "clean_reviews": self.clean_reviews,
            "false_alarms": self.false_alarms,
            "fa_per_clean_review": round(self.fa_per_clean_review, DECIMALS),
            "mutant_reviews": self.mutant_reviews,
            "spurious": self.spurious,
            "spurious_per_mutant_review": round(
                self.spurious_per_mutant_review, DECIMALS
            ),
        }


@dataclass(frozen=True)
class WallPoint:
    """One rule-less class at one (arm, k) — published even though it is zero,
    especially because it is zero."""

    arm: str
    k: int
    class_id: str
    mutant_reviews: int
    hits: int

    def to_row(self) -> dict[str, object]:
        return {
            "kind": "wall",
            "arm": self.arm,
            "k": self.k,
            "class_id": self.class_id,
            "mutant_reviews": self.mutant_reviews,
            "hits": self.hits,
        }


@dataclass(frozen=True)
class ExperimentResult:
    params: dict[str, object]
    curve: tuple[CurvePoint, ...]
    wall: tuple[WallPoint, ...]

    def point(self, arm: str, k: int) -> CurvePoint:
        for candidate in self.curve:
            if candidate.arm == arm and candidate.k == k:
                return candidate
        raise EngineError(f"no published point for arm {arm!r} at k={k}")

    def to_json_lines(self) -> list[str]:
        rows: list[dict[str, object]] = [self.params]
        rows.extend(point.to_row() for point in self.curve)
        rows.extend(row.to_row() for row in self.wall)
        return [json.dumps(row, sort_keys=True) for row in rows]


@dataclass(frozen=True)
class _ReplayReviewer(Reviewer):
    """The base reviewer's verdicts, precomputed per file.

    The base pass is identical in all 200 trials, for all 9 members, in all 3
    arms — running it 70,000 times would only prove that regexes are slow. The
    noise model is what varies, so the base runs once per file and replays.
    """

    findings_by_text: dict[str, tuple[Finding, ...]]
    name: str = "ReplayReviewer"

    def review(self, source_name: str, text: str) -> list[Finding]:
        return list(self.findings_by_text[text])


def build_members(arm: str, trial: int, base: Reviewer) -> tuple[NoisyReviewer, ...]:
    """The panel seats for one arm and one trial, nested by construction.

    Seats are built once per trial and sliced per k, so k=3's members are a
    subset of k=5's — the curve is one panel growing, not five unrelated
    panels, which removes the between-k variance that would otherwise dominate
    a 200-trial study.

    The correlated arm pins every seat to member 0: nine seats, one stream,
    nine identical ballots. That is the placebo, built rather than simulated.
    """
    if arm not in ARM_ACCURACY:
        raise EngineError(f"unknown arm {arm!r}")
    miss_rate = MISS_RATE_BELOW if arm == ARM_BELOW_CHANCE else MISS_RATE
    return tuple(
        NoisyReviewer(
            base=base,
            run_seed=RUN_SEED,
            trial=trial,
            member_index=0 if arm == ARM_CORRELATED else seat,
            miss_rate=miss_rate,
            fa_rate=FA_RATE,
            class_ids=tuple(sorted(RULE_CLASSES)),
        )
        for seat in range(MEMBERS)
    )


@dataclass
class _Tally:
    """Mutable accumulator for one (arm, k) point. Frozen on the way out."""

    detectable_reviews: int = 0
    detectable_hits: int = 0
    overall_reviews: int = 0
    overall_hits: int = 0
    clean_reviews: int = 0
    false_alarms: int = 0
    spurious: int = 0
    wall_reviews: dict[str, int] | None = None
    wall_hits: dict[str, int] | None = None


def _score_item(
    tally: _Tally, item: BatchItem, findings: list[Finding], wall: tuple[str, ...]
) -> None:
    if item.kind == "clean":
        tally.clean_reviews += 1
        tally.false_alarms += len(findings)
        return
    if item.class_id is None or item.line is None:
        raise EngineError(f"mutant item {item.item_id!r} lacks class/line")
    matching, spurious = match_findings(item.class_id, item.line, findings)
    hit = 1 if matching else 0
    tally.overall_reviews += 1
    tally.overall_hits += hit
    tally.spurious += len(spurious)
    if item.class_id in wall:
        assert tally.wall_reviews is not None and tally.wall_hits is not None
        tally.wall_reviews[item.class_id] += 1
        tally.wall_hits[item.class_id] += hit
    else:
        tally.detectable_reviews += 1
        tally.detectable_hits += hit


def run_experiment(fixtures: dict[str, str]) -> ExperimentResult:
    """Run all three arms over every k and return the publishable numbers."""
    items = sorted(build_batch(fixtures), key=lambda i: i.item_id)
    wall = wall_classes()
    base = _ReplayReviewer(
        findings_by_text={
            item.text: tuple(MockReviewer().review(item.source_name, item.text))
            for item in items
        }
    )

    tallies: dict[tuple[str, int], _Tally] = {
        (arm, k): _Tally(
            wall_reviews=dict.fromkeys(wall, 0), wall_hits=dict.fromkeys(wall, 0)
        )
        for arm in ARMS
        for k in K_VALUES
    }
    for arm in ARMS:
        for trial in range(N_TRIALS):
            members = build_members(arm, trial, base)
            for item in items:
                # One ballot per seat, cast once and reused at every k — the
                # nesting that makes the five points one growing panel.
                ballots = [m.review(item.source_name, item.text) for m in members]
                for k in K_VALUES:
                    _score_item(tallies[(arm, k)], item, majority_vote(ballots[:k]), wall)

    curve: list[CurvePoint] = []
    wall_rows: list[WallPoint] = []
    for arm in ARMS:
        for k in K_VALUES:
            tally = tallies[(arm, k)]
            assert tally.wall_reviews is not None and tally.wall_hits is not None
            curve.append(
                CurvePoint(
                    arm=arm,
                    k=k,
                    member_accuracy=ARM_ACCURACY[arm],
                    condorcet=condorcet_prediction(k, ARM_ACCURACY[arm]),
                    detectable_reviews=tally.detectable_reviews,
                    detectable_hits=tally.detectable_hits,
                    detectable_catch=tally.detectable_hits / tally.detectable_reviews,
                    overall_reviews=tally.overall_reviews,
                    overall_hits=tally.overall_hits,
                    overall_catch=tally.overall_hits / tally.overall_reviews,
                    clean_reviews=tally.clean_reviews,
                    false_alarms=tally.false_alarms,
                    fa_per_clean_review=tally.false_alarms / tally.clean_reviews,
                    mutant_reviews=tally.overall_reviews,
                    spurious=tally.spurious,
                    spurious_per_mutant_review=tally.spurious / tally.overall_reviews,
                )
            )
            for class_id in wall:
                wall_rows.append(
                    WallPoint(
                        arm=arm,
                        k=k,
                        class_id=class_id,
                        mutant_reviews=tally.wall_reviews[class_id],
                        hits=tally.wall_hits[class_id],
                    )
                )

    mutants = [i for i in items if i.kind == "mutant"]
    detectable = [i for i in mutants if i.class_id not in wall]
    params: dict[str, object] = {
        "kind": "params",
        "run_seed": RUN_SEED,
        "arms": list(ARMS),
        "k_values": list(K_VALUES),
        "n_trials": N_TRIALS,
        "members": MEMBERS,
        "miss_rate": MISS_RATE,
        "miss_rate_below": MISS_RATE_BELOW,
        "fa_rate": FA_RATE,
        "line_tolerance": LINE_TOLERANCE,
        "clean_items": len(items) - len(mutants),
        "mutant_items": len(mutants),
        "detectable_mutants": len(detectable),
        "detectable_classes": len({i.class_id for i in detectable}),
        "wall_classes": list(wall),
    }
    return ExperimentResult(
        params=params, curve=tuple(curve), wall=tuple(wall_rows)
    )


def write_ttc_metrics(result: ExperimentResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for line in result.to_json_lines():
            fh.write(line + "\n")
