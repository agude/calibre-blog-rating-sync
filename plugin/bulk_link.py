from typing import ClassVar

from calibre_plugins.blog_rating_sync.config import prefs
from calibre_plugins.blog_rating_sync.matching import (
    AUTO_SELECT_THRESHOLD,
    MINIMUM_MATCH_SCORE,
    TOP_N_CANDIDATES,
    MatchCandidate,
    ReviewMatch,
    deselect_duplicate_selections,
    find_conflict_rows,
)
from calibre_plugins.blog_rating_sync.network import start_batch_fetch
from calibre_plugins.blog_rating_sync.scraper import (
    match_score,
    normalize_url,
    parse_review_page,
)
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
    QThread,
    QVBoxLayout,
)

SKIP_LABEL = "— Skip —"


class _SitemapFetchThread(QThread):
    def __init__(self, sitemap_url, parent=None):
        super().__init__(parent)
        self._sitemap_url = sitemap_url
        self.urls = []
        self.failures = []
        self.error = None

    def run(self):
        try:
            self.urls, self.failures = fetch_book_urls(self._sitemap_url)
        except Exception as error:
            self.error = str(error)


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
        self._sitemap_thread = None
        self._sitemap_failure_count = 0
        self._fetch_worker = None
        self._is_closed = False

    def done(self, result):
        # Closing mid-fetch: stop the batch worker (the parented thread cleans
        # itself up, see start_batch_fetch) and make sure a still-running
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
        # closing mid-fetch; deleteLater cleans it up when done.
        self._sitemap_thread = _SitemapFetchThread(sitemap_url, self.parent())
        self._sitemap_thread.finished.connect(self._on_sitemap_fetched)
        self._sitemap_thread.finished.connect(self._sitemap_thread.deleteLater)
        self._sitemap_thread.start()

    def _on_sitemap_fetched(self):
        thread = self._sitemap_thread
        self._sitemap_thread = None

        if self._is_closed:
            return

        if thread.error:
            self.status_label.setText(f"Failed to fetch sitemap: {thread.error}")
            return

        self._sitemap_failure_count = len(thread.failures)
        unlinked_urls = [
            url for url in thread.urls if normalize_url(url) not in self._already_linked_urls
        ]

        if not unlinked_urls:
            message = f"All {len(thread.urls)} blog reviews are already linked."
            if self._sitemap_failure_count:
                message += f" {self._sitemap_failure_count} sitemap(s) failed to load."
            self.status_label.setText(message)
            return

        self._progress = QProgressDialog(
            "Fetching blog reviews...", "Cancel", 0, len(unlinked_urls), self
        )
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.show()

        _thread, self._fetch_worker = start_batch_fetch(
            unlinked_urls,
            self._on_fetch_progress,
            self._on_fetch_complete,
            cancel_signal=self._progress.canceled,
            parent=self.parent(),
        )

    def _on_fetch_progress(self, index, total, url):
        self._progress.setValue(index)
        self._progress.setLabelText(f"Fetching {index + 1}/{total}...")

    def _on_fetch_complete(self, fetch_results, was_cancelled):
        self._fetch_worker = None
        if self._is_closed:
            return
        self._progress.setValue(self._progress.maximum())

        matches = []
        skipped_canonical_count = 0
        error_count = 0

        for url, html, fetch_error in fetch_results:
            if fetch_error:
                error_count += 1
                continue

            page = parse_review_page(url, html)
            if page.is_outdated:
                skipped_canonical_count += 1
                continue

            if not page.title:
                error_count += 1
                continue

            scored = []
            for book_id, (calibre_title, calibre_authors) in self._calibre_books.items():
                score = match_score(page.title, page.authors, calibre_title, calibre_authors)
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
            candidates = scored[:TOP_N_CANDIDATES]

            if not candidates:
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

        self._matches = sorted(matches, key=lambda match: match.candidates[0].score, reverse=True)
        model = _BulkMatchModel(self._matches)
        self.table.setModel(model)
        for row in range(model.rowCount()):
            self.table.openPersistentEditor(model.index(row, _BulkMatchModel.COL_CALIBRE_MATCH))
        self.table.resizeColumnsToContents()
        self.link_button.setEnabled(bool(matches))

        summary_parts = [f"Found {len(matches)} potential match(es)."]
        if was_cancelled:
            summary_parts.insert(0, "Fetch cancelled — showing partial results.")
        if skipped_canonical_count:
            summary_parts.append(f"{skipped_canonical_count} old reviews skipped (have canonical).")
        if error_count:
            summary_parts.append(f"{error_count} URL(s) failed to fetch.")
        if self._sitemap_failure_count:
            summary_parts.append(f"{self._sitemap_failure_count} sitemap(s) failed to load.")
        summary_parts.append("Pick the correct Calibre book for each row, or set to Skip.")
        self.status_label.setText(" ".join(summary_parts))

    def _on_link_all(self):
        to_link = []
        for match in self._matches:
            candidate = match.selected_candidate()
            if candidate is not None:
                to_link.append((match, candidate))

        if not to_link:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Bulk Link",
            f"Link {len(to_link)} book(s) and update their ratings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        links = [
            (candidate.calibre_id, match.blog_url, match.blog_rating)
            for match, candidate in to_link
        ]
        rating_count = apply_links(self.db, self.column, links)

        self.linked_count = len(to_link)
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
