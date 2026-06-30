from calibre_plugins.blog_rating_sync.config import prefs
from calibre_plugins.blog_rating_sync.network import start_batch_fetch
from calibre_plugins.blog_rating_sync.scraper import (
    extract_book_info,
    extract_rating,
    find_canonical_url,
    match_score,
)
from calibre_plugins.blog_rating_sync.sitemap import fetch_book_urls
from calibre_plugins.blog_rating_sync.sync import CALIBRE_STARS_MULTIPLIER
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
    QTableView,
    QThread,
    QVBoxLayout,
    Qt,
)

AUTO_SELECT_THRESHOLD = 0.7
MINIMUM_MATCH_SCORE = 0.3
TOP_N_CANDIDATES = 5
SKIP_LABEL = "— Skip —"


class _SitemapFetchThread(QThread):
    def __init__(self, sitemap_url):
        super().__init__()
        self._sitemap_url = sitemap_url
        self.urls = []
        self.error = None

    def run(self):
        try:
            self.urls = fetch_book_urls(self._sitemap_url)
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
            label = f"{candidate['calibre_title']} — {candidate['calibre_authors']} ({candidate['score']:.0%})"
            combo.addItem(label, candidate)
        selected = index.data(_BulkMatchModel.SELECTED_INDEX_ROLE)
        combo.setCurrentIndex(selected)
        # activated fires only on user interaction, not programmatic setCurrentIndex,
        # so this won't loop when setEditorData syncs the combo after dataChanged.
        combo.activated.connect(
            lambda i: index.model().setData(index, i, Qt.ItemDataRole.EditRole)
        )
        return combo

    def setEditorData(self, editor, index):
        selected = index.data(_BulkMatchModel.SELECTED_INDEX_ROLE)
        editor.setCurrentIndex(selected)

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
        self._sitemap_thread = None
        self._fetch_thread = None
        self._fetch_worker = None

    def discover(self):
        base_url = prefs["blog_base_url"].rstrip("/")
        sitemap_url = base_url + "/sitemap.xml"

        already_linked_urls = set()
        calibre_books = {}
        for book_id in self.db.all_book_ids():
            url = self.db.field_for(self.column, book_id)
            if url:
                already_linked_urls.add(url.rstrip("/"))
                continue
            title = self.db.field_for("title", book_id)
            authors = self.db.field_for("authors", book_id) or ()
            calibre_books[book_id] = (title, list(authors))

        self._calibre_books = calibre_books
        self._already_linked_urls = already_linked_urls

        self._sitemap_thread = _SitemapFetchThread(sitemap_url)
        self._sitemap_thread.finished.connect(self._on_sitemap_fetched)
        self._sitemap_thread.start()

    def _on_sitemap_fetched(self):
        thread = self._sitemap_thread
        self._sitemap_thread = None

        if thread.error:
            self.status_label.setText(f"Failed to fetch sitemap: {thread.error}")
            return

        unlinked_urls = [
            url for url in thread.urls
            if url.rstrip("/") not in self._already_linked_urls
        ]

        if not unlinked_urls:
            self.status_label.setText(
                f"All {len(thread.urls)} blog reviews are already linked."
            )
            return

        self._progress = QProgressDialog(
            "Fetching blog reviews...", "Cancel", 0, len(unlinked_urls), self
        )
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.show()

        def on_progress(index, total, url):
            self._progress.setValue(index)
            self._progress.setLabelText(f"Fetching {index + 1}/{total}...")

        self._fetch_thread, self._fetch_worker = start_batch_fetch(
            unlinked_urls, on_progress, self._on_fetch_complete
        )
        self._progress.canceled.connect(self._fetch_worker.cancel)

    def _on_fetch_complete(self, fetch_results):
        self._progress.setValue(self._progress.maximum())

        matches = []
        skipped_canonical_count = 0
        error_count = 0

        for url, html, fetch_error in fetch_results:
            if fetch_error:
                error_count += 1
                continue

            canonical = find_canonical_url(html)
            if canonical and canonical.rstrip("/") != url.rstrip("/"):
                skipped_canonical_count += 1
                continue

            blog_title, blog_authors = extract_book_info(html)
            blog_rating = extract_rating(html)
            if not blog_title:
                error_count += 1
                continue

            scored = []
            for book_id, (calibre_title, calibre_authors) in self._calibre_books.items():
                score = match_score(
                    blog_title, blog_authors, calibre_title, calibre_authors
                )
                if score >= MINIMUM_MATCH_SCORE:
                    scored.append({
                        "calibre_id": book_id,
                        "calibre_title": calibre_title,
                        "calibre_authors": ", ".join(calibre_authors),
                        "score": score,
                    })

            scored.sort(key=lambda c: -c["score"])
            candidates = scored[:TOP_N_CANDIDATES]

            if not candidates:
                continue

            best = candidates[0]
            selected_index = 1 if best["score"] >= AUTO_SELECT_THRESHOLD else 0

            matches.append({
                "blog_title": blog_title,
                "blog_authors": ", ".join(blog_authors),
                "blog_rating": blog_rating,
                "blog_url": url,
                "candidates": candidates,
                "selected_index": selected_index,
            })

        # For each Calibre book, find the blog URL that scores highest against it.
        # Only keep rows where this blog URL is the best claimant for at least one
        # Calibre book — prevents many blog posts all mapping to the same book.
        best_blog_for_calibre = {}  # calibre_id -> (score, blog_url)
        for match in matches:
            top = match["candidates"][0]
            cid = top["calibre_id"]
            score = top["score"]
            if cid not in best_blog_for_calibre or score > best_blog_for_calibre[cid][0]:
                best_blog_for_calibre[cid] = (score, match["blog_url"])
        winning_urls = {url for _, url in best_blog_for_calibre.values()}
        matches = [m for m in matches if m["blog_url"] in winning_urls]

        self._matches = sorted(matches, key=lambda m: -m["candidates"][0]["score"])
        model = _BulkMatchModel(self._matches)
        self.table.setModel(model)
        for row in range(model.rowCount()):
            self.table.openPersistentEditor(
                model.index(row, _BulkMatchModel.COL_CALIBRE_MATCH)
            )
        self.table.resizeColumnsToContents()
        self.link_button.setEnabled(bool(matches))

        summary_parts = [f"Found {len(matches)} potential match(es)."]
        if skipped_canonical_count:
            summary_parts.append(f"{skipped_canonical_count} old reviews skipped (have canonical).")
        if error_count:
            summary_parts.append(f"{error_count} URL(s) failed to fetch.")
        summary_parts.append("Pick the correct Calibre book for each row, or set to Skip.")
        self.status_label.setText(" ".join(summary_parts))

        self._fetch_thread = None
        self._fetch_worker = None

    def _on_link_all(self):
        to_link = []
        for match in self._matches:
            idx = match["selected_index"]
            if idx == 0:
                continue
            candidate = match["candidates"][idx - 1]
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

        rating_count = 0
        for match, candidate in to_link:
            self.db.set_field(
                self.column, {candidate["calibre_id"]: match["blog_url"]}
            )
            if match["blog_rating"] is not None:
                new_rating = match["blog_rating"] * CALIBRE_STARS_MULTIPLIER
                self.db.set_field("rating", {candidate["calibre_id"]: new_rating})
                rating_count += 1

        self.linked_count = len(to_link)
        self.status_label.setText(
            f"Linked {self.linked_count} book(s), updated {rating_count} rating(s)."
        )
        self.link_button.setEnabled(False)


class _BulkMatchModel(QAbstractTableModel):
    HEADERS = [
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
        row = self._data[index.row()]
        column = index.column()

        if column == self.COL_CALIBRE_MATCH:
            if role == self.CANDIDATES_ROLE:
                return row["candidates"]
            if role == self.SELECTED_INDEX_ROLE:
                return row["selected_index"]
            if role == Qt.ItemDataRole.DisplayRole:
                idx = row["selected_index"]
                if idx == 0:
                    return SKIP_LABEL
                candidate = row["candidates"][idx - 1]
                return f"{candidate['calibre_title']} — {candidate['calibre_authors']}"
            return None

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if column == self.COL_BLOG_TITLE:
            return row["blog_title"]
        if column == self.COL_BLOG_AUTHORS:
            return row["blog_authors"]
        if column == self.COL_RATING:
            return str(row["blog_rating"]) if row["blog_rating"] else ""
        if column == self.COL_SCORE:
            idx = row["selected_index"]
            if idx == 0:
                return ""
            return f"{row['candidates'][idx - 1]['score']:.0%}"
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.column() != self.COL_CALIBRE_MATCH or role != Qt.ItemDataRole.EditRole:
            return False

        new_idx = value
        current_row = index.row()

        if new_idx > 0:
            target_id = self._data[current_row]["candidates"][new_idx - 1]["calibre_id"]
            # Collect ALL rows (not just the first) that already have this book selected.
            conflict_rows = [
                row for row, match in enumerate(self._data)
                if row != current_row
                and match["selected_index"] > 0
                and match["candidates"][match["selected_index"] - 1]["calibre_id"] == target_id
            ]
            if conflict_rows:
                # Reset every conflict row AND the incoming row to Skip so all are
                # free for the next run.
                for row in conflict_rows + [current_row]:
                    self._data[row]["selected_index"] = 0
                    self.dataChanged.emit(
                        self.index(row, self.COL_CALIBRE_MATCH),
                        self.index(row, self.COL_SCORE),
                    )
                return True

        self._data[current_row]["selected_index"] = new_idx
        self.dataChanged.emit(index, self.index(current_row, self.COL_SCORE))
        return True
