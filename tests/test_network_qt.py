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


def test_results_reach_on_finished_on_the_main_thread(qt_app, qt_network, monkeypatch):
    monkeypatch.setattr(qt_network, "fetch_page", _fake_fetch)
    monkeypatch.setattr(qt_network, "REQUEST_DELAY_SECONDS", 0.01)
    finished = []

    def on_finished(results, was_cancelled):
        on_main_thread = QtCore.QThread.currentThread() == qt_app.thread()
        finished.append((results, was_cancelled, on_main_thread))

    thread, _worker = qt_network.start_batch_fetch(URLS, lambda *args: None, on_finished)
    try:
        wait_until(qt_app, lambda: bool(finished))
    finally:
        join_thread(qt_app, thread)

    assert finished == [([(url, _fake_fetch(url), None) for url in URLS], False, True)]


def test_cancel_signal_stops_fetch_early(qt_app, qt_network, monkeypatch):
    monkeypatch.setattr(qt_network, "fetch_page", _slow_fetch)
    monkeypatch.setattr(qt_network, "REQUEST_DELAY_SECONDS", 0.01)
    urls = [f"https://example.com/{number}" for number in range(10)]
    cancel_source = _CancelSource()
    progress = []
    finished = []
    thread, _worker = qt_network.start_batch_fetch(
        urls,
        lambda index, total, url: progress.append(index),
        lambda results, was_cancelled: finished.append((results, was_cancelled)),
        cancel_signal=cancel_source.canceled,
    )
    try:
        wait_until(qt_app, lambda: bool(progress))
        cancel_source.canceled.emit()
        wait_until(qt_app, lambda: bool(finished))
    finally:
        join_thread(qt_app, thread)

    results, was_cancelled = finished[0]
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
    thread, _worker = qt_network.start_batch_fetch(
        URLS,
        lambda *args: None,
        lambda results, was_cancelled: finished.append((results, was_cancelled)),
    )
    try:
        wait_until(qt_app, lambda: bool(finished))
    finally:
        join_thread(qt_app, thread)

    assert finished == [
        (
            [
                (URLS[0], _fake_fetch(URLS[0]), None),
                (URLS[1], None, "garbage"),
                (URLS[2], _fake_fetch(URLS[2]), None),
            ],
            False,
        )
    ]
