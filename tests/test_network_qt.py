import http.client
import importlib.util
import sys
import time
import types
from pathlib import Path

import pytest

QtCore = pytest.importorskip("PyQt6.QtCore")

NETWORK_PATH = Path(__file__).resolve().parents[1] / "plugin" / "network.py"
MODULE_NAME = "blog_rating_sync_network_qt"
URLS = [
    "https://example.com/first",
    "https://example.com/second",
    "https://example.com/third",
]


class _CancelSource(QtCore.QObject):
    canceled = QtCore.pyqtSignal()


def _fake_fetch(url):
    return f"<html>{url}</html>"


def _slow_fetch(url):
    time.sleep(0.05)
    return _fake_fetch(url)


@pytest.fixture(scope="session")
def qt_app():
    app = QtCore.QCoreApplication.instance()
    if app is None:
        app = QtCore.QCoreApplication([])
    return app


@pytest.fixture
def qt_network(monkeypatch):
    """Load a fresh copy of plugin/network.py that binds to PyQt6 instead of the stubs."""
    qt_core = types.ModuleType("qt.core")
    for name in ("QObject", "QThread", "Qt", "pyqtSignal"):
        setattr(qt_core, name, getattr(QtCore, name))
    monkeypatch.setitem(sys.modules, "qt.core", qt_core)
    spec = importlib.util.spec_from_file_location(MODULE_NAME, NETWORK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_until(app, predicate, timeout=5.0):
    """Pump Qt events until predicate() is true; fail the test on timeout."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail("timed out waiting for the fetch thread")
        app.processEvents()
        time.sleep(0.005)


def join_thread(app, thread, timeout=5.0):
    """Wait until the QThread exits, pumping events between short waits.

    The worker's finished signal queues thread.quit to this thread, so a
    blocking wait would never deliver it. deleteLater removes the QThread
    after it finishes; a deleted wrapper counts as finished.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            if thread.wait(10):
                return
        except RuntimeError as error:
            if "has been deleted" in str(error):
                return
            raise
        if time.monotonic() > deadline:
            thread.quit()
            pytest.fail("fetch thread did not exit")
        app.processEvents()


def _fetch_task(network_module, urls):
    """Return a start_task task that runs fetch_all over urls on the worker thread."""

    def task(cancel_event, report_progress):
        return network_module.fetch_all(
            urls, cancel_event=cancel_event, on_progress=report_progress
        )

    return task


def test_results_reach_on_finished_on_the_main_thread(qt_app, qt_network, monkeypatch):
    monkeypatch.setattr(qt_network, "fetch_page", _fake_fetch)
    monkeypatch.setattr(qt_network, "REQUEST_DELAY_SECONDS", 0.01)
    finished = []

    def on_finished(result, error_text):
        on_main_thread = QtCore.QThread.currentThread() == qt_app.thread()
        finished.append((result, error_text, on_main_thread))

    thread, _worker = qt_network.start_task(_fetch_task(qt_network, URLS), on_finished)
    try:
        wait_until(qt_app, lambda: bool(finished))
    finally:
        join_thread(qt_app, thread)

    assert len(finished) == 1
    result, error_text, on_main_thread = finished[0]
    results, was_cancelled = result
    assert error_text is None
    assert on_main_thread is True
    assert results == [(url, _fake_fetch(url), None) for url in URLS]
    assert was_cancelled is False


def test_cancel_signal_stops_fetch_early(qt_app, qt_network, monkeypatch):
    monkeypatch.setattr(qt_network, "fetch_page", _slow_fetch)
    monkeypatch.setattr(qt_network, "REQUEST_DELAY_SECONDS", 0.01)
    urls = [f"https://example.com/{number}" for number in range(10)]
    cancel_source = _CancelSource()
    progress = []
    finished = []
    thread, _worker = qt_network.start_task(
        _fetch_task(qt_network, urls),
        lambda result, error_text: finished.append((result, error_text)),
        on_progress=lambda index, total, url: progress.append(index),
        cancel_signal=cancel_source.canceled,
    )
    try:
        wait_until(qt_app, lambda: bool(progress))
        cancel_source.canceled.emit()
        wait_until(qt_app, lambda: bool(finished))
    finally:
        join_thread(qt_app, thread)

    assert len(finished) == 1
    result, error_text = finished[0]
    results, was_cancelled = result
    assert error_text is None
    assert len(results) < len(urls)
    assert was_cancelled is True


def test_bad_status_line_still_finishes(qt_app, qt_network, monkeypatch):
    def fetch(url):
        if url == URLS[1]:
            raise http.client.BadStatusLine("garbage")
        return _fake_fetch(url)

    monkeypatch.setattr(qt_network, "fetch_page", fetch)
    monkeypatch.setattr(qt_network, "REQUEST_DELAY_SECONDS", 0.01)
    finished = []
    thread, _worker = qt_network.start_task(
        _fetch_task(qt_network, URLS),
        lambda result, error_text: finished.append((result, error_text)),
    )
    try:
        wait_until(qt_app, lambda: bool(finished))
    finally:
        join_thread(qt_app, thread)

    assert len(finished) == 1
    result, error_text = finished[0]
    results, was_cancelled = result
    assert error_text is None
    assert results == [
        (URLS[0], _fake_fetch(URLS[0]), None),
        (URLS[1], None, "garbage"),
        (URLS[2], _fake_fetch(URLS[2]), None),
    ]
    assert was_cancelled is False


def test_start_task_runs_off_main_thread_and_finishes_on_main_thread(qt_app, qt_network):
    task_threads = []
    finished = []

    def task(cancel_event, report_progress):
        task_threads.append(QtCore.QThread.currentThread())
        return "value"

    def on_finished(result, error_text):
        finished.append((QtCore.QThread.currentThread(), result, error_text))

    thread, _worker = qt_network.start_task(task, on_finished)
    try:
        wait_until(qt_app, lambda: bool(finished))
    finally:
        join_thread(qt_app, thread)

    main_thread = qt_app.thread()
    assert len(task_threads) == 1
    assert task_threads[0] != main_thread
    assert finished == [(main_thread, "value", None)]
