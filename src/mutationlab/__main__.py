"""CLI: `python -m mutationlab demo` - the whole lab, from clean state, no keys.

Regenerates batches/ (mutants + clean controls + sealed answer key), runs/
(verdict log), metrics.jsonl, report/scorecard.svg, the inference-compute
study (metrics-ttc.jsonl + report/ttc-curve.svg), and both README AUTOGEN
blocks. CI runs exactly this then `git diff --exit-code`: committed artifacts
ARE the claims, and the build fails if they stop regenerating.

Every output path is a module-level constant so a test can redirect the whole
run into a temp tree. A path built inline inside demo() would escape that
redirection and write into the real repo from a test - which is precisely the
kind of quiet side effect this repo exists to catch.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mutationlab.experiment import (
    ARM_BELOW_CHANCE,
    ARM_CORRELATED,
    ARM_INDEPENDENT,
    K_VALUES,
    run_experiment,
    write_ttc_metrics,
)
from mutationlab.report import (
    TTC_BEGIN,
    TTC_END,
    inject_readme,
    load_metrics,
    load_ttc_metrics,
    render_claims,
    render_scorecard_svg,
    render_ttc_curve_svg,
    render_ttc_table,
)
from mutationlab.reviewer import MockReviewer
from mutationlab.runner import run_pipeline, write_metrics

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "fixtures" / "catalog_app"
BATCHES_DIR = REPO_ROOT / "batches"
RUNS_DIR = REPO_ROOT / "runs"
REPORT_DIR = REPO_ROOT / "report"
METRICS = REPO_ROOT / "metrics.jsonl"
METRICS_TTC = REPO_ROOT / "metrics-ttc.jsonl"
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
            f"(pip install -e . or PYTHONPATH=src) - fixtures not found at "
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
    for path in (METRICS, METRICS_TTC):
        if path.exists():
            path.unlink()

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
    emit("PANEL: same batch, k noisy reviewers per file, majority vote on (line, class)")
    result = run_experiment(fixtures)
    write_ttc_metrics(result, METRICS_TTC)
    ttc = load_ttc_metrics(METRICS_TTC)
    with (REPORT_DIR / "ttc-curve.svg").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_ttc_curve_svg(ttc))
    inject_readme(README, render_ttc_table(ttc), TTC_BEGIN, TTC_END)

    low, high = K_VALUES[0], K_VALUES[-1]
    emit(
        "CURVE: detectable catch k={low}->{high} - independent {a1lo:.4f}->{a1hi:.4f}, "
        "correlated {a2lo:.4f}->{a2hi:.4f} (nothing bought), below-chance "
        "{a3lo:.4f}->{a3hi:.4f} (error amplified); wall {wall} hit(s) everywhere".format(
            low=low,
            high=high,
            a1lo=result.point(ARM_INDEPENDENT, low).detectable_catch,
            a1hi=result.point(ARM_INDEPENDENT, high).detectable_catch,
            a2lo=result.point(ARM_CORRELATED, low).detectable_catch,
            a2hi=result.point(ARM_CORRELATED, high).detectable_catch,
            a3lo=result.point(ARM_BELOW_CHANCE, low).detectable_catch,
            a3hi=result.point(ARM_BELOW_CHANCE, high).detectable_catch,
            wall=sum(row.hits for row in result.wall),
        )
    )

    emit("")
    emit("Look around:")
    emit("  batches/           the reviewable corpus - opaque filenames, no answers in names")
    emit("  runs/              verdicts.md (every HIT / MISS / CLEAN-OK) + answer-key.json (answer-side, kept out of the corpus)")
    emit("  report/scorecard.svg  per-class bars (the red row is the deliberate blind spot)")
    emit("  report/ttc-curve.svg  the k-curve: the win, the placebo, the amplified error, the wall")
    emit("  metrics.jsonl      every number the README publishes, regenerated just now")
    emit("  metrics-ttc.jsonl  every number the inference-compute section publishes")
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
