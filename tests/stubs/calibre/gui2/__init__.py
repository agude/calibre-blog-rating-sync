from typing import List, Tuple

calls: List[Tuple[str, tuple, dict]] = []


def error_dialog(*args, **kwargs):
    calls.append(("error_dialog", args, kwargs))


def info_dialog(*args, **kwargs):
    calls.append(("info_dialog", args, kwargs))
