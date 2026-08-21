"""The panel: k reviewers vote, and the arithmetic they are measured against.

This is the whole test-time-compute move in one file — instead of asking once,
ask k times and keep what a majority agrees on. Two design decisions carry the
result:

THE VOTE KEY IS (line, class_id), NOTHING ELSE. Two members who found the same
defect in different words agree; two members who flagged different lines do
not. Including the note would measure prose similarity instead of agreement.
The surviving note is taken from the lowest member index so the output is a
pure function of the ballots, not of dict ordering.

K IS ODD, ALWAYS. An even panel can tie, and a tie has no majority — rather
than invent a tie-break that no theory covers, even panels are refused.

`condorcet_prediction` is the exact binomial tail the empirical curve is
compared against. It is arithmetic about THIS harness's vote rule, not a
claim about any model. Its famous direction — more voters, better answer —
holds only where per-member accuracy exceeds one half. At exactly one half the
panel is a fixed point, and below it the same formula runs backwards: voting
amplifies error instead of averaging it away.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import comb

from mutationlab.reviewer import Finding, Reviewer


def majority_threshold(k: int) -> int:
    """Votes required to carry a cell on a panel of k: ceil((k + 1) / 2)."""
    if k < 1 or k % 2 == 0:
        raise ValueError(f"panel size must be odd and positive, got {k}")
    return (k + 1) // 2


def majority_vote(ballots: Sequence[Sequence[Finding]]) -> list[Finding]:
    """Keep the (line, class_id) cells that a majority of ballots names.

    Votes count MEMBERS, not findings: a member who names one cell twice still
    has one vote, or a single loud reviewer could carry a panel alone.
    """
    threshold = majority_threshold(len(ballots))
    voters: dict[tuple[int, str], set[int]] = {}
    notes: dict[tuple[int, str], Finding] = {}
    for index, ballot in enumerate(ballots):
        for finding in ballot:
            cell = (finding.line, finding.class_id)
            voters.setdefault(cell, set()).add(index)
            notes.setdefault(cell, finding)  # first writer is the lowest index
    return [notes[cell] for cell, seats in voters.items() if len(seats) >= threshold]


@dataclass(frozen=True)
class PanelReviewer(Reviewer):
    """Runs every member on the same text and returns the majority verdict."""

    members: tuple[Reviewer, ...]
    name: str = "PanelReviewer"

    def __post_init__(self) -> None:
        majority_threshold(len(self.members))  # refuses even and empty panels

    def review(self, source_name: str, text: str) -> list[Finding]:
        return majority_vote([m.review(source_name, text) for m in self.members])


def condorcet_prediction(k: int, p: float) -> float:
    """P(at least ceil((k+1)/2) of k independent members are right), exactly.

    Valid as a PREDICTION only under the independence this harness enforces by
    construction, and only above one-half member accuracy; below that it still
    describes the panel truthfully, but what it describes is amplified error.
    """
    threshold = majority_threshold(k)
    return sum(
        comb(k, i) * p**i * (1.0 - p) ** (k - i) for i in range(threshold, k + 1)
    )
