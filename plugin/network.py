import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from qt.core import QObject, QThread, pyqtSignal

try:
    from calibre_plugins.blog_rating_sync.constants import PLUGIN_VERSION_STRING
except ImportError:
    from constants import PLUGIN_VERSION_STRING

FETCH_TIMEOUT_SECONDS = 10
REQUEST_DELAY_SECONDS = 0.5
ALLOWED_SCHEMES = {"http", "https"}
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
USER_AGENT = (
    f"CalibreBlogRatingSync/{PLUGIN_VERSION_STRING} (Calibre plugin; +https://alexgude.com)"
)
FALLBACK_CHARSET = "utf-8"


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed, must be http or https")


def _open_url(url):
    validate_url(url)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    return urlopen(request, timeout=FETCH_TIMEOUT_SECONDS)


def _read_capped(response):
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Response exceeds {MAX_RESPONSE_BYTES} bytes")
    return data


def fetch_bytes(url):
    """Fetch a URL and return the raw response body."""
    with _open_url(url) as response:
        return _read_capped(response)


def fetch_page(url):
    """Fetch a URL and return the body decoded per the response charset."""
    with _open_url(url) as response:
        data = _read_capped(response)
        charset = response.headers.get_content_charset() or FALLBACK_CHARSET
    try:
        return data.decode(charset, errors="replace")
    except LookupError:  # server declared a charset Python does not know
        return data.decode(FALLBACK_CHARSET, errors="replace")


class BatchFetchWorker(QObject):
    """Fetches a list of URLs on a background thread."""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list, bool)

    def __init__(self, urls):
        super().__init__()
        self._urls = urls
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        results = []
        total = len(self._urls)
        for index, url in enumerate(self._urls):
            if self._is_cancelled:
                break
            self.progress.emit(index, total, url)
            try:
                html = fetch_page(url)
                results.append((url, html, None))
            except (URLError, OSError, ValueError) as error:
                results.append((url, None, str(error)))
            if index < total - 1:
                time.sleep(REQUEST_DELAY_SECONDS)
        self.finished.emit(results, self._is_cancelled)


def start_batch_fetch(urls, on_progress, on_finished, parent=None):
    """Start fetching URLs on a background thread.

    The thread is parented to `parent` (which must outlive the fetch) and
    deletes itself and the worker once done, so callers may drop the returned
    (thread, worker) references at any time — e.g. when a dialog closes
    mid-fetch. on_finished receives (results, was_cancelled).
    """
    thread = QThread(parent)
    worker = BatchFetchWorker(urls)
    worker.moveToThread(thread)
    thread._worker = worker  # keep the worker alive for the thread's lifetime

    thread.started.connect(worker.run)
    worker.progress.connect(on_progress)
    worker.finished.connect(on_finished)
    worker.finished.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    thread.start()
    return thread, worker
