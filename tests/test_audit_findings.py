"""Regression tests for defects found by independent review of v1.0.

Each class names the finding it pins down: the false-alarm arm only ever
tested at zero, hand-typed figures outside any pin, answer leakage, tolerance
spacing, and substring-based keyless checks.
"""
from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path

from mutationlab.batch import build_batch
from mutationlab.defects import BEHAVIORAL_PROBED_CLASSES, MUTATORS, apply
from mutationlab.reviewer import Finding, Reviewer
from mutationlab.runner import LINE_TOLERANCE, run_pipeline

REPO = Path(__file__).resolve().parents[1]
FIXTURES = {
    p.stem: p.read_text(encoding="utf-8")
    for p in sorted((REPO / "fixtures" / "catalog_app").glob("*.py"))
}


class FlagEverythingReviewer(Reviewer):
    """The cheapest cheat: one finding of every class on line 1 of every file."""

    name = "FlagEverythingReviewer"

    def review(self, source_name: str, text: str) -> list[Finding]:
        return [
            Finding(line=1, class_id=m.class_id, note="wolf!") for m in MUTATORS
        ]


class TestFalseAlarmArmBites:
    """Finding: the FALSE-ALARM branch had zero non-trivial coverage."""

    def test_flag_everything_pays_on_both_arms(self, tmp_path: Path) -> None:
        score = run_pipeline(
            FIXTURES,
            FlagEverythingReviewer(),
            tmp_path / "batches",
            tmp_path / "runs",
            lambda _line: None,
        )
        assert score.false_alarms == len(MUTATORS) * score.clean_files
        assert score.spurious_on_mutants > 0
        verdicts = (tmp_path / "runs" / "verdicts.md").read_text("utf-8")
        assert "FALSE-ALARM x" in verdicts


class TestAnswerLeakageClosed:
    """Finding: mutant filenames named the planted class, and the key sat in
    the reviewable directory."""

    def test_batch_files_are_opaque_and_key_lives_answer_side(
        self, tmp_path: Path
    ) -> None:
        from mutationlab.reviewer import MockReviewer

        run_pipeline(
            FIXTURES,
            MockReviewer(),
            tmp_path / "batches",
            tmp_path / "runs",
            lambda _line: None,
        )
        batch_names = sorted(p.name for p in (tmp_path / "batches").glob("*"))
        assert all(re.fullmatch(r"item-\d{2}\.py", n) for n in batch_names)
        class_ids = {m.class_id for m in MUTATORS}
        for name in batch_names:
            assert not any(cid in name for cid in class_ids)
        assert not (tmp_path / "batches" / "answer-key.json").exists()
        key = json.loads((tmp_path / "runs" / "answer-key.json").read_text("utf-8"))
        assert {r["file"] for r in key} == set(batch_names)


class TestToleranceSpacingContract:
    """Finding: a same-class pattern instance within LINE_TOLERANCE of a plant
    site could credit a hit to the wrong occurrence. The fixture pack must
    keep plant sites isolated."""

    def test_no_same_class_instance_near_any_plant_site(self) -> None:
        for mutator in MUTATORS:
            for name, text in FIXTURES.items():
                mutant = apply(mutator, name, text)
                if mutant is None:
                    continue
                pattern_lines = [
                    i + 1
                    for i, line in enumerate(text.split("\n"))
                    if re.search(mutator.pattern, line)
                ]
                near = [
                    ln
                    for ln in pattern_lines
                    if ln != mutant.line and abs(ln - mutant.line) <= LINE_TOLERANCE
                ]
                assert not near, f"{mutator.class_id} in {name}: instances at {near}"


class TestProbeManifestPinned:
    """Finding: 'N classes proven by executable probes' was a hand-typed
    figure inside the AUTOGEN block. The manifest and the probes must agree."""

    def test_manifest_matches_the_actual_probe_methods(self) -> None:
        from tests.test_engine import TestMutantsAreBehavioral

        probes = [
            name
            for name, _member in inspect.getmembers(
                TestMutantsAreBehavioral, inspect.isfunction
            )
            if name.startswith("test_")
        ]
        assert len(probes) == len(BEHAVIORAL_PROBED_CLASSES)
        for class_id in BEHAVIORAL_PROBED_CLASSES:
            slug = class_id.replace("-", "_")
            short = slug.replace("_slice", "").replace("_arg", "")
            assert any(short in p or slug in p for p in probes), class_id


class TestTolerancePinnedEverywhere:
    """Finding: every '±2' outside verdicts.md was hand-typed. The figure must
    trace to runner.LINE_TOLERANCE on every surface."""

    def test_readme_and_docs_carry_the_interpolated_tolerance(self) -> None:
        needle = f"±{LINE_TOLERANCE}"
        assert needle in (REPO / "README.md").read_text(encoding="utf-8")
        assert needle in (REPO / "docs" / "index.html").read_text(encoding="utf-8")
        assert needle in (REPO / "report" / "scorecard.svg").read_text(encoding="utf-8")


class TestKeylessViaAst:
    """Finding: substring import checks were bypassable. Parse the AST."""

    FORBIDDEN = {"socket", "urllib", "http", "requests", "subprocess", "datetime", "time"}

    def test_no_forbidden_imports_anywhere_in_package(self) -> None:
        for path in sorted((REPO / "src" / "mutationlab").glob("*.py")):
            tree = ast.parse(path.read_text("utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    tops = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    tops = {(node.module or "").split(".")[0]}
                else:
                    continue
                bad = tops & self.FORBIDDEN
                assert not bad, f"{path.name}: forbidden import(s) {bad}"
