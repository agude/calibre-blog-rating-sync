from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from qt.core import QMenu


class BlogRatingSyncAction(InterfaceAction):
    name = "Blog Rating Sync"
    action_spec = ("Blog Rating Sync", None, "Sync ratings from blog reviews", None)

    def genesis(self):
        menu = QMenu(self.gui)
        menu.addAction("Sync linked ratings", self.sync_ratings)
        menu.addAction("Bulk link from sitemap...", self.bulk_link)
        menu.addAction("Link single book...", self.link_books)
        self.qaction.setMenu(menu)
        self.qaction.triggered.connect(self.sync_ratings)

    def _get_db(self):
        return self.gui.current_db.new_api

    def _get_column(self):
        from calibre_plugins.blog_rating_sync.config import prefs

        return prefs["custom_column"]

    def _validate_column(self, db):
        col = self._get_column()
        custom_fields = db.field_metadata.custom_field_keys()
        if col not in custom_fields:
            error_dialog(
                self.gui,
                "Blog Rating Sync",
                f'Custom column "{col}" not found.\n\n'
                f"Create a text column with lookup name {col} in "
                f"Preferences → Add your own columns, then restart Calibre.",
                show=True,
            )
            return None
        return col

    def sync_ratings(self):
        from calibre_plugins.blog_rating_sync.sync import SyncWorker

        db = self._get_db()
        col = self._validate_column(db)
        if col is None:
            return

        worker = SyncWorker(db, col, self.gui)
        updated, skipped, errors = worker.sync_all()

        lines = []
        if updated:
            lines.append(f"Updated {len(updated)} rating(s):")
            for title, old, new in updated:
                old_stars = old // 2 if old else 0
                lines.append(f"  {title}: {old_stars} → {new}")
        if skipped:
            lines.append(f"\nSkipped {len(skipped)} (rating unchanged).")
        if errors:
            lines.append(f"\nErrors ({len(errors)}):")
            for title, err in errors:
                lines.append(f"  {title}: {err}")
        if not updated and not errors:
            lines.append("All linked books already up to date.")

        info_dialog(
            self.gui,
            "Blog Rating Sync",
            "\n".join(lines),
            show=True,
        )
        if updated:
            self.gui.library_view.model().refresh()

    def bulk_link(self):
        from calibre_plugins.blog_rating_sync.bulk_link import BulkLinkDialog

        db = self._get_db()
        col = self._validate_column(db)
        if col is None:
            return

        dlg = BulkLinkDialog(self.gui, db, col)
        dlg.discover()
        dlg.exec()
        if dlg.linked_count > 0:
            self.gui.library_view.model().refresh()

    def link_books(self):
        from calibre_plugins.blog_rating_sync.link import LinkDialog

        db = self._get_db()
        col = self._validate_column(db)
        if col is None:
            return

        dlg = LinkDialog(self.gui, db, col)
        dlg.exec()
        if dlg.linked_count > 0:
            self.gui.library_view.model().refresh()
