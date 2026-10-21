from calibre.utils.config import JSONConfig
from qt.core import QAbstractTableModel, Qt, QThread, pyqtSignal


class _Emitter:
    changed = pyqtSignal(int)


def test_signal_calls_slots_in_connection_order():
    emitter = _Emitter()
    calls = []
    emitter.changed.connect(lambda value: calls.append(("first", value)))
    emitter.changed.connect(lambda value: calls.append(("second", value)))

    emitter.changed.emit(5)

    assert calls == [("first", 5), ("second", 5)]


def test_signals_are_independent_per_instance():
    first = _Emitter()
    second = _Emitter()
    received = []
    first.changed.connect(received.append)

    second.changed.emit(7)
    assert received == []

    first.changed.emit(3)
    assert received == [3]


def test_signal_records_connection_type():
    emitter = _Emitter()
    received = []
    emitter.changed.connect(received.append, Qt.ConnectionType.QueuedConnection)

    assert emitter.changed.connections == [(received.append, Qt.ConnectionType.QueuedConnection)]


def test_qthread_start_runs_started_run_finished_in_order():
    events = []

    class RecordingThread(QThread):
        def run(self):
            events.append("run")

    thread = RecordingThread()
    thread.started.connect(lambda: events.append("started"))
    thread.finished.connect(lambda: events.append("finished"))

    thread.start()

    assert events == ["started", "run", "finished"]
    assert thread.isFinished()


def test_table_model_index_reports_row_and_column():
    model = QAbstractTableModel()

    index = model.index(3, 2)

    assert index.row() == 3
    assert index.column() == 2
    assert index.model() is model


def test_jsonconfig_falls_back_to_defaults():
    config = JSONConfig("plugins/test")
    config.defaults["colour"] = "blue"

    assert config["colour"] == "blue"

    config["colour"] = "red"
    assert config["colour"] == "red"
