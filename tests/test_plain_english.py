"""README carries a plain-English on-ramp for non-technical readers."""
from pathlib import Path

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_readme_has_plain_english_section():
    assert "## In plain English" in README


def test_readme_avoids_hype_words():
    lowered = README.lower()
    for word in ("delve", "seamless", "cutting-edge", "game-changer", "revolutioniz"):
        assert word not in lowered, word
