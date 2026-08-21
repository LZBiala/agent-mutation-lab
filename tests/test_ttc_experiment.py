"""The ten PRE-REGISTERED gates of the inference-compute study, as numeric
assertions - plus the conformance checks that keep the published artifacts
tied to them.

The gates were frozen against the sampling distribution BEFORE the first run.
The seed set then froze the numbers, and the same gates became permanent CI
assertions: if a future change moves a curve, one of these fails by name.

Every denominator here is DERIVED from the batch. Hardcoding n=1800 would let
a future defect class silently strand the arithmetic while the tests still
pass.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mutationlab.batch import build_batch
from mutationlab.defects import MUTATORS
from mutationlab.experiment import (
    ARM_BELOW_CHANCE,
    ARM_CORRELATED,
    ARM_INDEPENDENT,
    ARMS,
    K_VALUES,
    MISS_RATE,
    MISS_RATE_BELOW,
    N_TRIALS,
    ExperimentResult,
    build_members,
    run_experiment,
)
from mutationlab.panel import condorcet_prediction
from mutationlab.report import (
    AUTOGEN_BEGIN,
    AUTOGEN_END,
    TTC_BEGIN,
    TTC_END,
    load_ttc_metrics,
    render_ttc_curve_svg,
    render_ttc_table,
)
from mutationlab.reviewer import RULE_CLASSES, MockReviewer

REPO = Path(__file__).resolve().parents[1]
FIXTURES = {
    p.stem: p.read_text(encoding="utf-8")
    for p in sorted((REPO / "fixtures" / "catalog_app").glob("*.py"))
}
ITEMS = build_batch(FIXTURES)
WALL_CLASSES = {m.class_id for m in MUTATORS} - RULE_CLASSES
CLEAN_ITEMS = [i for i in ITEMS if i.kind == "clean"]
MUTANT_ITEMS = [i for i in ITEMS if i.kind == "mutant"]
DETECTABLE_ITEMS = [i for i in MUTANT_ITEMS if i.class_id in RULE_CLASSES]
TTC_METRICS = REPO / "metrics-ttc.jsonl"
TTC_CURVE = REPO / "report" / "ttc-curve.svg"

P_INDEPENDENT = 1.0 - MISS_RATE
P_BELOW_CHANCE = 1.0 - MISS_RATE_BELOW


@pytest.fixture(scope="module")
def result() -> ExperimentResult:
    return run_experiment(FIXTURES)


def catch(result: ExperimentResult, arm: str, k: int) -> float:
    return result.point(arm, k).detectable_catch


class TestSampleSizeIsDerived:
    """Every gate below is only as good as its denominator, and the denominator
    must come from the batch - not from prose written when the pack had nine
    classes."""

    def test_the_batch_shape_the_study_assumes(self) -> None:
        assert len(DETECTABLE_ITEMS) == len(MUTANT_ITEMS) - len(WALL_CLASSES)
        assert WALL_CLASSES, "no rule-less class - the wall exhibit has no subject"

    def test_reviews_per_point_match_trials_times_items(
        self, result: ExperimentResult
    ) -> None:
        for arm in ARMS:
            for k in K_VALUES:
                point = result.point(arm, k)
                assert point.detectable_reviews == N_TRIALS * len(DETECTABLE_ITEMS)
                assert point.overall_reviews == N_TRIALS * len(MUTANT_ITEMS)
                assert point.clean_reviews == N_TRIALS * len(CLEAN_ITEMS)


class TestG1Capability:
    """G1 - the winning exhibit: more inference compute, more defects caught."""

    def test_independent_catch_gains_at_least_fifteen_points(
        self, result: ExperimentResult
    ) -> None:
        gain = catch(result, ARM_INDEPENDENT, 9) - catch(result, ARM_INDEPENDENT, 1)
        assert gain >= 0.15, gain


class TestG2TheoryMatch:
    """G2 - the empirical curve must land on the exact binomial tail, in the
    arm above one-half accuracy AND the arm below it. The small lucky-false-
    alarm inflation is absorbed inside the tolerance a priori; filtering it out
    would mean scoring findings against the answer key."""

    def test_every_point_matches_its_binomial_prediction(
        self, result: ExperimentResult
    ) -> None:
        arms = ((ARM_INDEPENDENT, P_INDEPENDENT), (ARM_BELOW_CHANCE, P_BELOW_CHANCE))
        for arm, accuracy in arms:
            for k in K_VALUES:
                predicted = condorcet_prediction(k, accuracy)
                observed = catch(result, arm, k)
                assert abs(observed - predicted) <= 0.03, (arm, k, observed, predicted)

    def test_the_published_prediction_column_is_the_same_arithmetic(
        self, result: ExperimentResult
    ) -> None:
        arms = (
            (ARM_INDEPENDENT, P_INDEPENDENT),
            (ARM_CORRELATED, P_INDEPENDENT),
            (ARM_BELOW_CHANCE, P_BELOW_CHANCE),
        )
        for arm, accuracy in arms:
            for k in K_VALUES:
                point = result.point(arm, k)
                predicted = condorcet_prediction(k, accuracy)
                assert point.condorcet == pytest.approx(predicted), (arm, k)


class TestG3CorrelatedPlacebo:
    """G3 - the placebo arm, EXACT. Nine seats sharing one stream produce nine
    identical ballots, so the majority verdict is that one ballot at every k.
    Any deviation is a bug, not noise: the tolerance is zero."""

    def test_all_correlated_seats_return_the_same_ballot(self) -> None:
        members = build_members(ARM_CORRELATED, trial=0, base=MockReviewer())
        assert len(members) > 1
        for item in ITEMS:
            ballots = [m.review(item.source_name, item.text) for m in members]
            assert all(b == ballots[0] for b in ballots), item.item_id

    def test_hit_counts_are_integer_identical_at_every_k(
        self, result: ExperimentResult
    ) -> None:
        baseline = result.point(ARM_CORRELATED, 1)
        for k in K_VALUES:
            point = result.point(ARM_CORRELATED, k)
            assert point.detectable_hits == baseline.detectable_hits, k
            assert point.overall_hits == baseline.overall_hits, k

    def test_nine_times_the_compute_buys_exactly_nothing(
        self, result: ExperimentResult
    ) -> None:
        assert catch(result, ARM_CORRELATED, 9) == catch(result, ARM_CORRELATED, 1)


class TestG4TheWall:
    """G4 - a rule-less class is invisible to voting, EXACT. The invented-
    finding pool holds only rule-backed classes, so the wall reads zero by
    construction rather than by luck."""

    def test_every_wall_row_is_zero(self, result: ExperimentResult) -> None:
        assert result.wall, "no wall rows published"
        for row in result.wall:
            assert row.class_id in WALL_CLASSES
            assert row.hits == 0, (row.arm, row.k, row.class_id, row.hits)

    def test_a_wall_row_exists_for_every_arm_and_every_k(
        self, result: ExperimentResult
    ) -> None:
        published = {(r.arm, r.k, r.class_id) for r in result.wall}
        expected = {
            (arm, k, class_id)
            for arm in ARMS
            for k in K_VALUES
            for class_id in WALL_CLASSES
        }
        assert published == expected

    def test_the_wall_drags_overall_catch_below_detectable_catch(
        self, result: ExperimentResult
    ) -> None:
        for arm in ARMS:
            for k in K_VALUES:
                point = result.point(arm, k)
                assert point.overall_catch < point.detectable_catch, (arm, k)


class TestG5FalseAlarms:
    def test_a_single_reviewer_cries_wolf_at_the_configured_rate(
        self, result: ExperimentResult
    ) -> None:
        rate = result.point(ARM_INDEPENDENT, 1).fa_per_clean_review
        assert 0.05 <= rate <= 0.15, rate

    def test_voting_collapses_false_alarms_from_k_three_up(
        self, result: ExperimentResult
    ) -> None:
        for k in K_VALUES:
            if k < 3:
                continue
            rate = result.point(ARM_INDEPENDENT, k).fa_per_clean_review
            assert rate <= 0.005, (k, rate)

    def test_the_correlated_arm_never_loses_a_false_alarm(
        self, result: ExperimentResult
    ) -> None:
        baseline = result.point(ARM_CORRELATED, 1).false_alarms
        for k in K_VALUES:
            assert result.point(ARM_CORRELATED, k).false_alarms == baseline, k


class TestG6DiminishingReturns:
    """G6 - the published LOSES exhibit: the last two seats buy a fraction of
    what the first two bought, at the same price."""

    def test_the_last_step_is_smaller_than_the_first(
        self, result: ExperimentResult
    ) -> None:
        first = catch(result, ARM_INDEPENDENT, 3) - catch(result, ARM_INDEPENDENT, 1)
        last = catch(result, ARM_INDEPENDENT, 9) - catch(result, ARM_INDEPENDENT, 7)
        assert last < first, (first, last)


class TestG7Determinism:
    def test_two_in_process_runs_are_byte_identical(
        self, result: ExperimentResult
    ) -> None:
        again = run_experiment(FIXTURES)
        assert again.to_json_lines() == result.to_json_lines()

    def test_the_committed_metrics_are_what_this_run_produces(
        self, result: ExperimentResult
    ) -> None:
        committed = TTC_METRICS.read_text(encoding="utf-8").splitlines()
        assert committed == result.to_json_lines()


@pytest.fixture(scope="module")
def fresh_demo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A full `demo` run in a temp copy - never the real tree."""
    workdir = tmp_path_factory.mktemp("ttc_demo")
    shutil.copytree(REPO / "src", workdir / "src")
    shutil.copytree(REPO / "fixtures", workdir / "fixtures")
    shutil.copy(REPO / "README.md", workdir / "README.md")
    outcome = subprocess.run(  # noqa: S603 - running our own module under test
        [sys.executable, "-m", "mutationlab", "demo", "--quiet"],
        cwd=workdir,
        env={**os.environ, "PYTHONPATH": str(workdir / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert outcome.returncode == 0, outcome.stderr
    return workdir


class TestG8NoPerturbation:
    """G8 - the experiment is additive. The v1.0 artifacts must come out of a
    fresh full run byte-identical to what is committed."""

    def test_base_metrics_and_scorecard_are_untouched(self, fresh_demo: Path) -> None:
        for name in ("metrics.jsonl", "report/scorecard.svg"):
            assert (fresh_demo / name).read_bytes() == (REPO / name).read_bytes(), name

    def test_the_first_autogen_block_is_untouched(self, fresh_demo: Path) -> None:
        def block(text: str) -> str:
            return text[text.index(AUTOGEN_BEGIN) : text.index(AUTOGEN_END)]

        fresh = (fresh_demo / "README.md").read_text(encoding="utf-8")
        assert block(fresh) == block((REPO / "README.md").read_text(encoding="utf-8"))

    def test_the_new_artifacts_regenerate_too(self, fresh_demo: Path) -> None:
        for name in ("metrics-ttc.jsonl", "report/ttc-curve.svg"):
            assert (fresh_demo / name).read_bytes() == (REPO / name).read_bytes(), name


class TestG9Budget:
    """G9 - a soft budget, measured HERE. The package itself never reads a
    clock; a clock inside the package would put a moving number into a
    drift-gated artifact."""

    def test_the_experiment_costs_under_thirty_seconds(self) -> None:
        start = time.perf_counter()
        run_experiment(FIXTURES)
        elapsed = time.perf_counter() - start
        assert elapsed < 30.0, elapsed


class TestG10BelowChanceAmplification:
    """G10 - the honesty exhibit. Compute multiplies whatever competence is
    there; when there is none, it multiplies the absence."""

    def test_voting_makes_a_below_chance_panel_worse(
        self, result: ExperimentResult
    ) -> None:
        loss = catch(result, ARM_BELOW_CHANCE, 1) - catch(result, ARM_BELOW_CHANCE, 9)
        assert loss >= 0.15, loss

    def test_the_below_chance_curve_never_climbs(
        self, result: ExperimentResult
    ) -> None:
        curve = [catch(result, ARM_BELOW_CHANCE, k) for k in K_VALUES]
        assert curve == sorted(curve, reverse=True), curve


class TestPublishedArtifactsConform:
    """The README block and the curve must be RENDERED from the committed
    metrics, not typed - the drift gate is what makes the numbers claims."""

    def test_the_readme_block_renders_from_the_committed_metrics(self) -> None:
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        rendered = render_ttc_table(load_ttc_metrics(TTC_METRICS))
        begin = readme.index(TTC_BEGIN) + len(TTC_BEGIN)
        assert readme[begin : readme.index(TTC_END)].strip() == rendered.strip()

    def test_the_curve_svg_renders_from_the_committed_metrics(self) -> None:
        rendered = render_ttc_curve_svg(load_ttc_metrics(TTC_METRICS))
        assert TTC_CURVE.read_text(encoding="utf-8") == rendered

    def test_every_published_float_is_fixed_to_four_decimals(self) -> None:
        for line in TTC_METRICS.read_text(encoding="utf-8").splitlines():
            for key, value in json.loads(line).items():
                if isinstance(value, float):
                    assert round(value, 4) == value, (key, value)

    def test_no_wallclock_shape_in_the_new_artifacts(self) -> None:
        pattern = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}:\d{2}")
        for path in (TTC_METRICS, TTC_CURVE, REPO / "README.md"):
            assert not pattern.search(path.read_text(encoding="utf-8")), path.name
