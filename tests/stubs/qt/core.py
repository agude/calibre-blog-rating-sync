"""Stand-ins for the PyQt names that Calibre exposes as qt.core.

Signals call their slots synchronously, and a QThread runs its work on the
calling thread, so tests see a fixed order of events.
"""

from enum import IntEnum


class _BoundSignal:
    """The signal of one instance: its connected slots, in connection order."""

    def __init__(self):
        self.connections = []

    def connect(self, slot, type=None):
        self.connections.append((slot, type))

    def disconnect(self, slot=None):
        if slot is None:
            self.connections = []
        else:
            self.connections = [(s, t) for s, t in self.connections if s != slot]

    def emit(self, *args):
        for slot, _ in list(self.connections):
            slot(*args)


class pyqtSignal:
    """Class-level signal declaration. Argument types are recorded but not checked."""

    def __init__(self, *types):
        self.types = types
        self._attribute = None

    def __set_name__(self, owner, name):
        self._attribute = "_signal_" + name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        bound = instance.__dict__.get(self._attribute)
        if bound is None:
            bound = _BoundSignal()
            instance.__dict__[self._attribute] = bound
        return bound


class Qt:
    """Enum namespaces with the same nested access that PyQt6 uses."""

    class ItemDataRole(IntEnum):
        DisplayRole = 0
        EditRole = 2
        UserRole = 256

    class Orientation(IntEnum):
        Horizontal = 1
        Vertical = 2

    class ItemFlag(IntEnum):
        NoItemFlags = 0
        ItemIsEditable = 2

    class WindowModality(IntEnum):
        WindowModal = 1

    class ConnectionType(IntEnum):
        AutoConnection = 0
        DirectConnection = 1
        QueuedConnection = 2


class QObject:
    def __init__(self, parent=None):
        self._parent = parent

    def parent(self):
        return self._parent

    def moveToThread(self, thread):
        """Does nothing: stub objects stay on the calling thread."""

    def deleteLater(self):
        """Does nothing: stub objects are released by normal garbage collection."""


class QThread(QObject):
    started = pyqtSignal()
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_finished = False

    def start(self):
        self.started.emit()
        self.run()
        self._is_finished = True
        self.finished.emit()

    def run(self):
        """Override to do the thread's work. Does nothing by default."""

    def quit(self, *args):
        """Does nothing. Accepts signal arguments, because Qt drops extra arguments for slots."""

    def wait(self, *args):
        return True

    def isFinished(self):
        return self._is_finished


class _ModelIndex:
    """A (row, column) position within one model."""

    def __init__(self, model, row, column):
        self._model = model
        self._row = row
        self._column = column

    def row(self):
        return self._row

    def column(self):
        return self._column

    def model(self):
        return self._model

    def data(self, role=Qt.ItemDataRole.DisplayRole):
        return self._model.data(self, role)


class QAbstractTableModel(QObject):
    dataChanged = pyqtSignal(object, object)

    def index(self, row, column):
        return _ModelIndex(self, row, column)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        return None

    def flags(self, index):
        return Qt.ItemFlag.NoItemFlags


class QStyledItemDelegate(QObject):
    pass


class _Placeholder:
    """Widget stand-in. Constructor arguments are accepted and ignored."""

    def __init__(self, *args, **kwargs):
        """Accept and ignore any constructor arguments."""


class QComboBox(_Placeholder):
    pass


class QDialog(_Placeholder):
    pass


class QHBoxLayout(_Placeholder):
    pass


class QLabel(_Placeholder):
    pass


class QLineEdit(_Placeholder):
    pass


class QMenu(_Placeholder):
    pass


class QMessageBox(_Placeholder):
    pass


class QProgressDialog(_Placeholder):
    pass


class QPushButton(_Placeholder):
    pass


class QTableView(_Placeholder):
    pass


class QVBoxLayout(_Placeholder):
    pass


class QWidget(_Placeholder):
    pass
