"""Constants for the Phomemo T02 integration.

Protocol values here are measured against real hardware -- see docs/protocol.md.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "phomemo_t02"
MANUFACTURER: Final = "Phomemo"
MODEL: Final = "T02"

# --- BLE ------------------------------------------------------------------
SERVICE_UUID: Final = "0000ff00-0000-1000-8000-00805f9b34fb"
WRITE_UUID: Final = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID: Final = "0000ff03-0000-1000-8000-00805f9b34fb"

# The T02 advertises this local name but does NOT advertise its service UUID,
# so discovery has to match on the name. See docs/protocol.md.
LOCAL_NAME: Final = "T02"

# --- Geometry -------------------------------------------------------------
DOTS_PER_LINE: Final = 384
BYTES_PER_LINE: Final = DOTS_PER_LINE // 8  # 48
DOTS_PER_MM: Final = 8
MAX_LINES_PER_BLOCK: Final = 255

# Tall scratch canvas the composer draws into before cropping to content.
MAX_LABEL_HEIGHT: Final = 1600

# --- Options --------------------------------------------------------------
CONF_CHUNK_SIZE: Final = "chunk_size"
CONF_CHUNK_DELAY_MS: Final = "chunk_delay_ms"
CONF_IDLE_DISCONNECT_S: Final = "idle_disconnect_s"
CONF_FEED_LINES: Final = "feed_lines"

# Measured MTU on a local adapter was 200 (=197 payload). The effective chunk is
# always min(this, mtu - 3), so this is an upper bound, not an assumption.
DEFAULT_CHUNK_SIZE: Final = 197
DEFAULT_CHUNK_DELAY_MS: Final = 10
DEFAULT_IDLE_DISCONNECT_S: Final = 30
DEFAULT_FEED_LINES: Final = 3

# --- Composer -------------------------------------------------------------
ATTR_PAYLOAD: Final = "payload"
ATTR_TEXT: Final = "text"
ATTR_DATA: Final = "data"
ATTR_SIZE: Final = "size"
ATTR_ALIGN: Final = "align"
ATTR_CAPTION: Final = "caption"
ATTR_COPIES: Final = "copies"
ATTR_LINES: Final = "lines"
ATTR_HEIGHT: Final = "height"
ATTR_DITHER: Final = "dither"

SERVICE_PRINT: Final = "print"
SERVICE_PRINT_TEXT: Final = "print_text"
SERVICE_PRINT_QR: Final = "print_qr"
SERVICE_FEED: Final = "feed"

# Friendly size names -> pixel font size.
FONT_SIZES: Final[dict[str, int]] = {
    "Small": 24,
    "Medium": 32,
    "Large": 48,
    "Extra large": 64,
}
DEFAULT_FONT_SIZE: Final = "Large"

ALIGNMENTS: Final[list[str]] = ["left", "center", "right"]
DEFAULT_ALIGN: Final = "center"

# Justification passed to the printer itself is always left; the bitmap is
# already composed at full width, so alignment happens during rendering.
JUSTIFY_LEFT: Final = 0

MAX_TEXT_LENGTH: Final = 255
