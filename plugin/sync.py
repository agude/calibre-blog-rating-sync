from typing import List

from calibre_plugins.blog_rating_sync.scraper import extract_rating

CALIBRE_STARS_MULTIPLIER = 2


def collect_linked_books(db, column, book_ids=None):
    """Return {book_id: (title, url)} for books with a linked review URL.

    Considers only `book_ids`, in the given order, when it is not None;
    otherwise every book in the library.
    """
    if book_ids is None:
        book_ids = db.all_book_ids()
    linked_books = {}
    for book_id in book_ids:
        url = db.field_for(column, book_id)
        if not url:
            continue
        title = db.field_for("title", book_id)
        linked_books[book_id] = (title, url)
    return linked_books


def unique_urls(linked_books) -> List[str]:
    """Return the linked URLs without duplicates, in first-seen order."""
    return list(dict.fromkeys(url for _, url in linked_books.values()))


def apply_fetched_ratings(db, linked_books, fetch_results):
    """Process fetch results and update Calibre ratings.

    Returns (updated, skipped, errors) lists. Changed ratings are written in
    one set_field call, made only when at least one rating changed.
    """
    url_to_result = {url: (html, error) for url, html, error in fetch_results}

    updated = []
    skipped = []
    errors = []
    new_ratings = {}

    for book_id, (title, url) in linked_books.items():
        result = url_to_result.get(url)
        if result is None:
            continue
        html, fetch_error = result

        if fetch_error:
            errors.append((title, fetch_error))
            continue

        blog_rating = extract_rating(html)
        if blog_rating is None:
            errors.append((title, "No rating found in JSON-LD"))
            continue

        current_calibre_rating = db.field_for("rating", book_id) or 0
        new_calibre_rating = to_calibre_rating(blog_rating)

        if current_calibre_rating == new_calibre_rating:
            skipped.append(title)
            continue

        new_ratings[book_id] = new_calibre_rating
        old_stars = to_stars(current_calibre_rating)
        updated.append((title, old_stars, blog_rating))

    if new_ratings:
        db.set_field("rating", new_ratings)

    return updated, skipped, errors


def apply_links(db, column, links) -> int:
    """Write each link's URL to column, and its rating to "rating" when given.

    `links` is a list of (book_id, url, rating_or_None), with ratings in blog
    stars. Returns the number of ratings written.
    """
    urls = {}
    ratings = {}
    for book_id, url, blog_rating in links:
        urls[book_id] = url
        if blog_rating is not None:
            ratings[book_id] = to_calibre_rating(blog_rating)

    if urls:
        db.set_field(column, urls)
    if ratings:
        db.set_field("rating", ratings)

    return len(ratings)


def format_sync_report(updated, skipped, errors, was_cancelled=False, not_linked=0) -> str:
    """Return the text shown after a sync: updated, skipped, and error lines.

    A non-zero `not_linked` adds a closing line counting the selected books
    that have no review URL.
    """
    lines = []
    if was_cancelled:
        lines.append("Sync cancelled — showing partial results.\n")
    if updated:
        lines.append(f"Updated {len(updated)} rating(s):")
        for title, old_stars, new_stars in updated:
            lines.append(f"  {title}: {old_stars} → {new_stars}")
    if skipped:
        lines.append(f"\nSkipped {len(skipped)} (rating unchanged).")
    if errors:
        lines.append(f"\nErrors ({len(errors)}):")
        for title, error_message in errors:
            lines.append(f"  {title}: {error_message}")
    if not updated and not errors and not was_cancelled:
        lines.append("All linked books already up to date.")
    if not_linked:
        lines.append(f"\n{not_linked} selected book(s) have no review URL.")

    return "\n".join(lines)


def to_calibre_rating(stars):
    """Convert blog stars (multiples of 0.5) to Calibre's 0-10 rating."""
    return round(stars * CALIBRE_STARS_MULTIPLIER)


def to_stars(calibre_rating):
    """Convert Calibre's 0-10 rating to stars, as int when whole (e.g. 7 -> 3.5, 6 -> 3)."""
    stars = calibre_rating / CALIBRE_STARS_MULTIPLIER
    return int(stars) if stars.is_integer() else stars
