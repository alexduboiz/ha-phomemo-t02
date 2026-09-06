"""Phomemo T02 wire protocol.

Pure functions: PIL image in, bytes out. No I/O, no Home Assistant imports, so
this module is fully unit-testable without hardware. Every byte sequence here was
verified against a physical T02 -- see docs/protocol.md.
"""

from __future__ import annotations

from PIL import Image, ImageChops

from .const import (
    BYTES_PER_LINE,
    DOTS_PER_LINE,
    DOTS_PER_MM,
    JUSTIFY_LEFT,
    MAX_LINES_PER_BLOCK,
)

CMD_INIT = bytes([0x1B, 0x40])
CMD_RASTER_HDR = bytes([0x1D, 0x76, 0x30, 0x00])


def cmd_justify(mode: int = JUSTIFY_LEFT) -> bytes:
    """ESC a n -- 0 left, 1 centre, 2 right."""
    return bytes([0x1B, 0x61, mode])


def cmd_feed(lines: int) -> bytes:
    """ESC d n -- advance n lines."""
    return bytes([0x1B, 0x64, max(0, min(255, lines))])


def to_bilevel(img: Image.Image, dither: bool = False) -> Image.Image:
    """Convert any image to mode "1" at the printer's exact width.

    imagespec returns RGB, so this is always needed before packing.
    """
    if img.mode != "1":
        img = img.convert("L").convert(
            "1", dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
        )
    if img.width != DOTS_PER_LINE:
        raise ValueError(f"image must be {DOTS_PER_LINE}px wide, got {img.width}")
    return img


def crop_to_content(img: Image.Image, margin: int = 8) -> Image.Image:
    """Trim trailing blank paper, keeping full width and a small bottom margin.

    Height is rounded up to a multiple of 8 so line counts stay tidy. Returns a
    minimum-height image rather than None when the label is entirely blank.
    """
    # getbbox() locates non-zero pixels; in mode "1" black is 0, so invert first.
    bbox = ImageChops.invert(img.convert("L")).getbbox()
    if bbox is None:
        return img.crop((0, 0, DOTS_PER_LINE, 8))
    height = min(img.height, bbox[3] + margin)
    height += (-height) % 8
    return img.crop((0, 0, DOTS_PER_LINE, max(8, height)))


def pack_image(img: Image.Image) -> bytes:
    """Pack a mode "1" image MSB-first, 8 px per byte. A set bit burns (black)."""
    pixels = img.load()
    out = bytearray()
    for y in range(img.height):
        for byte_x in range(BYTES_PER_LINE):
            byte = 0
            base = byte_x * 8
            for bit in range(8):
                # PIL mode "1": 0 == black. Printer: set bit == burn == black.
                if pixels[base + bit, y] == 0:
                    byte |= 0x80 >> bit
            out.append(byte)
    return bytes(out)


def encode_job(
    img: Image.Image,
    *,
    feed_lines: int = 3,
    dither: bool = False,
) -> bytes:
    """Encode one complete print job.

    Splits the raster into <=255-line blocks, as the T02 requires.
    """
    img = to_bilevel(img, dither=dither)
    data = pack_image(img)

    stream = bytearray()
    stream += CMD_INIT
    stream += cmd_justify(JUSTIFY_LEFT)

    for start in range(0, img.height, MAX_LINES_PER_BLOCK):
        lines = min(MAX_LINES_PER_BLOCK, img.height - start)
        stream += CMD_RASTER_HDR
        stream += bytes(
            [
                BYTES_PER_LINE & 0xFF,
                BYTES_PER_LINE >> 8,
                lines & 0xFF,
                lines >> 8,
            ]
        )
        stream += data[start * BYTES_PER_LINE : (start + lines) * BYTES_PER_LINE]

    stream += cmd_feed(feed_lines)
    return bytes(stream)


def paper_mm(height_px: int) -> float:
    """Millimetres of paper a label of this pixel height consumes."""
    return height_px / DOTS_PER_MM
