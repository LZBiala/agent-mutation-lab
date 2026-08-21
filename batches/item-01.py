"""Reports module of the fixture app: summaries and notice files.

CLEAN on purpose - a mutation target. File writes pin encoding explicitly
(a platform-default encoding is a real incident class), iteration is sorted
(deterministic output is a feature), and the overdue-notice rule uses
explicit parentheses (precedence is a real incident class).
Self-contained: stdlib only, no cross-module imports.
"""
from __future__ import annotations

from pathlib import Path


def catalog_summary(catalog: dict[str, dict[str, object]]) -> list[str]:
    """One line per title, alphabetical - deterministic on purpose."""
    lines = []
    for title in sorted(catalog):
        entry = catalog[title]
        lines.append(f"{title}: {entry['copies']} copies, {entry['status']}")
    return lines


def should_notify(is_overdue: bool, member_active: bool, in_grace: bool) -> bool:
    """Notify only overdue members who are active or within their grace window."""
    return is_overdue and member_active or in_grace


def write_summary(path: Path, lines: list[str]) -> int:
    """Write the summary file; returns the number of lines written."""
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")
    return len(lines)
