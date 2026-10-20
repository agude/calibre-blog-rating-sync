import pytest
from calibre_plugins.blog_rating_sync.network import start_task
from qt.core import QObject, Qt, pyqtSignal


class _CancelSource(QObject):
    canceled = pyqtSignal()


class _Abort(BaseException):
    """Stands in for a BaseException that the task does not handle."""


def test_start_task_delivers_result():
    finished = []

    start_task(
        lambda cancel_event, report_progress: 42,
        lambda result, error_text: finished.append((result, error_text)),
    )

    assert finished == [(42, None)]


def test_start_task_reports_exception_text():
    finished = []

    def failing_task(cancel_event, report_progress):
        raise ValueError("bad input")

    def silent_task(cancel_event, report_progress):
        raise ValueError()

    start_task(failing_task, lambda result, error_text: finished.append((result, error_text)))
    start_task(silent_task, lambda result, error_text: finished.append((result, error_text)))

    assert finished == [(None, "bad input"), (None, "ValueError")]


def test_start_task_reports_base_exception_as_error():
    finished = []

    def aborting_task(cancel_event, report_progress):
        raise _Abort()

    def on_finished(result, error_text):
        finished.append((result, error_text))

    with pytest.raises(_Abort):
        start_task(aborting_task, on_finished)

    assert len(finished) == 1
    result, error_text = finished[0]
    assert result is None
    assert error_text is not None


def test_start_task_forwards_progress():
    progress = []

    def task(cancel_event, report_progress):
        report_progress(0, 2, "first")
        report_progress(1, 2, "second")

    start_task(
        task,
        lambda result, error_text: None,
        on_progress=lambda *args: progress.append(args),
    )

    assert progress == [(0, 2, "first"), (1, 2, "second")]


def test_start_task_connects_cancel_directly():
    cancel_source = _CancelSource()

    _thread, worker = start_task(
        lambda cancel_event, report_progress: None,
        lambda result, error_text: None,
        cancel_signal=cancel_source.canceled,
    )

    assert cancel_source.canceled.connections == [
        (worker.cancel, Qt.ConnectionType.DirectConnection)
    ]


def test_start_task_cancel_sets_event():
    cancel_source = _CancelSource()
    received_events = []

    def task(cancel_event, report_progress):
        received_events.append(cancel_event)

    _thread, worker = start_task(
        task,
        lambda result, error_text: None,
        cancel_signal=cancel_source.canceled,
    )
    cancel_source.canceled.emit()

    assert worker._cancel_event.is_set()
    assert received_events == [worker._cancel_event]
