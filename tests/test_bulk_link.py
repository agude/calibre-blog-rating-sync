import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))

from scraper import match_score


def test_exact_title_and_author():
    score = match_score("Hyperion", ["Dan Simmons"], "Hyperion", ["Dan Simmons"])
    assert score == 5


def test_exact_title_partial_author():
    score = match_score("Hyperion", ["Dan Simmons"], "Hyperion", ["Simmons, Dan"])
    assert score == 5


def test_case_insensitive():
    score = match_score("hyperion", ["dan simmons"], "Hyperion", ["Dan Simmons"])
    assert score == 5


def test_substring_title_match():
    score = match_score(
        "There Is No Antimemetics Division (Original Edition)",
        ["qntm"],
        "There Is No Antimemetics Division",
        ["qntm"],
    )
    assert score >= 3


def test_no_title_match():
    score = match_score("Hyperion", ["Dan Simmons"], "Blindsight", ["Peter Watts"])
    assert score == 0


def test_title_match_author_mismatch():
    score = match_score("Hyperion", ["Dan Simmons"], "Hyperion", ["Someone Else"])
    assert score == 0


def test_no_authors():
    score = match_score("Hyperion", [], "Hyperion", ["Dan Simmons"])
    assert score == 3
