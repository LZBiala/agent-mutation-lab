"""Batch builder: mutants + byte-identical clean controls + a sealed key.

The clean control arm is the point: scoring recall without a false-alarm arm
rewards a reviewer that cries defect at everything — the cheapest possible
way to score 100%. Every fixture appears once as a byte-identical CLEAN item,
and every applicable (mutator, fixture) pair appears once as a mutant.

Order is shuffled with a FIXED seed so the batch is deterministic and the
reviewer cannot infer kind from position. The answer key is generated with
the batch and sealed to JSON — never hand-edited.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from mutationlab.defects import MUTATORS, apply

SEED = 20260811


@dataclass(frozen=True)
class BatchItem:
    item_id: str
    source_name: str
    kind: str  # "mutant" | "clean"
    class_id: str | None  # None for clean items
    line: int | None
    text: str


def build_batch(fixtures: dict[str, str]) -> list[BatchItem]:
    items: list[BatchItem] = []
    for name in sorted(fixtures):
        items.append(
            BatchItem(
                item_id=f"clean-{name}",
                source_name=name,
                kind="clean",
                class_id=None,
                line=None,
                text=fixtures[name],
            )
        )
    for mutator in MUTATORS:
        for name in sorted(fixtures):
            mutant = apply(mutator, name, fixtures[name])
            if mutant is None:
                continue
            items.append(
                BatchItem(
                    item_id=f"{mutator.class_id}-{name}",
                    source_name=name,
                    kind="mutant",
                    class_id=mutant.class_id,
                    line=mutant.line,
                    text=mutant.text,
                )
            )
    rng = random.Random(SEED)  # noqa: S311 — fixed seed IS the reproducibility requirement
    rng.shuffle(items)
    return items


def seal_key(items: list[BatchItem], path: Path) -> None:
    """The answer key: everything but the text, sorted by item id."""
    records = [
        {
            "item_id": item.item_id,
            "source_name": item.source_name,
            "kind": item.kind,
            "class_id": item.class_id,
            "line": item.line,
        }
        for item in sorted(items, key=lambda i: i.item_id)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(records, fh, indent=2, sort_keys=True)
        fh.write("\n")
