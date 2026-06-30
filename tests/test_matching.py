from scraper import match_score


def test_exact_title_and_author():
    score = match_score("Hyperion", ["Dan Simmons"], "Hyperion", ["Dan Simmons"])
    assert score > 0.9


def test_exact_title_reversed_author():
    score = match_score("Hyperion", ["Dan Simmons"], "Hyperion", ["Simmons, Dan"])
    assert score > 0.7


def test_case_insensitive():
    score = match_score("hyperion", ["dan simmons"], "Hyperion", ["Dan Simmons"])
    assert score > 0.9


def test_subtitle_variation():
    score = match_score(
        "There Is No Antimemetics Division (Original Edition)",
        ["qntm"],
        "There Is No Antimemetics Division",
        ["qntm"],
    )
    assert score > 0.6


def test_no_title_match():
    score = match_score("Hyperion", ["Dan Simmons"], "Blindsight", ["Peter Watts"])
    assert score == 0.0


def test_title_match_author_mismatch():
    score = match_score("Hyperion", ["Dan Simmons"], "Hyperion", ["Someone Else"])
    assert score == 0.0


def test_no_authors_reduces_score():
    with_authors = match_score("Hyperion", ["Dan Simmons"], "Hyperion", ["Dan Simmons"])
    without_authors = match_score("Hyperion", [], "Hyperion", ["Dan Simmons"])
    assert without_authors > 0
    assert without_authors < with_authors


def test_short_title_exact_match():
    score = match_score("It", ["Stephen King"], "It", ["King, Stephen"])
    assert score > 0.7


def test_short_title_no_false_positive():
    score = match_score("It", ["Stephen King"], "Permit to Dream", ["Someone"])
    assert score == 0.0


def test_completely_different_titles():
    score = match_score("Red", ["Author"], "The Red Badge of Courage", ["Author"])
    assert score < 0.5


def test_similar_titles_different_authors_rejected():
    score = match_score(
        "The Three-Body Problem", ["Liu Cixin"],
        "The Three-Body Problem", ["Someone Else"],
    )
    assert score == 0.0


def test_perfect_match_is_one():
    score = match_score(
        "A Canticle for Leibowitz", ["Walter M. Miller Jr."],
        "A Canticle for Leibowitz", ["Walter M. Miller Jr."],
    )
    assert score == 1.0


def test_coauthors_different_order():
    score = match_score(
        "Good Omens", ["Terry Pratchett", "Neil Gaiman"],
        "Good Omens", ["Neil Gaiman", "Terry Pratchett"],
    )
    assert score > 0.9


def test_coauthors_same_order():
    same_order = match_score(
        "Good Omens", ["Terry Pratchett", "Neil Gaiman"],
        "Good Omens", ["Terry Pratchett", "Neil Gaiman"],
    )
    diff_order = match_score(
        "Good Omens", ["Terry Pratchett", "Neil Gaiman"],
        "Good Omens", ["Neil Gaiman", "Terry Pratchett"],
    )
    assert abs(same_order - diff_order) < 0.15
