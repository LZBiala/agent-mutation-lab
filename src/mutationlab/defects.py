"""The defect pack: nine injectable defect classes, each a documented,
real-world incident pattern — and the engine that plants exactly one.

Contract (enforced by the test suite):
- A mutator either APPLIES (source differs by one focused edit, struck line
  reported) or REFUSES (returns None). A silent no-op is the worst failure
  available to this module: it would score a reviewer a MISS on a file that
  contains no defect, and nothing in the output would reveal it.
- Deterministic: same source in, same mutant out. The FIRST occurrence of a
  pattern is struck.
- Mutators are regex-narrow on purpose: a half-applied clever transform
  produces a file with no clean answer key. Brittleness admitted and fenced
  beats robustness claimed and unverified.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class EngineError(RuntimeError):
    """Raised when an applied mutation fails its own invariants."""


@dataclass(frozen=True)
class Mutator:
    class_id: str
    title: str
    story: str  # the real-world incident class this represents
    pattern: str  # regex; first occurrence is struck
    replacement: str


@dataclass(frozen=True)
class Mutant:
    class_id: str
    source_name: str
    line: int  # 1-indexed line of the struck edit
    text: str  # full mutated source


MUTATORS: tuple[Mutator, ...] = (
    Mutator(
        class_id="mutable-default",
        title="Mutable default argument",
        story=(
            "A list default is created once at function definition and shared "
            "across every call — state leaks between unrelated invocations. "
            "Classic production symptom: records mysteriously accumulate other "
            "records' data under load."
        ),
        pattern=r"tags: list\[str\] \| None = None",
        replacement="tags: list[str] = []",
    ),
    Mutator(
        class_id="broad-except",
        title="Over-broad exception handler",
        story=(
            "Widening `except ValueError` to `except Exception` silently "
            "converts every unrelated failure — typos, attribute errors, "
            "system errors — into the domain error, hiding the real cause."
        ),
        pattern=r"except ValueError as exc:",
        replacement="except Exception as exc:",
    ),
    Mutator(
        class_id="off-by-one-slice",
        title="Off-by-one in a result limit",
        story=(
            "`[:limit + 1]` returns one more row than the caller asked for. "
            "Pagination and truncation bugs of exactly this shape ship "
            "constantly because the output LOOKS right at a glance."
        ),
        pattern=r"return matches\[:limit\]",
        replacement="return matches[:limit + 1]",
    ),
    Mutator(
        class_id="is-vs-equals",
        title="Identity comparison against a string literal",
        story=(
            "`is` on a string literal works by interning accident in tests "
            "and fails unpredictably in production when the value arrives "
            "from parsing or I/O."
        ),
        pattern=r'== "available"',
        replacement='is "available"',
    ),
    Mutator(
        class_id="encoding-drop",
        title="Platform-default file encoding",
        story=(
            "Dropping the explicit encoding makes the write depend on the "
            "OS locale — the file is fine on the author's machine and "
            "corrupt on the next one. A canonical works-on-my-machine bug."
        ),
        pattern=r'open\("w", encoding="utf-8", newline="\\n"\)',
        replacement='open("w")',
    ),
    Mutator(
        class_id="unsorted-iteration",
        title="Order-dependent iteration without sorting",
        story=(
            "Removing `sorted()` makes output depend on insertion order — "
            "green today, flaky the day the data path changes. "
            "Nondeterminism bugs are the most expensive class to debug."
        ),
        pattern=r"for title in sorted\(catalog\):",
        replacement="for title in catalog:",
    ),
    Mutator(
        class_id="boolean-precedence",
        title="Dropped parentheses change boolean precedence",
        story=(
            "`a and (b or c)` is not `a and b or c` — the second notifies "
            "everyone in the grace window whether or not they are overdue. "
            "Precedence bugs read correctly aloud, which is why they survive "
            "review."
        ),
        pattern=r"is_overdue and \(member_active or in_grace\)",
        replacement="is_overdue and member_active or in_grace",
    ),
    Mutator(
        class_id="wrong-variable",
        title="Returning the wrong same-typed variable",
        story=(
            "Two ints in scope, one returned — the days count instead of the "
            "fee. Type checkers pass, tests that only check 'a number came "
            "back' pass, customers get billed wrong."
        ),
        pattern=r"    return total_fee",
        replacement="    return days_late",
    ),
    Mutator(
        class_id="validation-boundary",
        title="Loosened validation boundary",
        story=(
            "`< 1` becomes `< 0`: zero sneaks through validation and a "
            "zero-copy record exists that no code downstream expects. "
            "Boundary loosenings are one keystroke and one incident."
        ),
        pattern=r"if copies < 1:",
        replacement="if copies < 0:",
    ),
)


def apply(mutator: Mutator, source_name: str, source_text: str) -> Mutant | None:
    """Plant the defect, or REFUSE with None when the pattern is absent."""
    match = re.search(mutator.pattern, source_text)
    if match is None:
        return None
    mutated = (
        source_text[: match.start()]
        + re.sub(mutator.pattern, mutator.replacement, match.group(0))
        + source_text[match.end() :]
    )
    if mutated == source_text:
        raise EngineError(
            f"{mutator.class_id} produced a no-op on {source_name} — "
            f"the worst failure available to this module"
        )
    line = source_text[: match.start()].count("\n") + 1
    return Mutant(
        class_id=mutator.class_id, source_name=source_name, line=line, text=mutated
    )


def applicable(mutator: Mutator, source_text: str) -> bool:
    return re.search(mutator.pattern, source_text) is not None
