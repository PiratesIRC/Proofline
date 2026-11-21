"""Write the exe icon (the tray's P badge) as a multi-size .ico for PyInstaller.

The file holds one image per size in ICO_SIZES. The 256 px image is stored as PNG, every
smaller image as a 32-bit DIB with an AND mask, which is what the ICO format expects.

Usage: python packaging/make_icon.py <output.ico>
"""

from __future__ import annotations

import logging
import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QGuiApplication, QImage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from proofline.tray import ACTIVE_COLOR, make_icon

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
PNG_SIZE = 256  # the only size stored as PNG; ICO_SIZES[-1] must be this
ICO_TYPE_ICON = 1
ICO_HEADER_FORMAT = "<HHH"  # reserved, type, count
ICO_ENTRY_FORMAT = "<BBBBHHII"  # width, height, colours, reserved, planes, bits, size, offset
ICO_DIB_HEADER_FORMAT = "<IiiHHIIiiII"  # BITMAPINFOHEADER
DIB_HEADER_BYTES = 40
DIB_PLANES = 1
BITS_PER_PIXEL = 32
BYTES_PER_PIXEL = 4
MASK_ROW_ALIGN_BITS = 32  # AND mask rows are padded to 4 bytes
ICO_DIM_FOR_256 = 0  # the ICO entry stores a 256 px dimension as 0

log = logging.getLogger(__name__)


def _render(size: int) -> QImage:
    """Render the badge at size x size as ARGB32, scaling if Qt returned another size."""
    pixmap = make_icon(ACTIVE_COLOR).pixmap(size, size)
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    if image.width() != size or image.height() != size:
        image = image.scaled(
            size,
            size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return image


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _dib_bytes(image: QImage) -> bytes:
    """Return a BITMAPINFOHEADER, the bottom-up BGRA pixels and a zero AND mask."""
    width = image.width()
    height = image.height()
    header = struct.pack(
        ICO_DIB_HEADER_FORMAT,
        DIB_HEADER_BYTES,
        width,
        height * 2,  # the XOR and AND masks share one height in an ICO DIB
        DIB_PLANES,
        BITS_PER_PIXEL,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    pixel_rows = [
        bytes(image.constScanLine(y).asstring(width * BYTES_PER_PIXEL))
        for y in reversed(range(height))
    ]
    mask_row_bytes = (width + MASK_ROW_ALIGN_BITS - 1) // MASK_ROW_ALIGN_BITS * 4
    mask = bytes(mask_row_bytes * height)
    return header + b"".join(pixel_rows) + mask


def _image_block(image: QImage) -> bytes:
    if image.width() == PNG_SIZE:
        return _png_bytes(image)
    return _dib_bytes(image)


def _dim_byte(dimension: int) -> int:
    return ICO_DIM_FOR_256 if dimension == PNG_SIZE else dimension


def build_ico(images: list[QImage]) -> bytes:
    """Return the bytes of an .ico file holding each square image in order."""
    blocks = [_image_block(image) for image in images]
    offset = struct.calcsize(ICO_HEADER_FORMAT) + struct.calcsize(ICO_ENTRY_FORMAT) * len(images)
    entries = []
    for image, block in zip(images, blocks):
        entries.append(
            struct.pack(
                ICO_ENTRY_FORMAT,
                _dim_byte(image.width()),
                _dim_byte(image.height()),
                0,  # colour count: 0 for 256 or more colours
                0,  # reserved
                DIB_PLANES,
                BITS_PER_PIXEL,
                len(block),
                offset,
            )
        )
        offset += len(block)
    header = struct.pack(ICO_HEADER_FORMAT, 0, ICO_TYPE_ICON, len(images))
    return header + b"".join(entries) + b"".join(blocks)


def main(output: Path) -> int:
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = build_ico([_render(size) for size in ICO_SIZES])
        output.write_bytes(data)
    except OSError:
        log.error("Could not write %s", output)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 2:
        log.error("Usage: python packaging/make_icon.py <output.ico>")
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
