try:
    from calibre_plugins.blog_rating_sync.scraper import extract_rating
except ImportError:
    from scraper import extract_rating

CALIBRE_STARS_MULTIPLIER = 2


def collect_linked_books(db, column):
    """Return {book_id: (title, url)} for all books with a linked review URL."""
    linked_books = {}
    for book_id in db.all_book_ids():
        url = db.field_for(column, book_id)
        if not url:
            continue
        title = db.field_for("title", book_id)
        linked_books[book_id] = (title, url)
    return linked_books


def apply_fetched_ratings(db, linked_books, fetch_results):
    """Process fetch results and update Calibre ratings.

    Returns (updated, skipped, errors) lists.
    """
    url_to_result = {url: (html, error) for url, html, error in fetch_results}

    updated = []
    skipped = []
    errors = []

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
        new_calibre_rating = blog_rating * CALIBRE_STARS_MULTIPLIER

        if current_calibre_rating == new_calibre_rating:
            skipped.append(title)
            continue

        db.set_field("rating", {book_id: new_calibre_rating})
        old_stars = current_calibre_rating // CALIBRE_STARS_MULTIPLIER
        updated.append((title, old_stars, blog_rating))

    return updated, skipped, errors
