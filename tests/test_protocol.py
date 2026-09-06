"""Golden-byte tests for the T02 encoder.

The expected header in `test_matches_verified_hardware_stream` is the exact byte
sequence that produced a correct label on real hardware -- see docs/protocol.md.
"""

from __future__ import annotations

import pytest
from conftest import load
from PIL import Image

protocol = load("protocol")
const = load("const")


def blank(height: int, colour: int = 1) -> Image.Image:
    """Mode "1" canvas. colour=1 is white, 0 is black."""
    return Image.new("1", (const.DOTS_PER_LINE, height), colour)


# --- bit packing ----------------------------------------------------------
def test_all_black_sets_every_bit():
    packed = protocol.pack_image(blank(1, colour=0))
    assert packed == b"\xff" * const.BYTES_PER_LINE


def test_all_white_clears_every_bit():
    packed = protocol.pack_image(blank(1, colour=1))
    assert packed == b"\x00" * const.BYTES_PER_LINE


def test_packing_is_msb_first():
    """A single black pixel at x=0 must set the most significant bit."""
    img = blank(1)
    img.putpixel((0, 0), 0)
    assert protocol.pack_image(img)[0] == 0x80

    img = blank(1)
    img.putpixel((7, 0), 0)
    assert protocol.pack_image(img)[0] == 0x01


def test_packed_length_is_lines_times_bytes_per_line():
    assert len(protocol.pack_image(blank(10))) == 10 * const.BYTES_PER_LINE


# --- width guard ----------------------------------------------------------
def test_wrong_width_is_rejected():
    with pytest.raises(ValueError, match="384px wide"):
        protocol.to_bilevel(Image.new("1", (200, 8), 1))


# --- job encoding ---------------------------------------------------------
def test_matches_verified_hardware_stream():
    """Header bytes observed in the successful 240px hardware print."""
    stream = protocol.encode_job(blank(240), feed_lines=3)
    assert stream[:12] == bytes(
        [
            0x1B, 0x40,              # init
            0x1B, 0x61, 0x00,        # justify left
            0x1D, 0x76, 0x30, 0x00,  # raster block
            0x30, 0x00,              # 48 bytes per line, little-endian
            0xF0,                    # 240 lines, low byte
        ]
    )
    assert stream[12] == 0x00  # 240 lines, high byte
    assert stream[-3:] == bytes([0x1B, 0x64, 0x03])  # trailing feed


def test_short_image_is_a_single_block():
    stream = protocol.encode_job(blank(100))
    assert stream.count(protocol.CMD_RASTER_HDR) == 1


def test_tall_image_splits_at_255_lines():
    """300 lines must become two blocks of 255 and 45."""
    stream = protocol.encode_job(blank(300))
    assert stream.count(protocol.CMD_RASTER_HDR) == 2

    first = stream.index(protocol.CMD_RASTER_HDR)
    assert stream[first + 6] == 255
    second = stream.index(protocol.CMD_RASTER_HDR, first + 1)
    assert stream[second + 6] == 45


def test_exactly_255_lines_stays_one_block():
    stream = protocol.encode_job(blank(255))
    assert stream.count(protocol.CMD_RASTER_HDR) == 1


def test_payload_size_accounts_for_every_line():
    height = 300
    stream = protocol.encode_job(blank(height))
    raster = height * const.BYTES_PER_LINE
    overhead = 2 + 3 + (2 * 8) + 3  # init + justify + two block headers + feed
    assert len(stream) == raster + overhead


# --- commands -------------------------------------------------------------
def test_feed_is_clamped_to_a_byte():
    assert protocol.cmd_feed(300) == bytes([0x1B, 0x64, 255])
    assert protocol.cmd_feed(-5) == bytes([0x1B, 0x64, 0])


def test_justify_modes():
    assert protocol.cmd_justify(1) == bytes([0x1B, 0x61, 0x01])


# --- cropping -------------------------------------------------------------
def test_crop_trims_trailing_blank_paper():
    img = blank(800)
    for x in range(50):
        img.putpixel((x, 20), 0)
    cropped = protocol.crop_to_content(img, margin=8)
    assert cropped.height < 800
    assert cropped.width == const.DOTS_PER_LINE
    assert cropped.height % 8 == 0


def test_crop_of_blank_image_does_not_crash():
    assert protocol.crop_to_content(blank(400)).height == 8


def test_crop_keeps_all_content():
    img = blank(600)
    for x in range(384):
        img.putpixel((x, 300), 0)
    cropped = protocol.crop_to_content(img)
    assert cropped.height > 300


# --- geometry -------------------------------------------------------------
def test_paper_mm():
    assert protocol.paper_mm(240) == 30.0
    assert protocol.paper_mm(8) == 1.0
