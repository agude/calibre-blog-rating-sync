import time
from urllib.error import URLError
from urllib.request import urlopen

from qt.core import QObject, QThread, pyqtSignal

FETCH_TIMEOUT_SECONDS = 10
REQUEST_DELAY_SECONDS = 0.1


def fetch_page(url):
    return urlopen(url, timeout=FETCH_TIMEOUT_SECONDS).read().decode("utf-8")


class BatchFetchWorker(QObject):
    """Fetches a list of URLs on a background thread."""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list)

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
            except (URLError, OSError) as error:
                results.append((url, None, str(error)))
            if index < total - 1:
                time.sleep(REQUEST_DELAY_SECONDS)
        self.finished.emit(results)


def start_batch_fetch(urls, on_progress, on_finished):
    """Start fetching URLs on a background thread.

    Returns (thread, worker) — caller must keep references alive.
    """
    thread = QThread()
    worker = BatchFetchWorker(urls)
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.progress.connect(on_progress)
    worker.finished.connect(on_finished)
    worker.finished.connect(thread.quit)

    thread.start()
    return thread, worker
