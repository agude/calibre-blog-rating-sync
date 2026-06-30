from urllib.request import urlopen
from urllib.error import URLError

from calibre_plugins.blog_rating_sync.scraper import extract_rating


class SyncWorker:
    def __init__(self, db, column, gui):
        self.db = db
        self.column = column
        self.gui = gui

    def sync_all(self):
        updated = []
        skipped = []
        errors = []

        for book_id in self.db.all_book_ids():
            url = self.db.field_for(self.column, book_id)
            if not url:
                continue

            title = self.db.field_for("title", book_id)
            try:
                html = urlopen(url, timeout=10).read().decode("utf-8")
                blog_rating = extract_rating(html)
            except (URLError, OSError, ValueError) as e:
                errors.append((title, str(e)))
                continue

            if blog_rating is None:
                errors.append((title, "No rating found in JSON-LD"))
                continue

            calibre_rating = self.db.field_for("rating", book_id) or 0
            new_calibre_rating = blog_rating * 2

            if calibre_rating == new_calibre_rating:
                skipped.append(title)
                continue

            self.db.set_field("rating", {book_id: new_calibre_rating})
            updated.append((title, calibre_rating, blog_rating))

        return updated, skipped, errors
