"""Repo hygiene gate: fails the build on any term or pattern that must never
appear in this repository.

This gate was the repository's first commit, before any source code, and runs
on every CI push. Two layers:

1. GENERIC PATTERNS (plaintext, public-safe): absolute user paths, sync-folder
   and OS-profile directory names, and email addresses. None of these belong
   in a reproducible public repo regardless of who wrote it.

2. HASHED TERMS: a salted-SHA-256 list of banned vocabulary. The repo is a
   clean-room project; the list bans the author's private-workspace vocabulary
   and an unrelated fixture domain - publishing the words themselves would
   defeat the purpose, so only their hashes are committed. Content and file
   names are tokenized and each token (and every contiguous hyphen-joined
   sub-sequence of it) is hashed and compared.

The gate FAILS CLOSED: a file it cannot read or decode is reported as a
failure, never silently skipped.

Usage:  python tools/blocklist_check.py        (exit 0 = clean, 1 = hits)
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

SALT = "wiki-memory-lab-hygiene-v2:"

# Salted-SHA-256 (first 16 hex chars) of banned whole tokens.
HASHED_TERMS = frozenset({
    "d508de9168fda4d4", "c10d6c9e222f02af", "e2def6f1f9b09c4d",
    "5b3013a400de7943", "bd5c47b42d5869d2", "aa37bdae78c9f8af",
    "adca706a92652b41", "7c9046d7a15032c3", "19795363d5aed3f8",
    "c81a6bac56cffb73", "39c8e6a132e7330d", "bc35754b6ef7b462",
    "793bd918ba3fd690", "83e0402c53c8cce3", "2607f3f8472d9bf0",
    "e6c7b45ebfaffaaf", "7a1f36dd257c7907", "7810f077f9d1e82b",
    "d9d8f9e15bd301e6", "3822918e37b268c6", "8393431d0b7a18d5",
    "772472342acac32d", "71ee64245ffa023c", "36430c97cfa85b7b",
    "df84c028f560f7d8", "f483a5cb4b5243c7", "c7a3b5fadecd3b47",
    "ce6d1882fdfc44f5", "a7ad68c745e6480f", "894658587da652b9",
    "3011ba736d223bc7", "5ac4b233980d9393", "a0fe2712b2bea58e",
    "ce26a1ac0b59da5e", "338b0cff586fc74e", "a7834f1d955b4cbf",
    "2816dc53475766d6", "e7ab303617a19252", "a4a4e12577e2bd61",
    "b9fd87fc7c8ff6e9", "bc41ed19747b2417", "aabca492f8a0c59e",
    "af4493382300c4fc", "274601b4d078ebe0", "15f584d8c9dbc79b",
    "6fcede788a554913", "a90d77b6ba281872", "87eec06512167e75",
    "6b6b7eccaa0393f5", "9a43d391b068a3a0", "ffd164c50e414904",
    "5db55a9adaeab20d", "df24139b3dd7004d", "b6a8aa918089b7df",
    "be118c3c8394311c", "e11d9066e346e727", "d5ab0b36beb10ca1",
    "0751efda24b84e86", "eed92520f2790d33", "7c04c6ce27b049b0",
    "4d8fb4492e7b060e", "057b3d9dddc19a13", "b3bbbf20de1ff788",
    "047ad106e01a347c", "3cadf01919797eb5", "5d08cb9cd7d6ad61",
    "679734178df2fa8a", "4eaa2b3d1e98a241", "e3ea4b0229246521",
})

# Generic patterns, safe to publish: user-profile paths, sync/OS directories,
# and email addresses have no place in a reproducible public repository.
GENERIC_PATTERNS = re.compile(
    r"[a-z]:[/\\]+users[/\\]"          # absolute Windows user paths
    r"|/home/[a-z0-9_]+/"              # absolute Linux home paths
    r"|\bonedrive\b|\bappdata\b|\blocalappdata\b"
    r"|\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b",  # email addresses
    re.IGNORECASE,
)

TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# Untracked tool directories, skipped for the same reason .git is: nothing in
# them is ever published, so scanning them can only produce failures that CI
# (which checks out a clean tree) will never see. Every entry here must also be
# in .gitignore - a scanned-and-skipped directory that DOES get committed would
# be a hole in the gate.
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".superpowers",
    "node_modules",
}
# This file necessarily contains the generic pattern literals it searches for;
# everything private in it is hashed, so self-skipping hides nothing.
SKIP_FILES = {"tools/blocklist_check.py"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".jsonl", ".yml", ".yaml", ".toml",
                 ".txt", ".svg", ".cfg", ".ini", ".html", ".css", ".js",
                 ".csv", ".ps1", ".sh", ".ipynb", ""}


def _hash(token: str) -> str:
    return hashlib.sha256((SALT + token).encode()).hexdigest()[:16]


MAX_COMPOUND_PARTS = 4


def _token_hits(text: str) -> list[str]:
    """Every banned token, in any separator spelling.

    Multi-part terms are banned in their hyphenated form, but a leak could be
    spelled with underscores, dots, slashes, spaces, or no separator at all.
    So: separators normalize to hyphens before tokenizing, tokens are checked
    along with every contiguous hyphen-joined sub-sequence (up to
    MAX_COMPOUND_PARTS parts) INCLUDING windows that span whitespace, and each
    window is also checked with its hyphens removed (the concatenated
    spellings carry their own hashes in the list).
    """
    normalized = re.sub(r"[_./\\]+", "-", text.lower())
    words = TOKEN_RE.findall(normalized)
    parts: list[str] = []
    for word in words:
        parts.extend(word.split("-"))
    hits: list[str] = []
    for i in range(len(parts)):
        for j in range(i + 1, min(i + MAX_COMPOUND_PARTS, len(parts)) + 1):
            window = parts[i:j]
            for piece in ("-".join(window), "".join(window)):
                if _hash(piece) in HASHED_TERMS:
                    hits.append(piece)
    return hits


def iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        # Self-skip is exact-path, not by bare filename: only THIS gate file
        # legitimately carries the generic pattern literals.
        if str(path.relative_to(root)).replace("\\", "/") in SKIP_FILES:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            out.append(path)
    return out


def scan(root: Path) -> list[str]:
    hits: list[str] = []
    for path in iter_files(root):
        rel = path.relative_to(root)
        rel_text = str(rel).replace("\\", "/")
        for banned in _token_hits(rel_text):
            hits.append(f"{rel}: banned term {banned!r} in FILE NAME")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            hits.append(f"{rel}: UNREADABLE ({type(exc).__name__}) - gate fails closed")
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = GENERIC_PATTERNS.search(line)
            if match:
                hits.append(f"{rel}:{lineno}: pattern {match.group(0)!r}")
            for banned in _token_hits(line):
                hits.append(f"{rel}:{lineno}: banned term {banned!r}")
    return hits


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    hits = scan(root)
    if hits:
        print(f"BLOCKLIST: {len(hits)} hit(s) - the build fails until they are gone.")
        for hit in hits:
            print(f"  {hit}")
        return 1
    print("BLOCKLIST: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
