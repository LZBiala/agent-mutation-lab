"""Reviewers: the ABC anyone can implement, and the rule-based one that ships.

MockReviewer is deterministic pattern rules - it exists to PROVE THE HARNESS:
that the pipeline plants real defects, seals a correct key, respects the
false-alarm arm, and scores hits at the right lines. Its numbers are harness
conformance, never any model's catch rate.

One rule is deliberately absent: MockReviewer carries NO detection for the
boolean-precedence class, so the shipped scorecard contains a visible MISS.
A harness whose bundled reviewer scores 100% teaches nothing about what a
miss looks like; ours shows one on purpose.

No live-model adapter ships in v1.0 (documented v1.1 seam) - so no published
number can be mistaken for model judgment.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    line: int  # 1-indexed
    class_id: str
    note: str


class Reviewer(ABC):
    """The seam: takes source text, returns findings. Implement with a live
    model if you want real catch rates - those numbers are yours, with your
    error bars, and will never appear in this repo's README."""

    name: str

    @abstractmethod
    def review(self, source_name: str, text: str) -> list[Finding]: ...


# Detection rules aim at the DEFECT side (what bad code looks like) - though
# for value-level defects (wrong-variable, validation-boundary) the bad code
# IS the injected output, so those rules necessarily mirror the injection.
# The README's "What this does NOT show" section owns this circularity out
# loud: these rules prove the harness, nothing more.
_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "mutable-default",
        # Parameter-line rule (signatures are often multi-line, so a def-anchored
        # regex would silently miss them - it did, in this repo's first run).
        r": list\[[^\]]*\] = \[\]",
        "mutable default argument: the list is shared across calls",
    ),
    (
        "broad-except",
        r"except Exception\b",
        "over-broad except: unrelated failures masquerade as the domain error",
    ),
    (
        "off-by-one-slice",
        r"\[:\w+ \+ 1\]",
        "slice returns one more element than the stated limit",
    ),
    (
        "is-vs-equals",
        r'\bis "',
        "identity comparison against a string literal",
    ),
    (
        "encoding-drop",
        r'open\("w"\)',
        "file opened for writing without an explicit encoding",
    ),
    (
        "unsorted-iteration",
        r"for \w+ in catalog:",
        "iteration over a dict whose order the output depends on",
    ),
    # boolean-precedence: DELIBERATELY NO RULE - the shipped miss.
    (
        "wrong-variable",
        r"    return days_late",
        "returns the day count where the fee is documented",
    ),
    (
        "validation-boundary",
        r"if copies < 0:",
        "validation admits zero where the docstring requires at least 1",
    ),
)


# The rule table's own class list, DERIVED - never hand-listed. Two consumers
# depend on it: the blind-spot wall (defect classes MINUS these, so a class
# that ships without a rule joins the wall automatically), and the noise model
# (a reviewer can only cry wolf about classes it carries a detector for).
RULE_CLASSES: frozenset[str] = frozenset(class_id for class_id, _, _ in _RULES)


class MockReviewer(Reviewer):
    name = "MockReviewer"
    banner = (
        "REVIEWER: MockReviewer - deterministic pattern rules, zero API keys; "
        "results are harness conformance, not any model's catch rate"
    )

    def review(self, source_name: str, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for lineno, line in enumerate(text.split("\n"), start=1):
            for class_id, pattern, note in _RULES:
                if re.search(pattern, line):
                    findings.append(Finding(line=lineno, class_id=class_id, note=note))
        return findings
