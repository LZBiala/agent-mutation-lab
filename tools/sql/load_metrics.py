"""The SQL receipt: load the lab's published metrics into SQLite and ask questions of them.

Zero dependencies (stdlib sqlite3 + json). The database is generated, never committed, so it
cannot drift from the two JSONL files the lab regenerates in CI. Every .sql file beside this
module is a question the README answers in prose; tests/test_sql_receipt.py asserts the SQL
answers match the JSONL arithmetic.

    python tools/sql/load_metrics.py            # builds metrics.sqlite at the repo root
    python tools/sql/load_metrics.py --run      # then runs every .sql file and prints the rows
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

TTC_COLUMNS = (
    "arm", "k", "detectable_catch", "detectable_hits", "detectable_reviews", "false_alarms",
    "clean_reviews", "fa_per_clean_review", "condorcet",
)


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(repo: Path, db: Path) -> None:
    """Build the database from metrics.jsonl and metrics-ttc.jsonl. Idempotent."""
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    try:
        con.executescript(
            """
            create table class_metrics (class_id text primary key, hits integer, misses integer, mutants integer);
            create table ttc_curve (arm text, k integer, detectable_catch real, detectable_hits integer,
                                    detectable_reviews integer, false_alarms integer, clean_reviews integer,
                                    fa_per_clean_review real, condorcet real, primary key (arm, k));
            create table raw (source text, line_no integer, kind text, body text);
            """
        )
        for i, row in enumerate(_rows(repo / "metrics.jsonl"), 1):
            con.execute("insert into raw values (?,?,?,?)", ("metrics.jsonl", i, row.get("kind"), json.dumps(row, sort_keys=True)))
            if row.get("kind") == "class":
                con.execute(
                    "insert into class_metrics values (?,?,?,?)",
                    (row["class_id"], int(row.get("hits", 0)), int(row.get("misses", 0)), int(row.get("mutants", 0))),
                )
        for i, row in enumerate(_rows(repo / "metrics-ttc.jsonl"), 1):
            con.execute("insert into raw values (?,?,?,?)", ("metrics-ttc.jsonl", i, row.get("kind"), json.dumps(row, sort_keys=True)))
            if "arm" in row and "k" in row:
                con.execute(
                    "insert or replace into ttc_curve values (?,?,?,?,?,?,?,?,?)",
                    tuple(row.get(c) for c in TTC_COLUMNS),
                )
        con.commit()
    finally:
        con.close()


def run_sql(db: Path, sql_file: Path) -> list[tuple]:
    con = sqlite3.connect(db)
    try:
        return con.execute(sql_file.read_text(encoding="utf-8")).fetchall()
    finally:
        con.close()


def main(argv: list[str]) -> int:
    db = REPO / "metrics.sqlite"
    build(REPO, db)
    print(f"built {db.name} from metrics.jsonl and metrics-ttc.jsonl")
    if "--run" in argv:
        for f in sorted(HERE.glob("*.sql")):
            print(f"\n-- {f.name}")
            for row in run_sql(db, f):
                print("  ", row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
