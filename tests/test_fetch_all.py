import http.client
import threading

import pytest
from calibre_plugins.blog_rating_sync import network
from calibre_plugins.blog_rating_sync.network import BatchFetchWorker, fetch_all

URLS = [
    "https://example.com/first",
    "https://example.com/second",
    "https://example.com/third",
]


def _fake_fetch(url):
    return f"<html>{url}</html>"


def _recording_fetch(fetched):
    def fetch(url):
        fetched.append(url)
        return _fake_fetch(url)

    return fetch


class RecordingEvent:
    """A cancel event that never sets and records each wait instead of sleeping."""

    def __init__(self):
        self.waits = []

    def is_set(self):
        return False

    def wait(self, timeout):
        self.waits.append(timeout)
        return False


def test_fetch_all_returns_results_in_order():
    results, was_cancelled = fetch_all(URLS, fetch=_fake_fetch, delay_seconds=0)

    assert results == [(url, _fake_fetch(url), None) for url in URLS]
    assert was_cancelled is False


def test_fetch_all_continues_after_bad_status_line():
    def fetch(url):
        if url == URLS[1]:
            raise http.client.BadStatusLine("garbage")
        return _fake_fetch(url)

    results, was_cancelled = fetch_all(URLS, fetch=fetch, delay_seconds=0)

    assert results == [
        (URLS[0], _fake_fetch(URLS[0]), None),
        (URLS[1], None, "garbage"),
        (URLS[2], _fake_fetch(URLS[2]), None),
    ]
    assert was_cancelled is False


def test_fetch_all_error_text_falls_back_to_class_name():
    def fetch(url):
        raise ValueError()

    results, _ = fetch_all(URLS[:1], fetch=fetch, delay_seconds=0)

    assert results == [(URLS[0], None, "ValueError")]


def test_fetch_all_cancel_before_start_fetches_nothing():
    fetched = []
    cancel_event = threading.Event()
    cancel_event.set()

    results, was_cancelled = fetch_all(
        URLS,
        fetch=_recording_fetch(fetched),
        cancel_event=cancel_event,
        delay_seconds=0,
    )

    assert results == []
    assert fetched == []
    assert was_cancelled is True


def test_fetch_all_cancel_during_progress_stops_early():
    urls = [f"https://example.com/{number}" for number in range(10)]
    fetched = []
    cancel_event = threading.Event()

    def on_progress(index, total, url):
        if index == 1:
            cancel_event.set()

    results, was_cancelled = fetch_all(
        urls,
        fetch=_recording_fetch(fetched),
        cancel_event=cancel_event,
        on_progress=on_progress,
        delay_seconds=0,
    )

    assert fetched == urls[:2]
    assert len(results) == 2
    assert was_cancelled is True


def test_fetch_all_waits_between_urls_only():
    event = RecordingEvent()

    results, was_cancelled = fetch_all(
        URLS,
        fetch=_fake_fetch,
        cancel_event=event,
        delay_seconds=0.25,
    )

    assert len(results) == len(URLS)
    assert event.waits == [0.25] * (len(URLS) - 1)
    assert was_cancelled is False


def test_batch_worker_emits_finished_once_on_success(monkeypatch):
    monkeypatch.setattr(network, "fetch_page", _fake_fetch)
    monkeypatch.setattr(network, "REQUEST_DELAY_SECONDS", 0)
    worker = BatchFetchWorker(URLS)
    progress = []
    finished = []
    worker.progress.connect(lambda *args: progress.append(args))
    worker.finished.connect(
        lambda results, was_cancelled: finished.append((results, was_cancelled))
    )

    worker.run()

    assert progress == [(index, len(URLS), url) for index, url in enumerate(URLS)]
    assert finished == [([(url, _fake_fetch(url), None) for url in URLS], False)]


def test_batch_worker_emits_finished_once_when_fetch_all_raises(monkeypatch):
    def broken_fetch_all(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(network, "fetch_all", broken_fetch_all)
    worker = BatchFetchWorker(URLS)
    finished = []
    worker.finished.connect(
        lambda results, was_cancelled: finished.append((results, was_cancelled))
    )

    with pytest.raises(RuntimeError, match="boom"):
        worker.run()

    assert finished == [([], False)]
