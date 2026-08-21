"""PanelReviewer contracts: the vote key, the threshold, and the arithmetic
the whole study is compared against.

The vote key is (line, class_id) and NOTHING else. Including the note would
let two reviewers who found the same defect in different words fail to agree —
the panel would measure prose similarity instead of agreement.

condorcet_prediction is the theoretical curve every empirical point is checked
against. It holds only where per-member accuracy p exceeds one half; below
that, the same arithmetic runs backwards and voting amplifies error.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from mutationlab.panel import (
    PanelReviewer,
    condorcet_prediction,
    majority_threshold,
    majority_vote,
)
from mutationlab.reviewer import Finding, Reviewer


@dataclass(frozen=True)
class _Fixed(Reviewer):
    """A reviewer that always returns the same findings — a voting seat."""

    findings: tuple[Finding, ...] = ()
    name: str = "FixedReviewer"

    def review(self, source_name: str, text: str) -> list[Finding]:
        return list(self.findings)


def _seat(*findings: Finding) -> _Fixed:
    return _Fixed(findings=findings)


BUG = Finding(line=12, class_id="broad-except", note="over-broad except")
OTHER = Finding(line=40, class_id="encoding-drop", note="no encoding")


class TestThreshold:
    def test_majority_threshold_per_panel_size(self) -> None:
        assert [majority_threshold(k) for k in (1, 3, 5, 7, 9)] == [1, 2, 3, 4, 5]

    def test_even_panels_are_refused(self) -> None:
        """An even panel can tie, and a tie has no majority — the study only
        ever runs odd k, so the code refuses the ambiguous case outright."""
        for k in (0, 2, 4, 8):
            with pytest.raises(ValueError):
                majority_threshold(k)
        with pytest.raises(ValueError):
            PanelReviewer(members=(_seat(BUG), _seat(BUG)))


class TestVoting:
    def test_unanimous_findings_survive(self) -> None:
        panel = PanelReviewer(members=tuple(_seat(BUG) for _ in range(5)))
        assert panel.review("x", "") == [BUG]

    def test_exactly_half_the_seats_is_not_a_majority(self) -> None:
        for k in (3, 5, 7, 9):
            voters = k // 2  # one short of the threshold at every odd k
            members = tuple(
                _seat(BUG) if i < voters else _seat() for i in range(k)
            )
            assert PanelReviewer(members=members).review("x", "") == [], k

    def test_one_more_than_half_carries_the_vote(self) -> None:
        for k in (3, 5, 7, 9):
            voters = majority_threshold(k)
            members = tuple(
                _seat(BUG) if i < voters else _seat() for i in range(k)
            )
            assert PanelReviewer(members=members).review("x", "") == [BUG], k

    def test_a_single_seat_cannot_carry_a_larger_panel(self) -> None:
        members = (_seat(BUG), _seat(), _seat())
        assert PanelReviewer(members=members).review("x", "") == []


class TestVoteKey:
    def test_the_note_is_excluded_from_the_key(self) -> None:
        loud = Finding(line=12, class_id="broad-except", note="CATASTROPHIC")
        quiet = Finding(line=12, class_id="broad-except", note="minor nit")
        panel = PanelReviewer(members=(_seat(loud), _seat(quiet), _seat()))
        assert len(panel.review("x", "")) == 1

    def test_the_surviving_note_comes_from_the_lowest_member_index(self) -> None:
        first = Finding(line=12, class_id="broad-except", note="from seat zero")
        second = Finding(line=12, class_id="broad-except", note="from seat one")
        panel = PanelReviewer(members=(_seat(first), _seat(second), _seat(second)))
        assert panel.review("x", "") == [first]

    def test_a_different_line_is_a_different_cell(self) -> None:
        near = Finding(line=13, class_id="broad-except", note="one line off")
        panel = PanelReviewer(members=(_seat(BUG), _seat(near), _seat()))
        assert panel.review("x", "") == []


class TestSingleSeatPanel:
    def test_k_one_is_the_identity(self) -> None:
        seat = _seat(BUG, OTHER)
        assert PanelReviewer(members=(seat,)).review("x", "") == [BUG, OTHER]

    def test_majority_vote_of_one_ballot_is_that_ballot(self) -> None:
        assert majority_vote([[OTHER, BUG]]) == [OTHER, BUG]


class TestCondorcetPrediction:
    """Pinned to four decimals: these are the numbers every empirical point in
    the study is measured against, so they may not drift silently."""

    def test_exact_binomial_tail_at_p_seven_tenths(self) -> None:
        got = [round(condorcet_prediction(k, 0.70), 4) for k in (1, 3, 5, 7, 9)]
        assert got == [0.7000, 0.7840, 0.8369, 0.8740, 0.9012]

    def test_below_one_half_the_curve_runs_backwards(self) -> None:
        """The precondition, asserted rather than assumed: under one-half
        member accuracy more seats make the panel WORSE — arm A3's regime."""
        curve = [condorcet_prediction(k, 0.35) for k in (1, 3, 5, 7, 9)]
        assert curve == sorted(curve, reverse=True)
        assert curve[0] == pytest.approx(0.35)

    def test_one_half_is_the_fixed_point(self) -> None:
        for k in (1, 3, 5, 7, 9):
            assert condorcet_prediction(k, 0.5) == pytest.approx(0.5)

    def test_certainty_in_certainty_out(self) -> None:
        assert condorcet_prediction(9, 1.0) == pytest.approx(1.0)
        assert condorcet_prediction(9, 0.0) == pytest.approx(0.0)
