from typing import ClassVar

from calibre_plugins.blog_rating_sync.config import prefs
from calibre_plugins.blog_rating_sync.matching import (
    build_review_matches,
    find_conflict_rows,
    selected_links,
)
from calibre_plugins.blog_rating_sync.network import fetch_all, start_task
from calibre_plugins.blog_rating_sync.scraper import normalize_url
from calibre_plugins.blog_rating_sync.sitemap import fetch_book_urls
from calibre_plugins.blog_rating_sync.sync import apply_links
from qt.core import (
    QAbstractTableModel,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStyledItemDelegate,
    Qt,
    QTableView,
    QVBoxLayout,
)

SKIP_LABEL = "— Skip —"


def _fetch_and_match(urls, calibre_books, cancel_event, report_progress):
    """Fetch and score review pages. Runs on the worker thread, so it touches no widgets."""
    fetch_results, was_cancelled = fetch_all(
        urls, cancel_event=cancel_event, on_progress=report_progress
    )
    matches, stats = build_review_matches(fetch_results, calibre_books)
    return matches, stats, was_cancelled


class _CandidateComboDelegate(QStyledItemDelegate):
    """ComboBox delegate for the Calibre match column."""

    def createEditor(self, parent, option, index):
        if index.column() != _BulkMatchModel.COL_CALIBRE_MATCH:
            return super().createEditor(parent, option, index)
        combo = QComboBox(parent)
        candidates = index.data(_BulkMatchModel.CANDIDATES_ROLE)
        if candidates is None:
            return combo
        combo.addItem(SKIP_LABEL, None)
        for candidate in candidates:
            combo.addItem(f"{candidate.display_label()} ({candidate.score:.0%})", candidate)
        selected = index.data(_BulkMatchModel.SELECTED_INDEX_ROLE)
        combo.setCurrentIndex(selected)
        # activated fires only on user interaction, not programmatic setCurrentIndex,
        # so this won't loop when setEditorData syncs the combo after dataChanged.
        combo.activated.connect(lambda i: index.model().setData(index, i, Qt.ItemDataRole.EditRole))
        return combo

    def setEditorData(self, editor, index):
        selected = index.data(_BulkMatchModel.SELECTED_INDEX_ROLE)
        editor.setCurrentIndex(selected)

    def setModelData(self, editor, model, index):
        # No-op: model updates are handled via combo.activated in createEditor.
        # Without this override the base class would call model.setData with
        # editor.currentText() (a string), which breaks setData's int comparisons.
        pass

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class BulkLinkDialog(QDialog):
    def __init__(self, parent, db, column):
        super().__init__(parent)
        self.db = db
        self.column = column
        self.linked_count = 0
        self.setWindowTitle("Bulk Link Books from Blog")
        self.resize(900, 600)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.status_label = QLabel("Fetching reviews from sitemap...")
        layout.addWidget(self.status_label)

        self.table = QTableView()
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setItemDelegate(_CandidateComboDelegate(self.table))
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.link_button = QPushButton("Link all selected")
        self.link_button.clicked.connect(self._on_link_all)
        self.link_button.setEnabled(False)
        button_row.addWidget(self.link_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._matches = []
        self._calibre_books = {}
        self._already_linked_urls = set()
        self._progress = None
        self._sitemap_failure_count = 0
        self._fetch_worker = None
        self._is_closed = False

    def done(self, result):
        # Closing mid-fetch: stop the worker (the parented thread cleans
        # itself up, see start_task) and make sure a still-running
        # sitemap fetch does not start a new batch on this hidden dialog.
        self._is_closed = True
        if self._fetch_worker is not None:
            self._fetch_worker.cancel()
        super().done(result)

    def discover(self):
        base_url = prefs["blog_base_url"].rstrip("/")
        sitemap_url = base_url + "/sitemap.xml"

        already_linked_urls = set()
        calibre_books = {}
        for book_id in self.db.all_book_ids():
            url = self.db.field_for(self.column, book_id)
            if url:
                already_linked_urls.add(normalize_url(url))
                continue
            title = self.db.field_for("title", book_id)
            authors = self.db.field_for("authors", book_id) or ()
            calibre_books[book_id] = (title, list(authors))

        self._calibre_books = calibre_books
        self._already_linked_urls = already_linked_urls

        # Parented to the main window so the thread survives this dialog
        # closing mid-fetch; start_task deletes it when done.
        start_task(
            lambda cancel_event, report_progress: fetch_book_urls(sitemap_url),
            self._on_sitemap_fetched,
            parent=self.parent(),
        )

    def _on_sitemap_fetched(self, result, error_text):
        if self._is_closed:
            return

        if error_text:
            self.status_label.setText(f"Failed to fetch sitemap: {error_text}")
            return

        urls, failures = result
        self._sitemap_failure_count = len(failures)
        unlinked_urls = [url for url in urls if normalize_url(url) not in self._already_linked_urls]

        if not unlinked_urls:
            message = f"All {len(urls)} blog reviews are already linked."
            if self._sitemap_failure_count:
                message += f" {self._sitemap_failure_count} sitemap(s) failed to load."
            self.status_label.setText(message)
            return

        self._progress = QProgressDialog(
            "Fetching blog reviews...", "Cancel", 0, len(unlinked_urls), self
        )
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.show()

        # The worker thread gets the book map as a local, never self.
        calibre_books = self._calibre_books
        _thread, self._fetch_worker = start_task(
            lambda cancel_event, report_progress: _fetch_and_match(
                unlinked_urls, calibre_books, cancel_event, report_progress
            ),
            self._on_fetch_complete,
            on_progress=self._on_fetch_progress,
            cancel_signal=self._progress.canceled,
            parent=self.parent(),
        )

    def _on_fetch_progress(self, index, total, url):
        self._progress.setValue(index)
        self._progress.setLabelText(f"Fetching {index + 1}/{total}...")

    def _on_fetch_complete(self, result, error_text):
        self._fetch_worker = None
        if self._is_closed:
            return
        self._progress.setValue(self._progress.maximum())

        if error_text:
            self.status_label.setText(f"Failed to fetch reviews: {error_text}")
            return

        matches, stats, was_cancelled = result
        self._matches = matches
        model = _BulkMatchModel(self._matches)
        self.table.setModel(model)
        for row in range(model.rowCount()):
            self.table.openPersistentEditor(model.index(row, _BulkMatchModel.COL_CALIBRE_MATCH))
        self.table.resizeColumnsToContents()
        self.link_button.setEnabled(bool(matches))

        summary_parts = [f"Found {len(matches)} potential match(es)."]
        if was_cancelled:
            summary_parts.insert(0, "Fetch cancelled — showing partial results.")
        if stats.outdated:
            summary_parts.append(f"{stats.outdated} old reviews skipped (have canonical).")
        if stats.errors:
            summary_parts.append(f"{stats.errors} URL(s) failed to fetch.")
        if stats.no_candidates:
            summary_parts.append(f"{stats.no_candidates} review(s) had no matching book.")
        if self._sitemap_failure_count:
            summary_parts.append(f"{self._sitemap_failure_count} sitemap(s) failed to load.")
        summary_parts.append("Pick the correct Calibre book for each row, or set to Skip.")
        self.status_label.setText(" ".join(summary_parts))

    def _on_link_all(self):
        links = selected_links(self._matches)
        if not links:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Bulk Link",
            f"Link {len(links)} book(s) and update their ratings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        rating_count = apply_links(self.db, self.column, links)

        self.linked_count = len(links)
        self.status_label.setText(
            f"Linked {self.linked_count} book(s), updated {rating_count} rating(s)."
        )
        self.link_button.setEnabled(False)


class _BulkMatchModel(QAbstractTableModel):
    HEADERS: ClassVar = [
        "Blog Title",
        "Blog Authors",
        "Rating",
        "Calibre Match",
        "Score",
    ]

    COL_BLOG_TITLE = 0
    COL_BLOG_AUTHORS = 1
    COL_RATING = 2
    COL_CALIBRE_MATCH = 3
    COL_SCORE = 4

    CANDIDATES_ROLE = Qt.ItemDataRole.UserRole + 1
    SELECTED_INDEX_ROLE = Qt.ItemDataRole.UserRole + 2

    def __init__(self, matches):
        super().__init__()
        self._data = matches

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        base = super().flags(index)
        if index.column() == self.COL_CALIBRE_MATCH:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        match = self._data[index.row()]
        column = index.column()

        if column == self.COL_CALIBRE_MATCH:
            if role == self.CANDIDATES_ROLE:
                return match.candidates
            if role == self.SELECTED_INDEX_ROLE:
                return match.selected_index
            if role == Qt.ItemDataRole.DisplayRole:
                candidate = match.selected_candidate()
                if candidate is None:
                    return SKIP_LABEL
                return candidate.display_label()
            return None

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if column == self.COL_BLOG_TITLE:
            return match.blog_title
        if column == self.COL_BLOG_AUTHORS:
            return match.blog_authors
        if column == self.COL_RATING:
            return str(match.blog_rating) if match.blog_rating else ""
        if column == self.COL_SCORE:
            candidate = match.selected_candidate()
            if candidate is None:
                return ""
            return f"{candidate.score:.0%}"
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.column() != self.COL_CALIBRE_MATCH or role != Qt.ItemDataRole.EditRole:
            return False
        if not isinstance(value, int):
            return False

        new_idx = value
        current_row = index.row()

        if new_idx > 0:
            target_id = self._data[current_row].candidates[new_idx - 1].calibre_id
            conflict_rows = find_conflict_rows(self._data, current_row, target_id)
            if conflict_rows:
                for row in [*conflict_rows, current_row]:
                    self._data[row].selected_index = 0
                    self.dataChanged.emit(
                        self.index(row, self.COL_CALIBRE_MATCH),
                        self.index(row, self.COL_SCORE),
                    )
                return True

        self._data[current_row].selected_index = new_idx
        self.dataChanged.emit(index, self.index(current_row, self.COL_SCORE))
        return True
