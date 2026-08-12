"""Batch + reviewer contracts: control arms byte-identical, key sealed and
correct, deterministic order; MockReviewer silent on clean files, and the
deliberate boolean-precedence blind spot present.
"""
from __future__ import annotations

import json
from pathlib import Path

from mutationlab.batch import build_batch, seal_key
from mutationlab.defects import MUTATORS
from mutationlab.reviewer import MockReviewer

REPO = Path(__file__).resolve().parents[1]
FIXTURES = {
    p.stem: p.read_text(encoding="utf-8")
    for p in sorted((REPO / "fixtures" / "catalog_app").glob("*.py"))
}


class TestBatch:
    def test_clean_controls_are_byte_identical(self) -> None:
        items = build_batch(FIXTURES)
        cleans = [i for i in items if i.kind == "clean"]
        assert len(cleans) == len(FIXTURES)
        for item in cleans:
            assert item.text == FIXTURES[item.source_name]
            assert item.class_id is None and item.line is None

    def test_every_applicable_pair_present_exactly_once(self) -> None:
        from mutationlab.defects import applicable

        items = build_batch(FIXTURES)
        ids = [i.item_id for i in items]
        assert len(ids) == len(set(ids))
        expected_pairs = {
            (m.class_id, name)
            for m in MUTATORS
            for name, text in FIXTURES.items()
            if applicable(m, text)
        }
        actual_pairs = {
            (i.class_id, i.source_name) for i in items if i.kind == "mutant"
        }
        assert actual_pairs == expected_pairs  # the name's promise, exactly

    def test_batch_order_is_deterministic(self) -> None:
        a = [i.item_id for i in build_batch(FIXTURES)]
        b = [i.item_id for i in build_batch(FIXTURES)]
        assert a == b

    def test_key_seals_everything_but_text(self, tmp_path: Path) -> None:
        items = build_batch(FIXTURES)
        key_path = tmp_path / "key.json"
        seal_key(items, key_path)
        records = json.loads(key_path.read_text("utf-8"))
        assert len(records) == len(items)
        by_id = {r["item_id"]: r for r in records}
        for item in items:
            rec = by_id[item.item_id]
            assert rec["kind"] == item.kind and rec["line"] == item.line
            assert "text" not in rec


class TestMockReviewer:
    def test_silent_on_every_clean_fixture(self) -> None:
        reviewer = MockReviewer()
        for name, text in FIXTURES.items():
            assert reviewer.review(name, text) == [], name

    def test_exactly_one_deliberate_miss(self) -> None:
        reviewer = MockReviewer()
        missed: list[str] = []
        total = 0
        for item in build_batch(FIXTURES):
            if item.kind != "mutant":
                continue
            total += 1
            findings = reviewer.review(item.source_name, item.text)
            matched = any(
                f.class_id == item.class_id and abs(f.line - (item.line or 0)) <= 2
                for f in findings
            )
            if not matched:
                missed.append(str(item.class_id))
        # ONE blind spot, and it is the documented one. An accidental second
        # miss (the def-anchored mutable-default rule vs multi-line
        # signatures) slipped through this exact test's first version.
        assert missed == ["boolean-precedence"], missed
        assert total >= 10

    def test_the_blind_spot_is_boolean_precedence(self) -> None:
        reviewer = MockReviewer()
        for item in build_batch(FIXTURES):
            if item.kind == "mutant" and item.class_id == "boolean-precedence":
                assert reviewer.review(item.source_name, item.text) == []
