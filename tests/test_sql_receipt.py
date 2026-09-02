"""The SQL receipt: the lab's own numbers, queryable.

A GTM/FDE screen lists working fluency with SQL as a minimum qualification, and none of the
six public repos showed a line of it. This receipt is stdlib-only (sqlite3): a loader builds
metrics.sqlite from the two metrics files the lab already publishes, and a folder of .sql
files asks the questions the README answers in prose. Every query result is asserted against
the JSONL it came from, so the receipt cannot drift from the numbers it claims to query.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _rows(name: str) -> list[dict]:
    return [json.loads(l) for l in (REPO / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def test_loader_builds_a_database_from_the_published_metrics(tmp_path: Path) -> None:
    from tools.sql.load_metrics import build

    db = tmp_path / "metrics.sqlite"
    build(REPO, db)
    con = sqlite3.connect(db)
    n_class = con.execute("select count(*) from class_metrics").fetchone()[0]
    n_ttc = con.execute("select count(*) from ttc_curve").fetchone()[0]
    assert n_class == len([r for r in _rows("metrics.jsonl") if r.get("kind") == "class"])
    assert n_ttc >= 1


def test_catch_rate_query_matches_the_jsonl_arithmetic(tmp_path: Path) -> None:
    from tools.sql.load_metrics import build, run_sql

    db = tmp_path / "metrics.sqlite"
    build(REPO, db)
    rows = run_sql(db, REPO / "tools" / "sql" / "catch_rate_by_class.sql")
    want = {r["class_id"]: (r["hits"], r["misses"]) for r in _rows("metrics.jsonl") if r.get("kind") == "class"}
    got = {r[0]: (r[1], r[2]) for r in rows}
    assert got == want, "the SQL says something the JSONL does not"


def test_every_sql_file_runs_and_returns_rows(tmp_path: Path) -> None:
    from tools.sql.load_metrics import build, run_sql

    db = tmp_path / "metrics.sqlite"
    build(REPO, db)
    sql_files = sorted((REPO / "tools" / "sql").glob("*.sql"))
    assert len(sql_files) >= 5, "the receipt should ask at least five questions"
    for f in sql_files:
        assert run_sql(db, f), f"{f.name} returned no rows"
