from calibre_plugins.blog_rating_sync.network import fetch_page
from calibre_plugins.blog_rating_sync.scraper import parse_review_page
from qt.core import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QThread,
    QVBoxLayout,
    pyqtSignal,
)


class _FetchWorker(QThread):
    succeeded = pyqtSignal(str, str)
    failed = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            html = fetch_page(self._url)
            self.succeeded.emit(self._url, html)
        except Exception as error:
            self.failed.emit(str(error))


class LinkDialog(QDialog):
    def __init__(self, parent, db, column, book_id):
        super().__init__(parent)
        self.db = db
        self.column = column
        self.book_id = book_id
        self.linked_count = 0
        self.setWindowTitle("Link URL to Selected Book")
        self.resize(500, 200)

        layout = QVBoxLayout()
        self.setLayout(layout)

        title = db.field_for("title", book_id)
        authors = db.field_for("authors", book_id) or ()
        author_str = ", ".join(authors) if authors else "Unknown"
        book_label = QLabel(f'Book: "{title}" by {author_str}')
        book_label.setWordWrap(True)
        layout.addWidget(book_label)

        existing_url = db.field_for(column, book_id) or ""
        if existing_url:
            existing_label = QLabel(f"Currently linked to: {existing_url}")
            existing_label.setWordWrap(True)
            layout.addWidget(existing_label)

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
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        self.link_button = QPushButton("Link")
        self.link_button.setEnabled(False)
        self.link_button.clicked.connect(self._on_link)
        button_row.addWidget(self.link_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._fetched_url = None
        self._fetch_thread = None

    def _on_fetch(self):
        url = self.url_edit.text().strip()
        if not url:
            return

        self.fetch_button.setEnabled(False)
        self.link_button.setEnabled(False)
        self.status_label.setText("Fetching...")
        # Parent the thread to the main window, not this dialog: the fetch
        # cannot be interrupted, and the thread must survive the dialog
        # closing mid-fetch. Signals to this dialog disconnect automatically
        # if it is destroyed; deleteLater cleans the thread up when done.
        self._fetch_thread = _FetchWorker(url, self.parent())
        self._fetch_thread.succeeded.connect(self._on_fetch_succeeded)
        self._fetch_thread.failed.connect(self._on_fetch_failed)
        self._fetch_thread.finished.connect(self._fetch_thread.deleteLater)
        self._fetch_thread.start()

    def _on_fetch_failed(self, error_message):
        self.status_label.setText(f"Error: {error_message}")
        self.fetch_button.setEnabled(True)

    def _on_fetch_succeeded(self, url, html):
        self.fetch_button.setEnabled(True)

        page = parse_review_page(url, html)
        if page.is_outdated:
            self.status_label.setText(
                "This is an old review. Canonical URL: "
                f"{page.canonical_url}\nUse the canonical URL instead."
            )
            return

        if not page.title:
            self.status_label.setText("No book review found in page JSON-LD.")
            return

        author_string = ", ".join(page.authors) if page.authors else "Unknown"
        rating_string = f" (rating: {page.rating})" if page.rating else ""
        self.status_label.setText(f'Review found: "{page.title}" by {author_string}{rating_string}')

        self._fetched_url = url
        self.link_button.setEnabled(True)

    def _on_link(self):
        self.db.set_field(self.column, {self.book_id: self._fetched_url})
        self.linked_count += 1

        title = self.db.field_for("title", self.book_id)
        self.status_label.setText(f'Linked "{title}" → {self._fetched_url}')
        self.link_button.setEnabled(False)
