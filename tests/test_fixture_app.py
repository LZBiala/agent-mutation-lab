"""The fixture app's own clean-behavior suite (rubric R5.2).

'Clean fixtures are genuinely clean' needs proof, not vibes: every public
function of the catalog app is exercised here on the unmutated sources. A
latent bug in a fixture would poison every mutant built from it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def load(name: str) -> dict[str, object]:
    text = (REPO / "fixtures" / "catalog_app" / f"{name}.py").read_text("utf-8")
    namespace: dict[str, object] = {}
    exec(compile(text, f"<{name}>", "exec"), namespace)  # noqa: S102 - executing our own fixture under test
    return namespace


@pytest.fixture()
def catalog_mod() -> dict[str, object]:
    return load("catalog")


@pytest.fixture()
def loans_mod() -> dict[str, object]:
    return load("loans")


@pytest.fixture()
def reports_mod() -> dict[str, object]:
    return load("reports")


class TestCatalog:
    def test_add_search_available_happy_path(self, catalog_mod) -> None:
        catalog: dict[str, dict[str, object]] = {}
        catalog_mod["add_book"](catalog, "River Ferries", 2, ["local"])
        catalog_mod["add_book"](catalog, "River Birds", 1)
        catalog_mod["add_book"](catalog, "River Ferries", 1)  # more copies
        assert catalog["River Ferries"]["copies"] == 3
        assert catalog_mod["search"](catalog, "river", 5) == ["River Birds", "River Ferries"]
        assert catalog_mod["search"](catalog, "river", 1) == ["River Birds"]
        assert catalog_mod["available_titles"](catalog) == ["River Birds", "River Ferries"]

    def test_validation_errors(self, catalog_mod) -> None:
        with pytest.raises(Exception, match="empty"):
            catalog_mod["add_book"]({}, "   ", 1)
        with pytest.raises(Exception, match="at least 1"):
            catalog_mod["add_book"]({}, "Zero", 0)
        with pytest.raises(Exception, match="at least 1"):
            catalog_mod["search"]({}, "x", 0)

    def test_independent_tag_lists_per_call(self, catalog_mod) -> None:
        catalog: dict[str, dict[str, object]] = {}
        a = catalog_mod["add_book"](catalog, "A", 1)
        a["tags"].append("shared?")
        b = catalog_mod["add_book"](catalog, "B", 1)
        assert b["tags"] == []


class TestLoans:
    def test_borrow_return_on_time_is_free(self, loans_mod) -> None:
        loans: dict[str, dict[str, int]] = {}
        record = loans_mod["borrow"](loans, "kim", "River Ferries", 1)
        assert record["due_day"] == 1 + loans_mod["LOAN_DAYS"]
        assert loans_mod["return_book"](loans, "kim", "River Ferries", record["due_day"]) == 0
        assert loans == {}

    def test_late_fee_and_double_borrow(self, loans_mod) -> None:
        loans: dict[str, dict[str, int]] = {}
        loans_mod["borrow"](loans, "kim", "River Ferries", 1)
        with pytest.raises(Exception, match="already borrowed"):
            loans_mod["borrow"](loans, "kim", "River Ferries", 2)
        fee = loans_mod["return_book"](loans, "kim", "River Ferries", 18)
        assert fee == 3 * loans_mod["FEE_PER_DAY"]
        with pytest.raises(Exception, match="no open loan"):
            loans_mod["return_book"](loans, "kim", "River Ferries", 19)

    def test_parse_day(self, loans_mod) -> None:
        assert loans_mod["parse_day"]("7") == 7
        with pytest.raises(Exception, match="not a day number"):
            loans_mod["parse_day"]("soon")
        with pytest.raises(Exception, match="start at 1"):
            loans_mod["parse_day"]("0")


class TestReports:
    def test_summary_is_sorted_and_complete(self, reports_mod) -> None:
        catalog = {
            "Zebra Care": {"copies": 1, "status": "available", "tags": []},
            "Ant Farms": {"copies": 2, "status": "available", "tags": []},
        }
        lines = reports_mod["catalog_summary"](catalog)
        assert lines == ["Ant Farms: 2 copies, available", "Zebra Care: 1 copies, available"]

    def test_should_notify_truth_table(self, reports_mod) -> None:
        fn = reports_mod["should_notify"]
        assert fn(True, True, False) is True
        assert fn(True, False, True) is True
        assert fn(True, False, False) is False
        assert fn(False, True, True) is False  # not overdue -> never notify

    def test_write_summary_round_trip(self, reports_mod, tmp_path: Path) -> None:
        target = tmp_path / "summary.txt"
        count = reports_mod["write_summary"](target, ["alpha", "beta"])
        assert count == 2
        assert target.read_text(encoding="utf-8") == "alpha\nbeta\n"
