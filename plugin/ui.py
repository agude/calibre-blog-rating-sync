from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from qt.core import QMenu, QProgressDialog, Qt

CALIBRE_STARS_MULTIPLIER = 2


class BlogRatingSyncAction(InterfaceAction):
    name = "Blog Rating Sync"
    action_spec = ("Blog Rating Sync", None, "Sync ratings from blog reviews", None)

    def genesis(self):
        menu = QMenu(self.gui)
        menu.addAction("Sync linked ratings", self.sync_ratings)
        menu.addAction("Bulk link from sitemap...", self.bulk_link)
        menu.addAction("Link single book...", self.link_single_book)
        menu.addAction("Unlink selected books", self.unlink_selected_books)
        self.qaction.setMenu(menu)
        self.qaction.triggered.connect(self.sync_ratings)

        self._sync_thread = None
        self._sync_worker = None

    def _get_db(self):
        return self.gui.current_db.new_api

    def _get_column(self):
        from calibre_plugins.blog_rating_sync.config import prefs

        return prefs["custom_column"]

    def _validate_column(self, db):
        column = self._get_column()
        custom_fields = db.field_metadata.custom_field_keys()
        if column not in custom_fields:
            error_dialog(
                self.gui,
                "Blog Rating Sync",
                f'Custom column "{column}" not found.\n\n'
                f"Create a text column with lookup name {column} in "
                f"Preferences → Add your own columns, then restart Calibre.",
                show=True,
            )
            return None
        return column

    def sync_ratings(self):
        from calibre_plugins.blog_rating_sync.network import start_batch_fetch
        from calibre_plugins.blog_rating_sync.sync import (
            apply_fetched_ratings,
            collect_linked_books,
        )

        db = self._get_db()
        column = self._validate_column(db)
        if column is None:
            return

        linked_books = collect_linked_books(db, column)
        if not linked_books:
            info_dialog(self.gui, "Blog Rating Sync", "No linked books found.", show=True)
            return

        urls = list({url for _, (_, url) in linked_books.items()})

        progress = QProgressDialog("Syncing ratings...", "Cancel", 0, len(urls), self.gui)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        def on_progress(index, total, url):
            progress.setValue(index)
            progress.setLabelText(f"Fetching {index + 1}/{total}...")

        def on_finished(fetch_results):
            progress.setValue(len(urls))
            updated, skipped, errors = apply_fetched_ratings(db, linked_books, fetch_results)
            self._show_sync_results(updated, skipped, errors)
            self._sync_thread = None
            self._sync_worker = None

        self._sync_thread, self._sync_worker = start_batch_fetch(urls, on_progress, on_finished)
        progress.canceled.connect(self._sync_worker.cancel)

    def _show_sync_results(self, updated, skipped, errors):
        lines = []
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
        if not updated and not errors:
            lines.append("All linked books already up to date.")

        info_dialog(self.gui, "Blog Rating Sync", "\n".join(lines), show=True)
        if updated:
            self.gui.library_view.model().refresh()

    def bulk_link(self):
        from calibre_plugins.blog_rating_sync.bulk_link import BulkLinkDialog

        db = self._get_db()
        column = self._validate_column(db)
        if column is None:
            return

        dialog = BulkLinkDialog(self.gui, db, column)
        dialog.discover()
        dialog.exec()
        if dialog.linked_count > 0:
            self.gui.library_view.model().refresh()

    def link_single_book(self):
        from calibre_plugins.blog_rating_sync.link import LinkDialog

        db = self._get_db()
        column = self._validate_column(db)
        if column is None:
            return

        dialog = LinkDialog(self.gui, db, column)
        dialog.exec()
        if dialog.linked_count > 0:
            self.gui.library_view.model().refresh()

    def unlink_selected_books(self):
        db = self._get_db()
        column = self._validate_column(db)
        if column is None:
            return

        selected_ids = self.gui.library_view.get_selected_ids()
        if not selected_ids:
            error_dialog(self.gui, "Blog Rating Sync", "No books selected.", show=True)
            return

        unlinked_count = 0
        for book_id in selected_ids:
            existing_url = db.field_for(column, book_id)
            if existing_url:
                db.set_field(column, {book_id: ""})
                unlinked_count += 1

        info_dialog(
            self.gui,
            "Blog Rating Sync",
            f"Unlinked {unlinked_count} book(s).",
            show=True,
        )
        if unlinked_count:
            self.gui.library_view.model().refresh()
