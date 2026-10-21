import struct
from pathlib import Path

ICON_PATH = Path(__file__).resolve().parents[1] / "plugin" / "images" / "icon.png"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_icon_is_a_128px_png():
    data = ICON_PATH.read_bytes()

    assert data[:8] == PNG_SIGNATURE
    assert data[12:16] == b"IHDR"
    assert struct.unpack(">II", data[16:24]) == (128, 128)
