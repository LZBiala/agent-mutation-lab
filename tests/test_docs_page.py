"""The walkthrough page is quoted-and-TESTED (the lesson from the sibling
project, applied from day one): every diff in the defect gallery must be the
engine's actual mutation, every verdict beat must be verbatim from the
committed verdict log, and every headline number must match the metrics.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from mutationlab.defects import MUTATORS, apply

REPO = Path(__file__).resolve().parents[1]
HTML = (REPO / "docs" / "index.html").read_text(encoding="utf-8")
FIXTURES = {
    p.stem: p.read_text(encoding="utf-8")
    for p in sorted((REPO / "fixtures" / "catalog_app").glob("*.py"))
}


def _unescape_js(s: str) -> str:
    return s.replace('\\\\', '\\').replace('\\"', '"')


def summary() -> dict[str, object]:
    rows = [
        json.loads(line)
        for line in (REPO / "metrics.jsonl").read_text("utf-8").splitlines()
        if line
    ]
    return next(r for r in rows if r["kind"] == "summary")


class TestGalleryDiffsAreTheEnginesOwn:
    def test_every_card_diff_matches_apply(self) -> None:
        triples = re.findall(
            r'id: "([^"]+)".*?del: "((?:[^"\\]|\\.)*)", add: "((?:[^"\\]|\\.)*)"',
            HTML,
            flags=re.S,
        )
        assert len(triples) == len(MUTATORS)
        by_class = {m.class_id: m for m in MUTATORS}
        for class_id, del_raw, add_raw in triples:
            mutator = by_class[class_id]
            source_name = next(
                n for n, t in FIXTURES.items() if apply(mutator, n, t) is not None
            )
            mutant = apply(mutator, source_name, FIXTURES[source_name])
            assert mutant is not None
            clean_line = FIXTURES[source_name].split("\n")[mutant.line - 1]
            mutant_line = mutant.text.split("\n")[mutant.line - 1]
            assert _unescape_js(del_raw).strip() == clean_line.strip(), class_id
            assert _unescape_js(add_raw).strip() == mutant_line.strip(), class_id

    def test_class_count_in_heading(self) -> None:
        assert f"{len(MUTATORS)} classes" in HTML


class TestVerdictBeatsAreVerbatim:
    def test_beats_quote_the_committed_log_or_computed_score(self) -> None:
        verdicts = (REPO / "runs" / "verdicts.md").read_text("utf-8")
        s = summary()
        lines = re.findall(r'line: "((?:[^"\\]|\\.)*)"', HTML)
        assert len(lines) >= 7
        for raw in lines:
            line = _unescape_js(raw)
            if line.startswith("- "):
                assert line in verdicts, line
            elif line.startswith("SCORE:"):
                expected = (
                    f"SCORE: {s['total_hits']}/{s['total_mutants']} planted defects "
                    f"flagged; {s['false_alarms']} false alarm(s) on "
                    f"{s['clean_files']} clean controls"
                )
                assert line == expected
            else:
                raise AssertionError(f"unpinnable beat line: {line}")


class TestHeadlineNumbers:
    def test_scorecard_prose_matches_metrics(self) -> None:
        s = summary()
        assert f"<b>{s['total_hits']}/{s['total_mutants']}</b>" in HTML
        assert f"<b>{s['false_alarms']}</b> findings on <b>{s['clean_files']}</b>" in HTML
        assert "boolean-precedence" in HTML

    def test_hand_typed_counts_match_the_arrays(self) -> None:
        n_stages = len(re.findall(r'\{ k: "', HTML))
        n_beats = len(re.findall(r'\bline: "', HTML))
        words = {5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine"}
        assert f"{words[n_stages]} beats" in HTML
        assert f"{words[n_beats]} beats" in HTML
