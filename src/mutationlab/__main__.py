"""CLI: `python -m mutationlab demo` — the whole lab, from clean state, no keys.

Regenerates batches/ (mutants + clean controls + sealed answer key), runs/
(verdict log), metrics.jsonl, report/scorecard.svg, and the README AUTOGEN
block. CI runs exactly this then `git diff --exit-code`: committed artifacts
ARE the claims, and the build fails if they stop regenerating.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mutationlab.report import (
    inject_readme,
    load_metrics,
    render_claims,
    render_scorecard_svg,
)
from mutationlab.reviewer import MockReviewer
from mutationlab.runner import run_pipeline, write_metrics

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "fixtures" / "catalog_app"
BATCHES_DIR = REPO_ROOT / "batches"
RUNS_DIR = REPO_ROOT / "runs"
REPORT_DIR = REPO_ROOT / "report"
METRICS = REPO_ROOT / "metrics.jsonl"
README = REPO_ROOT / "README.md"


def _clean_tree(path: Path) -> None:
    """Delete files, tolerate held directories (sync tools hold handles)."""
    if not path.exists():
        return
    for p in sorted(path.rglob("*"), reverse=True):
        if p.is_file():
            p.unlink()
        else:
            try:
                p.rmdir()
            except OSError:
                pass  # a held directory handle is harmless; files are gone
    try:
        path.rmdir()
    except OSError:
        pass


def demo(quiet: bool) -> int:
    if not (FIXTURES_DIR / "catalog.py").exists():
        print(
            "mutationlab demo must run from a source checkout "
            f"(pip install -e . or PYTHONPATH=src) — fixtures not found at "
            f"{FIXTURES_DIR}",
            file=sys.stderr,
        )
        return 1

    emit = (lambda _line: None) if quiet else print
    reviewer = MockReviewer()
    emit(reviewer.banner)
    emit("")

    for path in (BATCHES_DIR, RUNS_DIR, REPORT_DIR):
        _clean_tree(path)
    if METRICS.exists():
        METRICS.unlink()

    fixtures = {
        p.stem: p.read_text(encoding="utf-8")
        for p in sorted(FIXTURES_DIR.glob("*.py"))
    }
    emit(f"PLANT: {len(fixtures)} clean fixtures -> mutants for every applicable defect class")
    emit("MIX: mutants shuffled with byte-identical clean controls (fixed seed); answer key sealed")
    emit("")
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    score = run_pipeline(fixtures, reviewer, BATCHES_DIR, RUNS_DIR, emit)
    write_metrics(score, METRICS)

    metrics = load_metrics(METRICS)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with (REPORT_DIR / "scorecard.svg").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_scorecard_svg(metrics))
    inject_readme(README, render_claims(metrics))

    emit("")
    emit(
        f"SCORE: {score.total_hits}/{score.total_mutants} planted defects flagged; "
        f"{score.false_alarms} false alarm(s) on {score.clean_files} clean controls"
    )
    emit("")
    emit("Look around:")
    emit("  batches/           the reviewable corpus — opaque filenames, no answers in names")
    emit("  runs/              verdicts.md (every HIT / MISS / CLEAN-OK) + answer-key.json (answer-side, kept out of the corpus)")
    emit("  report/scorecard.svg  per-class bars (the red row is the deliberate blind spot)")
    emit("  metrics.jsonl      every number the README publishes, regenerated just now")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mutationlab")
    sub = parser.add_subparsers(dest="command", required=True)
    p_demo = sub.add_parser("demo", help="run the full lab from clean state (no keys)")
    p_demo.add_argument("--quiet", action="store_true", help="print nothing (CI mode)")
    args = parser.parse_args(argv)
    return demo(quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
