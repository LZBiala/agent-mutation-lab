"""The pipeline: build the batch, dispatch the reviewer, score against the
sealed key, and leave a fully auditable paper trail.

Scoring rules (stated here, tested, and printed into the README):
- HIT: on a mutant, any finding whose class matches the planted class within
  LINE_TOLERANCE lines of the planted line.
- MISS: a mutant with no matching finding.
- FALSE ALARM: any finding at all on a byte-identical clean control file.
- SPURIOUS: a finding on a mutant that does NOT match the planted defect —
  counted and published, so noisy reviewers pay a visible price on mutants
  too, not only on the clean arm.
A reviewer that flags everything maxes false alarms and spurious counts; one
that flags nothing maxes misses. The measurement lives between.

Nothing here reads a clock or the network; artifacts are deterministic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from mutationlab.batch import batch_file_name, build_batch, seal_key
from mutationlab.defects import EngineError
from mutationlab.reviewer import Finding, Reviewer

Emit = Callable[[str], None]
LINE_TOLERANCE = 2


def match_findings(
    class_id: str, line: int, findings: list[Finding]
) -> tuple[tuple[Finding, ...], tuple[Finding, ...]]:
    """Split a review into (matching the planted defect, spurious).

    HIT semantics live here and ONLY here. The pipeline and the inference-
    compute experiment both score through this function, so a panel of nine
    reviewers is judged by exactly the rule a single reviewer is judged by —
    two definitions of "hit" would make the two studies incomparable while
    both looked right.
    """
    matching: list[Finding] = []
    spurious: list[Finding] = []
    for finding in findings:
        if finding.class_id == class_id and abs(finding.line - line) <= LINE_TOLERANCE:
            matching.append(finding)
        else:
            spurious.append(finding)
    return tuple(matching), tuple(spurious)


@dataclass(frozen=True)
class ClassScore:
    class_id: str
    mutants: int
    hits: int
    misses: int


@dataclass(frozen=True)
class RunScore:
    reviewer: str
    per_class: tuple[ClassScore, ...]
    clean_files: int
    false_alarms: int
    spurious_on_mutants: int
    total_mutants: int
    total_hits: int

    def to_json_lines(self) -> list[str]:
        rows: list[dict[str, object]] = [
            {
                "kind": "class",
                "class_id": c.class_id,
                "mutants": c.mutants,
                "hits": c.hits,
                "misses": c.misses,
            }
            for c in self.per_class
        ]
        rows.append(
            {
                "kind": "summary",
                "reviewer": self.reviewer,
                "clean_files": self.clean_files,
                "false_alarms": self.false_alarms,
                "spurious_on_mutants": self.spurious_on_mutants,
                "total_mutants": self.total_mutants,
                "total_hits": self.total_hits,
            }
        )
        return [json.dumps(r, sort_keys=True) for r in rows]


@dataclass
class _Tally:
    mutants: int = 0
    hits: int = 0
    notes: list[str] = field(default_factory=list)


def run_pipeline(
    fixtures: dict[str, str],
    reviewer: Reviewer,
    batches_dir: Path,
    runs_dir: Path,
    emit: Emit,
) -> RunScore:
    items = build_batch(fixtures)
    # The key is answer-side material: it lives OUTSIDE the reviewable
    # directory, and the batch files carry opaque names so a file-fed
    # reviewer cannot read the planted class off a filename.
    seal_key(items, runs_dir / "answer-key.json")
    batches_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(sorted(items, key=lambda i: i.item_id)):
        path = batches_dir / batch_file_name(index)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(item.text)

    verdict_lines: list[str] = [
        "# review verdicts",
        "",
        f"Reviewer: {reviewer.name}. Rules: HIT = planted class within "
        f"±{LINE_TOLERANCE} lines of the planted line; any finding on a clean "
        "control is a FALSE ALARM.",
        "",
    ]
    tallies: dict[str, _Tally] = {}
    clean_files = 0
    false_alarms = 0
    spurious_on_mutants = 0

    for item in sorted(items, key=lambda i: i.item_id):
        findings = reviewer.review(item.source_name, item.text)
        if item.kind == "clean":
            clean_files += 1
            false_alarms += len(findings)
            verdict = "CLEAN-OK" if not findings else f"FALSE-ALARM x{len(findings)}"
            verdict_lines.append(f"- {item.item_id}: {verdict}")
            emit(f"REVIEW {item.item_id} -> {verdict}")
            continue
        if item.class_id is None or item.line is None:
            raise EngineError(f"mutant item {item.item_id!r} lacks class/line")
        tally = tallies.setdefault(item.class_id, _Tally())
        tally.mutants += 1
        matching, spurious = match_findings(item.class_id, item.line, findings)
        spurious_on_mutants += len(spurious)
        if matching:
            tally.hits += 1
            verdict = f"HIT at line {item.line}"
        else:
            verdict = f"MISS (planted {item.class_id} at line {item.line})"
        verdict_lines.append(f"- {item.item_id}: {verdict}")
        emit(f"REVIEW {item.item_id} -> {verdict}")

    runs_dir.mkdir(parents=True, exist_ok=True)
    with (runs_dir / "verdicts.md").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(verdict_lines) + "\n")

    per_class = tuple(
        ClassScore(
            class_id=class_id,
            mutants=tally.mutants,
            hits=tally.hits,
            misses=tally.mutants - tally.hits,
        )
        for class_id, tally in sorted(tallies.items())
    )
    return RunScore(
        reviewer=reviewer.name,
        per_class=per_class,
        clean_files=clean_files,
        false_alarms=false_alarms,
        spurious_on_mutants=spurious_on_mutants,
        total_mutants=sum(c.mutants for c in per_class),
        total_hits=sum(c.hits for c in per_class),
    )


def write_metrics(score: RunScore, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for line in score.to_json_lines():
            fh.write(line + "\n")
