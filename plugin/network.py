import threading
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from calibre_plugins.blog_rating_sync.constants import PLUGIN_VERSION_STRING
from qt.core import QObject, Qt, QThread, pyqtSignal

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
    declared = _declared_length(response)
    if declared is not None and len(data) < declared:
        raise ValueError(f"Truncated response: got {len(data)} of {declared} bytes")
    return data


def _declared_length(response):
    """Return the Content-Length as an int, or None if absent or unparseable."""
    try:
        return int(response.headers.get("Content-Length"))
    except (TypeError, ValueError):
        return None


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


def fetch_all(urls, fetch=None, cancel_event=None, on_progress=None, delay_seconds=None):
    """Fetch each URL in order and return (results, was_cancelled).

    Each result is (url, html, error). An exception from one fetch becomes that
    URL's error text, and the loop continues. The wait between URLs goes through
    cancel_event, so a cancel ends the wait at once.
    """
    if fetch is None:
        fetch = fetch_page
    if delay_seconds is None:
        delay_seconds = REQUEST_DELAY_SECONDS
    if cancel_event is None:
        cancel_event = threading.Event()

    results = []
    total = len(urls)
    for index, url in enumerate(urls):
        if cancel_event.is_set():
            break
        if on_progress is not None:
            on_progress(index, total, url)
        try:
            html = fetch(url)
            results.append((url, html, None))
        except Exception as error:
            results.append((url, None, str(error) or type(error).__name__))
        if index < total - 1:
            cancel_event.wait(delay_seconds)
    return results, cancel_event.is_set()


class _TaskWorker(QObject):
    """Runs one task on a background thread and reports its outcome once."""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(object, object)

    def __init__(self, task):
        super().__init__()
        self._task = task
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def run(self):
        result = None
        # Pre-set so a BaseException, which the except clause does not catch,
        # still reports a failure rather than success.
        error_text = "Task ended without a result"
        try:
            result = self._task(self._cancel_event, self.progress.emit)
            error_text = None
        except Exception as error:
            error_text = str(error) or type(error).__name__
        finally:
            self.finished.emit(result, error_text)


def start_task(task, on_finished, on_progress=None, cancel_signal=None, parent=None):
    """Run task(cancel_event, report_progress) on a background thread.

    The task returns any value, or raises. report_progress(index, total, text)
    emits on_progress. When the task ends, on_finished(result, error_text) runs
    on the thread that called start_task. error_text is None on success; on
    an exception, result is None and error_text is the error's text.

    The thread is parented to `parent` (which must outlive the task) and
    deletes itself and the worker once done, so callers may drop the returned
    (thread, worker) references at any time — e.g. when a dialog closes
    mid-task.
    """
    thread = QThread(parent)
    worker = _TaskWorker(task)
    worker.moveToThread(thread)
    thread._worker = worker  # keep the worker alive for the thread's lifetime

    thread.started.connect(worker.run)
    if on_progress is not None:
        worker.progress.connect(on_progress)
    worker.finished.connect(on_finished)
    worker.finished.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    if cancel_signal is not None:
        # The worker thread sits in run() with no event loop, so a queued call
        # would arrive only after the task ends. A direct call is safe because
        # cancel() only sets a threading.Event.
        cancel_signal.connect(worker.cancel, type=Qt.ConnectionType.DirectConnection)

    thread.start()
    return thread, worker
