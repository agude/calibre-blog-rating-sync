from urllib.request import urlopen
from urllib.error import URLError

from calibre_plugins.blog_rating_sync.config import prefs
from calibre_plugins.blog_rating_sync.scraper import (
    extract_book_info,
    extract_rating,
    find_canonical_url,
)
from qt.core import (
    QAbstractTableModel,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    Qt,
)


class LinkDialog(QDialog):
    def __init__(self, parent, db, column):
        super().__init__(parent)
        self.db = db
        self.column = column
        self.linked_count = 0
        self.setWindowTitle("Link Book to Blog Review")
        self.resize(700, 400)

        layout = QVBoxLayout()
        self.setLayout(layout)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Review URL:"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://alexgude.com/books/hyperion/")
        url_row.addWidget(self.url_edit)
        fetch_btn = QPushButton("Fetch")
        fetch_btn.clicked.connect(self._on_fetch)
        url_row.addWidget(fetch_btn)
        layout.addLayout(url_row)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.table = QTableView()
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        btn_box = QHBoxLayout()
        self.link_btn = QPushButton("Link selected book")
        self.link_btn.setEnabled(False)
        self.link_btn.clicked.connect(self._on_link)
        btn_box.addWidget(self.link_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

        self._fetched_url = None
        self._candidates = []

    def _on_fetch(self):
        url = self.url_edit.text().strip()
        if not url:
            return

        self.status_label.setText("Fetching...")
        try:
            html = urlopen(url, timeout=10).read().decode("utf-8")
        except (URLError, OSError) as e:
            self.status_label.setText(f"Error: {e}")
            return

        canonical = find_canonical_url(html)
        if canonical and canonical != url:
            self.status_label.setText(f"Following canonical URL: {canonical}")
            self._fetched_url = canonical
        else:
            self._fetched_url = url

        blog_title, blog_authors = extract_book_info(html)
        blog_rating = extract_rating(html)
        if not blog_title:
            self.status_label.setText("No book review found in page JSON-LD.")
            return

        author_str = ", ".join(blog_authors) if blog_authors else "Unknown"
        rating_str = f" (rating: {blog_rating})" if blog_rating else ""
        self.status_label.setText(
            f'Found: "{blog_title}" by {author_str}{rating_str}\n'
            f"Select a matching book from your library below:"
        )

        self._find_candidates(blog_title, blog_authors)

    def _find_candidates(self, blog_title, blog_authors):
        candidates = []
        blog_title_lower = blog_title.lower()
        blog_author_words = {
            w.lower() for a in blog_authors for w in a.split()
        }

        for book_id in self.db.all_book_ids():
            title = self.db.field_for("title", book_id)
            authors = self.db.field_for("authors", book_id) or ()

            title_lower = title.lower() if title else ""
            if blog_title_lower not in title_lower and title_lower not in blog_title_lower:
                continue

            author_words = {w.lower() for a in authors for w in a.split()}
            if blog_author_words and not blog_author_words & author_words:
                continue

            existing_url = self.db.field_for(self.column, book_id) or ""
            rating = self.db.field_for("rating", book_id) or 0
            candidates.append({
                "id": book_id,
                "title": title,
                "authors": ", ".join(authors),
                "rating": rating // 2,
                "linked": existing_url,
            })

        self._candidates = candidates
        model = _CandidateModel(candidates)
        self.table.setModel(model)
        self.table.selectionModel().selectionChanged.connect(
            lambda: self.link_btn.setEnabled(True)
        )
        self.link_btn.setEnabled(False)

        if not candidates:
            self.status_label.setText(
                self.status_label.text() + "\n\nNo matching books found in library."
            )

    def _on_link(self):
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return

        row = indexes[0].row()
        candidate = self._candidates[row]
        book_id = candidate["id"]

        self.db.set_field(self.column, {book_id: self._fetched_url})
        self.linked_count += 1

        self.status_label.setText(
            f'Linked "{candidate["title"]}" → {self._fetched_url}'
        )
        self.link_btn.setEnabled(False)
        self.url_edit.clear()


class _CandidateModel(QAbstractTableModel):
    HEADERS = ["Title", "Authors", "Rating", "Already linked"]

    def __init__(self, candidates):
        super().__init__()
        self._data = candidates

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        row = self._data[index.row()]
        col = index.column()
        if col == 0:
            return row["title"]
        if col == 1:
            return row["authors"]
        if col == 2:
            return str(row["rating"]) if row["rating"] else ""
        if col == 3:
            return row["linked"]
        return None
