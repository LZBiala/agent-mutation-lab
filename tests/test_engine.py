"""Engine contract: mutate-or-refuse-never-noop, determinism, one focused
edit, struck-line accuracy, and a real applicability matrix.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mutationlab.defects import MUTATORS, Mutant, apply, applicable

REPO = Path(__file__).resolve().parents[1]
FIXTURES = {
    p.stem: p.read_text(encoding="utf-8")
    for p in sorted((REPO / "fixtures" / "catalog_app").glob("*.py"))
}


def all_pairs() -> list[tuple[str, str]]:
    return [(m.class_id, name) for m in MUTATORS for name in FIXTURES]


class TestContract:
    @pytest.mark.parametrize("mutator", MUTATORS, ids=lambda m: m.class_id)
    def test_applies_somewhere_and_refuses_elsewhere(self, mutator) -> None:
        hits = [n for n, text in FIXTURES.items() if applicable(mutator, text)]
        assert hits, f"{mutator.class_id} applies to no fixture - dead pack entry"
        for name, text in FIXTURES.items():
            result = apply(mutator, name, text)
            if name in hits:
                assert isinstance(result, Mutant)
            else:
                assert result is None  # refuse, never guess

    @pytest.mark.parametrize("mutator", MUTATORS, ids=lambda m: m.class_id)
    def test_mutant_differs_and_is_deterministic(self, mutator) -> None:
        for name, text in FIXTURES.items():
            first = apply(mutator, name, text)
            second = apply(mutator, name, text)
            assert first == second  # deterministic
            if first is not None:
                assert first.text != text  # never a silent no-op

    @pytest.mark.parametrize("mutator", MUTATORS, ids=lambda m: m.class_id)
    def test_edit_is_focused_on_the_reported_line(self, mutator) -> None:
        for name, text in FIXTURES.items():
            mutant = apply(mutator, name, text)
            if mutant is None:
                continue
            src_lines = text.split("\n")
            mut_lines = mutant.text.split("\n")
            assert len(src_lines) == len(mut_lines)  # one-line edits only
            changed = [
                i + 1
                for i, (a, b) in enumerate(zip(src_lines, mut_lines, strict=True))
                if a != b
            ]
            assert changed == [mutant.line]

    def test_refusal_on_unrelated_source(self) -> None:
        unrelated = "def hello() -> str:\n    return 'greetings'\n"
        for mutator in MUTATORS:
            assert apply(mutator, "unrelated", unrelated) is None

    def test_every_fixture_is_targeted_at_least_twice(self) -> None:
        for name, text in FIXTURES.items():
            count = sum(1 for m in MUTATORS if applicable(m, text))
            assert count >= 2, f"{name} targeted by only {count} mutator(s)"

    def test_class_ids_unique_and_stories_present(self) -> None:
        ids = [m.class_id for m in MUTATORS]
        assert len(ids) == len(set(ids)) and len(ids) >= 9
        for m in MUTATORS:
            assert len(m.story) > 60, f"{m.class_id} story too thin to teach"


class TestMutantsAreBehavioral:
    """R5.3: showcase classes are REAL bugs - the mutated module misbehaves.

    Each probe execs the (self-contained) fixture module text and drives the
    bug: pass on clean, misbehave on mutant.
    """

    @staticmethod
    def run_module(text: str) -> dict[str, object]:
        namespace: dict[str, object] = {}
        exec(compile(text, "<fixture>", "exec"), namespace)  # noqa: S102 - executing our own fixture under test
        return namespace

    def test_mutable_default_shares_state(self) -> None:
        mutator = next(m for m in MUTATORS if m.class_id == "mutable-default")
        clean = self.run_module(FIXTURES["catalog"])
        mutant = self.run_module(apply(mutator, "catalog", FIXTURES["catalog"]).text)  # type: ignore[union-attr]

        def probe(ns: dict[str, object]) -> bool:
            catalog: dict[str, dict[str, object]] = {}
            entry_a = ns["add_book"](catalog, "A Tale of Two Rivers", 1)  # type: ignore[operator]
            entry_a["tags"].append("classic")  # type: ignore[union-attr, index]
            entry_b = ns["add_book"](catalog, "Bridge Engineering", 1)  # type: ignore[operator]
            return entry_b["tags"] == []  # type: ignore[index]

        assert probe(clean) is True
        assert probe(mutant) is False  # the shared list leaked

    def test_off_by_one_breaks_the_limit(self) -> None:
        mutator = next(m for m in MUTATORS if m.class_id == "off-by-one-slice")
        clean = self.run_module(FIXTURES["catalog"])
        mutant = self.run_module(apply(mutator, "catalog", FIXTURES["catalog"]).text)  # type: ignore[union-attr]
        catalog = {t: {"copies": 1, "status": "available", "tags": []} for t in ("a", "ab", "abc")}
        assert len(clean["search"](catalog, "a", 2)) == 2  # type: ignore[operator]
        assert len(mutant["search"](catalog, "a", 2)) == 3  # type: ignore[operator]

    def test_wrong_variable_bills_wrong(self) -> None:
        mutator = next(m for m in MUTATORS if m.class_id == "wrong-variable")
        clean = self.run_module(FIXTURES["loans"])
        mutant = self.run_module(apply(mutator, "loans", FIXTURES["loans"]).text)  # type: ignore[union-attr]

        def fee(ns: dict[str, object]) -> int:
            loans: dict[str, dict[str, int]] = {}
            ns["borrow"](loans, "kim", "Handbook of Bridges", 1)  # type: ignore[operator]
            return ns["return_book"](loans, "kim", "Handbook of Bridges", 18)  # type: ignore[operator, return-value]

        assert fee(clean) == 6  # 3 days late * 2 per day
        assert fee(mutant) == 3  # days returned instead of fee

    def test_validation_boundary_admits_zero(self) -> None:
        mutator = next(m for m in MUTATORS if m.class_id == "validation-boundary")
        clean = self.run_module(FIXTURES["catalog"])
        mutant = self.run_module(apply(mutator, "catalog", FIXTURES["catalog"]).text)  # type: ignore[union-attr]
        with pytest.raises(Exception, match="at least 1"):
            clean["add_book"]({}, "Zero Copies", 0)  # type: ignore[operator]
        entry = mutant["add_book"]({}, "Zero Copies", 0)  # type: ignore[operator]
        assert entry["copies"] == 0  # type: ignore[index]
