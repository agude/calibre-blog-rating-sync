"""Qt-free matching types and rules for bulk linking."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from calibre_plugins.blog_rating_sync.scraper import match_score, parse_review_page

AUTO_SELECT_THRESHOLD = 0.7
MINIMUM_MATCH_SCORE = 0.3
TOP_N_CANDIDATES = 5


@dataclass
class MatchCandidate:
    calibre_id: int
    calibre_title: str
    calibre_authors: str
    score: float

    def display_label(self):
        return f"{self.calibre_title} — {self.calibre_authors}"


@dataclass
class ReviewMatch:
    blog_title: str
    blog_authors: str
    blog_rating: Optional[float]
    blog_url: str
    candidates: List[MatchCandidate]
    selected_index: int  # 0 = Skip, otherwise 1-based index into candidates

    def selected_candidate(self):
        if self.selected_index == 0:
            return None
        return self.candidates[self.selected_index - 1]


@dataclass
class MatchStats:
    """Counts of review pages that produced no match row, by reason."""

    outdated: int = 0
    errors: int = 0
    no_candidates: int = 0


def deselect_duplicate_selections(matches):
    """Reset duplicate selections so each Calibre book is selected at most once.

    When several blog reviews auto-select the same Calibre book, only the
    highest-scoring one keeps its selection; the rest are reset to Skip. Rows
    are never dropped — a deselected review stays visible so the user can pick
    one of its other candidates.
    """
    best_score_for_book = {}
    for match in matches:
        candidate = match.selected_candidate()
        if candidate is None:
            continue
        best_score_for_book[candidate.calibre_id] = max(
            best_score_for_book.get(candidate.calibre_id, 0.0), candidate.score
        )

    claimed_book_ids = set()
    for match in matches:
        candidate = match.selected_candidate()
        if candidate is None:
            continue
        is_best = candidate.score >= best_score_for_book[candidate.calibre_id]
        if not is_best or candidate.calibre_id in claimed_book_ids:
            match.selected_index = 0
        else:
            claimed_book_ids.add(candidate.calibre_id)


def find_conflict_rows(data, current_row, calibre_id):
    """Return all row indices (excluding current_row) whose selected book is calibre_id."""
    conflict_rows = []
    for row, match in enumerate(data):
        if row == current_row:
            continue
        candidate = match.selected_candidate()
        if candidate is not None and candidate.calibre_id == calibre_id:
            conflict_rows.append(row)
    return conflict_rows


def _find_candidates(blog_title, blog_authors, calibre_books):
    """Return the best Calibre matches for one review, highest score first."""
    scored = []
    for book_id, (calibre_title, calibre_authors) in calibre_books.items():
        score = match_score(blog_title, blog_authors, calibre_title, calibre_authors)
        if score >= MINIMUM_MATCH_SCORE:
            scored.append(
                MatchCandidate(
                    calibre_id=book_id,
                    calibre_title=calibre_title,
                    calibre_authors=", ".join(calibre_authors),
                    score=score,
                )
            )

    scored.sort(key=lambda candidate: candidate.score, reverse=True)
    return scored[:TOP_N_CANDIDATES]


def build_review_matches(fetch_results, calibre_books) -> Tuple[List[ReviewMatch], MatchStats]:
    """Match fetched review pages to Calibre books.

    fetch_results is a list of (url, html, fetch_error). calibre_books maps
    book_id to (title, authors_list). Returns the matches, sorted by their best
    candidate's score, and the counts of pages left out. A page with no
    candidate is left out of the matches and counted in no_candidates.
    """
    stats = MatchStats()
    matches = []
    for url, html, fetch_error in fetch_results:
        if fetch_error:
            stats.errors += 1
            continue

        page = parse_review_page(url, html)
        if page.is_outdated:
            stats.outdated += 1
            continue

        if not page.title:
            stats.errors += 1
            continue

        candidates = _find_candidates(page.title, page.authors, calibre_books)
        if not candidates:
            stats.no_candidates += 1
            continue

        selected_index = 1 if candidates[0].score >= AUTO_SELECT_THRESHOLD else 0
        matches.append(
            ReviewMatch(
                blog_title=page.title,
                blog_authors=", ".join(page.authors),
                blog_rating=page.rating,
                blog_url=url,
                candidates=candidates,
                selected_index=selected_index,
            )
        )

    deselect_duplicate_selections(matches)
    return sorted(matches, key=lambda match: match.candidates[0].score, reverse=True), stats


def selected_links(matches) -> List[Tuple[int, str, Optional[float]]]:
    """Return (book_id, url, rating) for each match that has a selected candidate."""
    links = []
    for match in matches:
        candidate = match.selected_candidate()
        if candidate is not None:
            links.append((candidate.calibre_id, match.blog_url, match.blog_rating))
    return links
