from urllib.request import urlopen
from urllib.error import URLError

from calibre_plugins.blog_rating_sync.config import prefs
from calibre_plugins.blog_rating_sync.scraper import (
    extract_book_info,
    extract_rating,
    find_canonical_url,
    match_score,
)
from calibre_plugins.blog_rating_sync.sitemap import fetch_book_urls
from qt.core import (
    QAbstractTableModel,
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressDialog,
    QPushButton,
    QTableView,
    QVBoxLayout,
    Qt,
)


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

        btn_row = QHBoxLayout()
        self.link_btn = QPushButton("Link all checked")
        self.link_btn.clicked.connect(self._on_link_all)
        self.link_btn.setEnabled(False)
        btn_row.addWidget(self.link_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._matches = []

    def discover(self):
        base_url = prefs["blog_base_url"].rstrip("/")
        sitemap_url = base_url + "/sitemap.xml"

        already_linked = set()
        for book_id in self.db.all_book_ids():
            url = self.db.field_for(self.column, book_id)
            if url:
                already_linked.add(url.rstrip("/"))

        try:
            blog_urls = fetch_book_urls(sitemap_url)
        except (URLError, OSError) as e:
            self.status_label.setText(f"Failed to fetch sitemap: {e}")
            return

        unlinked_urls = [
            u for u in blog_urls if u.rstrip("/") not in already_linked
        ]

        if not unlinked_urls:
            self.status_label.setText(
                f"All {len(blog_urls)} blog reviews are already linked."
            )
            return

        calibre_books = {}
        for book_id in self.db.all_book_ids():
            existing = self.db.field_for(self.column, book_id)
            if existing:
                continue
            title = self.db.field_for("title", book_id)
            authors = self.db.field_for("authors", book_id) or ()
            calibre_books[book_id] = (title, list(authors))

        progress = QProgressDialog(
            "Fetching blog reviews...", "Cancel", 0, len(unlinked_urls), self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        matches = []
        skipped = 0
        errors = 0

        for i, url in enumerate(unlinked_urls):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"Fetching {i + 1}/{len(unlinked_urls)}...")
            QApplication.processEvents()

            try:
                html = urlopen(url, timeout=10).read().decode("utf-8")
            except (URLError, OSError):
                errors += 1
                continue

            canonical = find_canonical_url(html)
            if canonical and canonical.rstrip("/") != url.rstrip("/"):
                skipped += 1
                continue

            blog_title, blog_authors = extract_book_info(html)
            blog_rating = extract_rating(html)
            if not blog_title:
                errors += 1
                continue

            best_id = None
            best_score = 0
            for book_id, (cal_title, cal_authors) in calibre_books.items():
                score = match_score(
                    blog_title, blog_authors, cal_title, cal_authors
                )
                if score > best_score:
                    best_score = score
                    best_id = book_id

            if best_id is None:
                continue

            cal_title, cal_authors = calibre_books[best_id]
            matches.append({
                "checked": best_score >= 4,
                "blog_title": blog_title,
                "blog_authors": ", ".join(blog_authors),
                "blog_rating": blog_rating,
                "blog_url": url,
                "calibre_id": best_id,
                "calibre_title": cal_title,
                "calibre_authors": ", ".join(cal_authors),
                "score": best_score,
            })

        progress.setValue(len(unlinked_urls))

        self._matches = sorted(matches, key=lambda m: -m["score"])
        model = _BulkMatchModel(self._matches)
        self.table.setModel(model)
        self.table.resizeColumnsToContents()
        self.link_btn.setEnabled(bool(matches))

        parts = [f"Found {len(matches)} potential match(es)."]
        if skipped:
            parts.append(f"{skipped} old reviews skipped (have canonical).")
        if errors:
            parts.append(f"{errors} URL(s) failed to fetch.")
        parts.append("Review the matches and uncheck any that are wrong.")
        self.status_label.setText(" ".join(parts))

    def _on_link_all(self):
        count = 0
        for match in self._matches:
            if not match["checked"]:
                continue
            self.db.set_field(
                self.column, {match["calibre_id"]: match["blog_url"]}
            )
            count += 1

        self.linked_count = count
        self.status_label.setText(f"Linked {count} book(s).")
        self.link_btn.setEnabled(False)


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
        col = index.column()

        if col == 0 and role == Qt.ItemDataRole.CheckStateRole:
            return (
                Qt.CheckState.Checked if row["checked"] else Qt.CheckState.Unchecked
            )

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if col == 1:
            return row["blog_title"]
        if col == 2:
            return row["blog_authors"]
        if col == 3:
            return str(row["blog_rating"]) if row["blog_rating"] else ""
        if col == 4:
            return row["calibre_title"]
        if col == 5:
            return row["calibre_authors"]
        if col == 6:
            return str(row["score"])
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            self._data[index.row()]["checked"] = value == Qt.CheckState.Checked.value
            self.dataChanged.emit(index, index)
            return True
        return False
