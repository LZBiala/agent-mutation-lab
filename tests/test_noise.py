"""NoisyReviewer contracts: reproducible, trial- and member-distinct,
order-independent, and BLIND to the answer key.

The key-blindness tests are the load-bearing ones. Noise that fires only on
clean files is answer-key leakage wearing a lab coat: it hands the panel a
free signal no real reviewer gets, and every catch curve measured on top of it
is fiction. So the false-alarm rate is measured separately on clean texts and
on mutant texts, and the two must agree.

The invented-finding class pool is REVIEWER-SIDE knowledge (the classes the
base reviewer carries a rule for), never the full defect taxonomy: a reviewer
cannot idly hallucinate a class it has no detector for, and letting the noise
draw the rule-less class would let luck alone produce a "hit" on the very
blind spot the wall exhibit is measuring.

The empirical-rate tests use a REPLAY stand-in for the base reviewer - the
same findings MockReviewer produces, precomputed once - because these tests
draw thousands of streams and the base pass is identical every time.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from mutationlab.batch import build_batch
from mutationlab.noise import NoisyReviewer
from mutationlab.reviewer import RULE_CLASSES, Finding, MockReviewer, Reviewer

REPO = Path(__file__).resolve().parents[1]
FIXTURES = {
    p.stem: p.read_text(encoding="utf-8")
    for p in sorted((REPO / "fixtures" / "catalog_app").glob("*.py"))
}
ITEMS = build_batch(FIXTURES)
CLEAN_TEXTS = [i.text for i in ITEMS if i.kind == "clean"]
MUTANT_TEXTS = [i.text for i in ITEMS if i.kind == "mutant"]
CLASS_POOL = tuple(sorted(RULE_CLASSES))
SEED = "noise-test"


@dataclass(frozen=True)
class _Replay(Reviewer):
    """MockReviewer's verdicts, precomputed - same findings, no rescan."""

    by_text: dict[str, list[Finding]] = field(default_factory=dict)
    name: str = "ReplayReviewer"

    def review(self, source_name: str, text: str) -> list[Finding]:
        return list(self.by_text[text])


def _replay_base() -> _Replay:
    mock = MockReviewer()
    return _Replay(by_text={t: mock.review("x", t) for t in CLEAN_TEXTS + MUTANT_TEXTS})


def _noisy(
    base: Reviewer,
    member_index: int,
    trial: int = 0,
    miss_rate: float = 0.30,
    fa_rate: float = 0.10,
) -> NoisyReviewer:
    return NoisyReviewer(
        base=base,
        run_seed=SEED,
        trial=trial,
        member_index=member_index,
        miss_rate=miss_rate,
        fa_rate=fa_rate,
        class_ids=CLASS_POOL,
    )


class TestDeterminism:
    def test_same_seed_twice_is_identical(self) -> None:
        a = _noisy(MockReviewer(), 3)
        b = _noisy(MockReviewer(), 3)
        for text in CLEAN_TEXTS + MUTANT_TEXTS:
            assert a.review("x", text) == b.review("x", text)

    def test_review_order_does_not_change_any_verdict(self) -> None:
        """The stream is keyed by (run seed, trial, member, file hash) - never
        by call order - so a shuffled batch yields identical per-file verdicts."""
        reviewer = _noisy(MockReviewer(), 2)
        texts = CLEAN_TEXTS + MUTANT_TEXTS
        forward = {t: reviewer.review("x", t) for t in texts}
        backward = {t: reviewer.review("x", t) for t in reversed(texts)}
        assert forward == backward

    def test_distinct_members_diverge(self) -> None:
        a = _noisy(MockReviewer(), 0)
        b = _noisy(MockReviewer(), 1)
        assert any(
            a.review("x", t) != b.review("x", t) for t in CLEAN_TEXTS + MUTANT_TEXTS
        )

    def test_distinct_trials_diverge(self) -> None:
        """Without the trial in the seed every trial replays one stream: n
        collapses from 1800 to 9 and every error bar in the study is fiction."""
        first = _noisy(MockReviewer(), 0, trial=0)
        second = _noisy(MockReviewer(), 0, trial=1)
        assert any(
            first.review("x", t) != second.review("x", t)
            for t in CLEAN_TEXTS + MUTANT_TEXTS
        )


class TestNoiseBoundaries:
    def test_zero_noise_is_an_identity_wrapper(self) -> None:
        base = MockReviewer()
        quiet = _noisy(base, 4, miss_rate=0.0, fa_rate=0.0)
        for text in CLEAN_TEXTS + MUTANT_TEXTS:
            assert quiet.review("x", text) == base.review("x", text)

    def test_miss_rate_one_drops_everything(self) -> None:
        blind = _noisy(MockReviewer(), 4, miss_rate=1.0, fa_rate=0.0)
        for text in CLEAN_TEXTS + MUTANT_TEXTS:
            assert blind.review("x", text) == []


class TestKeyBlindness:
    """The noise model never sees item kind or the key - so its false-alarm
    rate must be statistically the same on clean and mutant texts."""

    MEMBERS = 400

    def _invented(self, base: _Replay, member: int, text: str) -> list[Finding]:
        truth = set(base.review("x", text))
        return [f for f in _noisy(base, member).review("x", text) if f not in truth]

    def _fa_rate(self, texts: list[str], base: _Replay) -> float:
        fired = sum(
            len(self._invented(base, member, text))
            for member in range(self.MEMBERS)
            for text in texts
        )
        return fired / (self.MEMBERS * len(texts))

    def test_false_alarm_rate_matches_on_clean_and_mutant_texts(self) -> None:
        base = _replay_base()
        clean = self._fa_rate(CLEAN_TEXTS, base)
        mutant = self._fa_rate(MUTANT_TEXTS, base)
        assert abs(clean - 0.10) <= 0.04, clean
        assert abs(mutant - 0.10) <= 0.04, mutant
        assert abs(clean - mutant) <= 0.04, (clean, mutant)

    def test_at_most_one_false_alarm_per_file(self) -> None:
        base = _replay_base()
        for member in range(50):
            for text in CLEAN_TEXTS + MUTANT_TEXTS:
                assert len(self._invented(base, member, text)) <= 1

    def test_invented_findings_only_ever_carry_a_pool_class(self) -> None:
        """The rule-less wall class is not in the pool, so no lucky invented
        finding can ever score on it - the wall reads zero by construction."""
        base = _replay_base()
        seen: set[str] = set()
        for member in range(200):
            for text in CLEAN_TEXTS + MUTANT_TEXTS:
                for finding in self._invented(base, member, text):
                    seen.add(finding.class_id)
        assert seen, "no false alarms fired at all - the rate test is a lie"
        assert seen <= set(CLASS_POOL), seen - set(CLASS_POOL)

    def test_invented_lines_stay_inside_the_file(self) -> None:
        base = _replay_base()
        for member in range(100):
            for text in CLEAN_TEXTS + MUTANT_TEXTS:
                limit = len(text.splitlines())
                for finding in self._invented(base, member, text):
                    assert 1 <= finding.line <= limit


class TestRetainRate:
    def test_empirical_retain_rate_is_within_five_points_of_the_setting(self) -> None:
        base = _replay_base()
        kept = 0
        total = 0
        for member in range(300):
            reviewer = _noisy(base, member, fa_rate=0.0)
            for text in MUTANT_TEXTS:
                total += len(base.review("x", text))
                kept += len(reviewer.review("x", text))
        assert total > 0
        assert abs(kept / total - 0.70) <= 0.05, kept / total


class TestKeyBlindByConstruction:
    """Blindness is a claim about IMPORTS, not only about rates: a module that
    can reach the batch (item kind) or the runner (scoring) can leak the key by
    accident later. Parse the AST and forbid the edge."""

    def test_noise_module_imports_neither_batch_nor_runner(self) -> None:
        tree = ast.parse((REPO / "src" / "mutationlab" / "noise.py").read_text("utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
        assert "mutationlab.batch" not in modules, modules
        assert "mutationlab.runner" not in modules, modules
