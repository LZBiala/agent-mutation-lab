"""Batch builder: mutants + byte-identical clean controls + a sealed key.

The clean control arm is the point: scoring recall without a false-alarm arm
rewards a reviewer that cries defect at everything — the cheapest possible
way to score 100%. Every fixture appears once as a byte-identical CLEAN item,
and every applicable (mutator, fixture) pair appears once as a mutant.

On disk, batch files carry OPAQUE names (item-01.py, item-02.py, ...): a
reviewable corpus whose filenames named the planted class would hand any
file-fed reviewer the answers. The id→file mapping lives only in the answer
key, which is sealed OUTSIDE the reviewable directory — generated with the
batch, never hand-edited.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mutationlab.defects import MUTATORS, apply


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
    return items


def batch_file_name(index: int) -> str:
    """Opaque on-disk name for the item at `index` of the id-sorted order."""
    return f"item-{index + 1:02d}.py"


def seal_key(items: list[BatchItem], path: Path) -> None:
    """The answer key: everything but the text, sorted by item id, including
    the opaque on-disk file each item was written to."""
    records = [
        {
            "item_id": item.item_id,
            "file": batch_file_name(index),
            "source_name": item.source_name,
            "kind": item.kind,
            "class_id": item.class_id,
            "line": item.line,
        }
        for index, item in enumerate(sorted(items, key=lambda i: i.item_id))
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(records, fh, indent=2, sort_keys=True)
        fh.write("\n")
