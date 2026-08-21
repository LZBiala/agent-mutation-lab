"""End-to-end guarantees: determinism (double run byte-identical), no
wall-clock in artifacts, keyless imports, hygiene gate, README prose pinned,
and the in-process demo path (temp copy - never the real tree).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WALLCLOCK_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}:\d{2}")
FORBIDDEN_IMPORTS = ("socket", "urllib", "http.client", "requests", "subprocess")


def run_demo(workdir: Path) -> None:
    shutil.copytree(REPO / "src", workdir / "src")
    shutil.copytree(REPO / "fixtures", workdir / "fixtures")
    shutil.copy(REPO / "README.md", workdir / "README.md")
    result = subprocess.run(  # noqa: S603 - running our own module under test
        [sys.executable, "-m", "mutationlab", "demo", "--quiet"],
        cwd=workdir,
        env={**os.environ, "PYTHONPATH": str(workdir / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def artifact_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for sub in ("batches", "runs", "report"):
        out.extend(sorted(p for p in (root / sub).rglob("*") if p.is_file()))
    out.append(root / "metrics.jsonl")
    out.append(root / "README.md")
    return out


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workdir = tmp_path_factory.mktemp("run_a")
    run_demo(workdir)
    return workdir


class TestPipeline:
    def test_score_summary_matches_design(self, demo_run: Path) -> None:
        rows = [
            json.loads(line)
            for line in (demo_run / "metrics.jsonl").read_text("utf-8").splitlines()
        ]
        summary = next(r for r in rows if r["kind"] == "summary")
        assert summary["total_hits"] == summary["total_mutants"] - 1  # one blind spot
        assert summary["false_alarms"] == 0
        classes = [r for r in rows if r["kind"] == "class"]
        assert len(classes) >= 9

    def test_verdicts_show_the_miss(self, demo_run: Path) -> None:
        verdicts = (demo_run / "runs" / "verdicts.md").read_text("utf-8")
        assert "MISS (planted boolean-precedence" in verdicts
        assert "CLEAN-OK" in verdicts

    def test_answer_key_never_contains_source_text(self, demo_run: Path) -> None:
        records = json.loads(
            (demo_run / "runs" / "answer-key.json").read_text("utf-8")
        )
        assert records and all("text" not in r for r in records)

    def test_no_wallclock_in_artifacts(self, demo_run: Path) -> None:
        hits: list[str] = []
        for path in artifact_files(demo_run):
            for lineno, line in enumerate(path.read_text("utf-8").splitlines(), 1):
                if WALLCLOCK_RE.search(line):
                    hits.append(f"{path.name}:{lineno}: {line.strip()[:70]}")
        assert not hits, f"wall-clock patterns in artifacts: {hits}"


class TestDeterminism:
    def test_two_runs_are_byte_identical(
        self, demo_run: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        second = tmp_path_factory.mktemp("run_b")
        run_demo(second)
        files_a = artifact_files(demo_run)
        files_b = artifact_files(second)
        assert [p.relative_to(demo_run) for p in files_a] == [
            p.relative_to(second) for p in files_b
        ]
        for pa, pb in zip(files_a, files_b, strict=True):
            assert pa.read_bytes() == pb.read_bytes(), f"drift in {pa.name}"


class TestKeyless:
    def test_no_network_clock_or_process_imports_in_package(self) -> None:
        for path in sorted((REPO / "src" / "mutationlab").glob("*.py")):
            text = path.read_text("utf-8")
            for module in FORBIDDEN_IMPORTS:
                assert f"import {module}" not in text, f"{module} in {path.name}"
            assert "datetime" not in text and "time.time" not in text, path.name


class TestReadmePinned:
    README_TEXT = (REPO / "README.md").read_text(encoding="utf-8")

    def test_prose_constants_match_the_pack(self) -> None:
        from mutationlab.defects import MUTATORS

        assert f"**{len(MUTATORS)} classes**" in self.README_TEXT

    def test_diff_excerpt_matches_the_actual_mutation(self) -> None:
        from mutationlab.defects import MUTATORS, apply

        mutator = next(m for m in MUTATORS if m.class_id == "mutable-default")
        clean = (REPO / "fixtures" / "catalog_app" / "catalog.py").read_text("utf-8")
        mutant = apply(mutator, "catalog", clean)
        assert mutant is not None
        removed = clean.split("\n")[mutant.line - 1]
        added = mutant.text.split("\n")[mutant.line - 1]
        assert f"-{removed}" in self.README_TEXT
        assert f"+{added}" in self.README_TEXT

    def test_no_wallclock_in_readme(self) -> None:
        assert not WALLCLOCK_RE.search(self.README_TEXT)


class TestInProcessCoverage:
    def test_demo_runs_in_process_on_a_temp_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import mutationlab.__main__ as main_mod

        shutil.copytree(REPO / "fixtures", tmp_path / "fixtures")
        shutil.copy(REPO / "README.md", tmp_path / "README.md")
        monkeypatch.setattr(main_mod, "FIXTURES_DIR", tmp_path / "fixtures" / "catalog_app")
        monkeypatch.setattr(main_mod, "README", tmp_path / "README.md")
        monkeypatch.setattr(main_mod, "BATCHES_DIR", tmp_path / "batches")
        monkeypatch.setattr(main_mod, "RUNS_DIR", tmp_path / "runs")
        monkeypatch.setattr(main_mod, "REPORT_DIR", tmp_path / "report")
        monkeypatch.setattr(main_mod, "METRICS", tmp_path / "metrics.jsonl")
        # EVERY output constant must be redirected, not most of them: demo()
        # deletes and rewrites each one, so a single unpatched path makes this
        # test scribble on the real repo's committed artifacts mid-suite - and
        # a later test that reads those artifacts would then be grading this
        # test's output instead of what is committed.
        monkeypatch.setattr(main_mod, "METRICS_TTC", tmp_path / "metrics-ttc.jsonl")
        assert main_mod.demo(quiet=True) == 0
        for name in (
            "metrics.jsonl",
            "metrics-ttc.jsonl",
            "report/scorecard.svg",
            "report/ttc-curve.svg",
            "runs/answer-key.json",
        ):
            assert (tmp_path / name).exists(), name


class TestHygieneGate:
    def test_repo_passes_its_own_gate(self) -> None:
        result = subprocess.run(  # noqa: S603 - running our own tool under test
            [sys.executable, str(REPO / "tools" / "blocklist_check.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout
