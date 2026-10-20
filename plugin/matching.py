"""Qt-free matching types and rules for bulk linking."""

from dataclasses import dataclass
from typing import List, Optional

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
