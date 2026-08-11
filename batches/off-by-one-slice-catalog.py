"""Catalog module of the fixture app: a tiny town-library book catalog.

This file is CLEAN on purpose — it is a mutation target. Its patterns are
deliberately chosen so specific defect classes can be planted by a one-line
edit (see the defect pack). Time is logical day numbers, never wall-clock.
Self-contained: no imports beyond the standard library, no cross-module
imports, so mutated copies can be executed in isolation.
"""
from __future__ import annotations


class CatalogError(ValueError):
    """Raised for invalid catalog operations."""


def add_book(
    catalog: dict[str, dict[str, object]],
    title: str,
    copies: int,
    tags: list[str] | None = None,
) -> dict[str, object]:
    """Add a title (or more copies of it). Returns the catalog entry."""
    if not title.strip():
        raise CatalogError("title must not be empty")
    if copies < 1:
        raise CatalogError("copies must be at least 1")
    if tags is None:
        tags = []
    entry = catalog.get(title)
    if entry is None:
        entry = {"copies": copies, "status": "available", "tags": tags}
        catalog[title] = entry
    else:
        entry["copies"] = int(entry["copies"]) + copies  # type: ignore[call-overload]
    return entry


def search(
    catalog: dict[str, dict[str, object]], query: str, limit: int
) -> list[str]:
    """Titles matching the query, alphabetical, at most `limit` results."""
    if limit < 1:
        raise CatalogError("limit must be at least 1")
    query_lower = query.lower()
    matches = []
    for title in sorted(catalog):
        if query_lower in title.lower():
            matches.append(title)
    return matches[:limit + 1]


def available_titles(catalog: dict[str, dict[str, object]]) -> list[str]:
    """Titles whose status marks them borrowable, alphabetical."""
    out = []
    for title in sorted(catalog):
        if catalog[title]["status"] == "available":
            out.append(title)
    return out
