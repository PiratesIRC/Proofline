"""The exe icon must be a multi-size .ico with the sizes the Windows shell asks for."""

from __future__ import annotations

import importlib.util
import itertools
import struct
from pathlib import Path
from types import ModuleType

from PyQt6.QtGui import QImage

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "packaging" / "make_icon.py"
EXPECTED_SIZES = [16, 20, 24, 32, 40, 48, 64, 256]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ICO_HEADER = "<HHH"
ICO_ENTRY = "<BBBBHHII"
ENTRY_BYTES = struct.calcsize(ICO_ENTRY)
DIB_HEADER_BYTES = 40


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_icon", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_icon(qapp, tmp_path: Path) -> Path:
    path = tmp_path / "app.ico"
    assert _load_script().main(path) == 0
    return path


def _parse_entries(data: bytes) -> list[tuple[int, int, int, int, int]]:
    """Return (width, height, bit count, size, offset) for each ICONDIRENTRY."""
    _reserved, _kind, count = struct.unpack_from(ICO_HEADER, data, 0)
    entries = []
    for index in range(count):
        width, height, _colours, _res, _planes, bits, size, offset = struct.unpack_from(
            ICO_ENTRY, data, struct.calcsize(ICO_HEADER) + index * ENTRY_BYTES
        )
        entries.append((width or 256, height or 256, bits, size, offset))
    return entries


def test_ico_header_and_sizes(qapp, tmp_path: Path) -> None:
    data = _write_icon(qapp, tmp_path).read_bytes()
    reserved, kind, _count = struct.unpack_from(ICO_HEADER, data, 0)
    assert reserved == 0
    assert kind == 1
    entries = _parse_entries(data)
    assert [width for width, *_ in entries] == EXPECTED_SIZES
    assert [height for _w, height, *_ in entries] == EXPECTED_SIZES
    assert all(bits == 32 for _w, _h, bits, _size, _offset in entries)


def test_blocks_lie_inside_file_without_overlap(qapp, tmp_path: Path) -> None:
    data = _write_icon(qapp, tmp_path).read_bytes()
    spans = sorted((offset, offset + size) for _w, _h, _b, size, offset in _parse_entries(data))
    for start, end in spans:
        assert start >= 0
        assert end <= len(data)
    for (_start1, end1), (start2, _end2) in itertools.pairwise(spans):
        assert end1 <= start2


def test_block_payloads_are_png_and_dib(qapp, tmp_path: Path) -> None:
    data = _write_icon(qapp, tmp_path).read_bytes()
    for width, height, _bits, _size, offset in _parse_entries(data):
        if width == 256:
            assert data[offset : offset + 8] == PNG_SIGNATURE
            continue
        header_size = struct.unpack_from("<I", data, offset)[0]
        header_width, header_height = struct.unpack_from("<ii", data, offset + 4)
        assert header_size == DIB_HEADER_BYTES
        assert header_width == width
        assert header_height == 2 * height


def test_written_file_loads_as_image(qapp, tmp_path: Path) -> None:
    path = _write_icon(qapp, tmp_path)
    assert not QImage(str(path)).isNull()
