"""The pipeline: build the batch, dispatch the reviewer, score against the
sealed key, and leave a fully auditable paper trail.

Scoring rules (stated here, tested, and printed into the README):
- HIT: on a mutant, any finding whose class matches the planted class within
  ±2 lines of the planted line.
- MISS: a mutant with no matching finding.
- FALSE ALARM: any finding at all on a byte-identical clean control file.
A reviewer that flags everything maxes false alarms; one that flags nothing
maxes misses. The interesting region is between — that is the measurement.

Nothing here reads a clock or the network; artifacts are deterministic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from mutationlab.batch import BatchItem, build_batch, seal_key
from mutationlab.reviewer import Reviewer

Emit = Callable[[str], None]
LINE_TOLERANCE = 2


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
    seal_key(items, batches_dir / "answer-key.json")
    for item in items:
        path = batches_dir / f"{item.item_id}.py"
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

    for item in sorted(items, key=lambda i: i.item_id):
        findings = reviewer.review(item.source_name, item.text)
        if item.kind == "clean":
            clean_files += 1
            false_alarms += len(findings)
            verdict = "CLEAN-OK" if not findings else f"FALSE-ALARM x{len(findings)}"
            verdict_lines.append(f"- {item.item_id}: {verdict}")
            emit(f"REVIEW {item.item_id} -> {verdict}")
            continue
        assert item.class_id is not None and item.line is not None
        tally = tallies.setdefault(item.class_id, _Tally())
        tally.mutants += 1
        matched = any(
            f.class_id == item.class_id and abs(f.line - item.line) <= LINE_TOLERANCE
            for f in findings
        )
        if matched:
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
        total_mutants=sum(c.mutants for c in per_class),
        total_hits=sum(c.hits for c in per_class),
    )


def write_metrics(score: RunScore, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for line in score.to_json_lines():
            fh.write(line + "\n")
