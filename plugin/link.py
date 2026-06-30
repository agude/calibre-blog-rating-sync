from calibre_plugins.blog_rating_sync.network import fetch_page
from calibre_plugins.blog_rating_sync.scraper import (
    extract_book_info,
    extract_rating,
    find_canonical_url,
    match_score,
)
from qt.core import (
    QAbstractTableModel,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QThread,
    QVBoxLayout,
    Qt,
    pyqtSignal,
)

CALIBRE_STARS_MULTIPLIER = 2


class _FetchWorker(QThread):
    finished = pyqtSignal(str, str)
    failed = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self._url = url

    def run(self):
        try:
            html = fetch_page(self._url)
            self.finished.emit(self._url, html)
        except Exception as error:
            self.failed.emit(str(error))


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
        self.fetch_button = QPushButton("Fetch")
        self.fetch_button.clicked.connect(self._on_fetch)
        url_row.addWidget(self.fetch_button)
        layout.addLayout(url_row)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.table = QTableView()
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.link_button = QPushButton("Link selected book")
        self.link_button.setEnabled(False)
        self.link_button.clicked.connect(self._on_link)
        button_row.addWidget(self.link_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._fetched_url = None
        self._candidates = []
        self._fetch_thread = None

    def _on_fetch(self):
        url = self.url_edit.text().strip()
        if not url:
            return

        self.fetch_button.setEnabled(False)
        self.status_label.setText("Fetching...")
        self._fetch_thread = _FetchWorker(url)
        self._fetch_thread.finished.connect(self._on_fetch_finished)
        self._fetch_thread.failed.connect(self._on_fetch_failed)
        self._fetch_thread.start()

    def _on_fetch_failed(self, error_message):
        self.status_label.setText(f"Error: {error_message}")
        self.fetch_button.setEnabled(True)

    def _on_fetch_finished(self, url, html):
        self.fetch_button.setEnabled(True)

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

        author_string = ", ".join(blog_authors) if blog_authors else "Unknown"
        rating_string = f" (rating: {blog_rating})" if blog_rating else ""
        self.status_label.setText(
            f'Found: "{blog_title}" by {author_string}{rating_string}\n'
            f"Select a matching book from your library below:"
        )

        self._find_candidates(blog_title, blog_authors)

    def _find_candidates(self, blog_title, blog_authors):
        candidates = []

        for book_id in self.db.all_book_ids():
            calibre_title = self.db.field_for("title", book_id)
            calibre_authors = self.db.field_for("authors", book_id) or ()

            score = match_score(blog_title, blog_authors, calibre_title, list(calibre_authors))
            if score == 0:
                continue

            existing_url = self.db.field_for(self.column, book_id) or ""
            rating = self.db.field_for("rating", book_id) or 0
            candidates.append({
                "id": book_id,
                "title": calibre_title,
                "authors": ", ".join(calibre_authors),
                "rating": rating // CALIBRE_STARS_MULTIPLIER,
                "linked": existing_url,
                "score": score,
            })

        candidates.sort(key=lambda candidate: -candidate["score"])
        self._candidates = candidates
        model = _CandidateModel(candidates)
        self.table.setModel(model)
        self.table.selectionModel().selectionChanged.connect(
            lambda: self.link_button.setEnabled(True)
        )
        self.link_button.setEnabled(False)

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

        self.db.set_field(self.column, {candidate["id"]: self._fetched_url})
        self.linked_count += 1

        self.status_label.setText(
            f'Linked "{candidate["title"]}" → {self._fetched_url}'
        )
        self.link_button.setEnabled(False)
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
        column = index.column()
        if column == 0:
            return row["title"]
        if column == 1:
            return row["authors"]
        if column == 2:
            return str(row["rating"]) if row["rating"] else ""
        if column == 3:
            return row["linked"]
        return None
