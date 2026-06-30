from urllib.error import URLError

from calibre_plugins.blog_rating_sync.config import prefs
from calibre_plugins.blog_rating_sync.network import start_batch_fetch
from calibre_plugins.blog_rating_sync.scraper import (
    extract_book_info,
    extract_rating,
    find_canonical_url,
    match_score,
)
from calibre_plugins.blog_rating_sync.sitemap import fetch_book_urls
from qt.core import (
    QAbstractTableModel,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QTableView,
    QVBoxLayout,
    Qt,
)

AUTO_CHECK_THRESHOLD = 4


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
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.link_button = QPushButton("Link all checked")
        self.link_button.clicked.connect(self._on_link_all)
        self.link_button.setEnabled(False)
        button_row.addWidget(self.link_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._matches = []
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

        try:
            all_blog_urls = fetch_book_urls(sitemap_url)
        except (URLError, OSError) as error:
            self.status_label.setText(f"Failed to fetch sitemap: {error}")
            return

        unlinked_urls = [
            url for url in all_blog_urls
            if url.rstrip("/") not in already_linked_urls
        ]

        if not unlinked_urls:
            self.status_label.setText(
                f"All {len(all_blog_urls)} blog reviews are already linked."
            )
            return

        self._calibre_books = calibre_books

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

        claimed_book_ids = set()
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

            best_id = None
            best_score = 0
            for book_id, (calibre_title, calibre_authors) in self._calibre_books.items():
                if book_id in claimed_book_ids:
                    continue
                score = match_score(
                    blog_title, blog_authors, calibre_title, calibre_authors
                )
                if score > best_score:
                    best_score = score
                    best_id = book_id

            if best_id is None:
                continue

            claimed_book_ids.add(best_id)
            calibre_title, calibre_authors = self._calibre_books[best_id]
            matches.append({
                "is_checked": best_score >= AUTO_CHECK_THRESHOLD,
                "blog_title": blog_title,
                "blog_authors": ", ".join(blog_authors),
                "blog_rating": blog_rating,
                "blog_url": url,
                "calibre_id": best_id,
                "calibre_title": calibre_title,
                "calibre_authors": ", ".join(calibre_authors),
                "score": best_score,
            })

        self._matches = sorted(matches, key=lambda match: -match["score"])
        model = _BulkMatchModel(self._matches)
        self.table.setModel(model)
        self.table.resizeColumnsToContents()
        self.link_button.setEnabled(bool(matches))

        summary_parts = [f"Found {len(matches)} potential match(es)."]
        if skipped_canonical_count:
            summary_parts.append(f"{skipped_canonical_count} old reviews skipped (have canonical).")
        if error_count:
            summary_parts.append(f"{error_count} URL(s) failed to fetch.")
        summary_parts.append("Review the matches and uncheck any that are wrong.")
        self.status_label.setText(" ".join(summary_parts))

        self._fetch_thread = None
        self._fetch_worker = None

    def _on_link_all(self):
        count = 0
        for match in self._matches:
            if not match["is_checked"]:
                continue
            self.db.set_field(
                self.column, {match["calibre_id"]: match["blog_url"]}
            )
            count += 1

        self.linked_count = count
        self.status_label.setText(f"Linked {count} book(s).")
        self.link_button.setEnabled(False)


class _BulkMatchModel(QAbstractTableModel):
    HEADERS = [
        "",
        "Blog Title",
        "Blog Authors",
        "Rating",
        "Calibre Title",
        "Calibre Authors",
        "Score",
    ]

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
        if index.column() == 0:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        row = self._data[index.row()]
        column = index.column()

        if column == 0 and role == Qt.ItemDataRole.CheckStateRole:
            return (
                Qt.CheckState.Checked if row["is_checked"]
                else Qt.CheckState.Unchecked
            )

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if column == 1:
            return row["blog_title"]
        if column == 2:
            return row["blog_authors"]
        if column == 3:
            return str(row["blog_rating"]) if row["blog_rating"] else ""
        if column == 4:
            return row["calibre_title"]
        if column == 5:
            return row["calibre_authors"]
        if column == 6:
            return str(row["score"])
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.column() != 0 or role != Qt.ItemDataRole.CheckStateRole:
            return False
        self._data[index.row()]["is_checked"] = value in (
            Qt.CheckState.Checked,
            Qt.CheckState.Checked.value,
        )
        self.dataChanged.emit(index, index)
        return True
