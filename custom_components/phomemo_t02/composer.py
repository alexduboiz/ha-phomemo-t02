"""Label composition: GUI state -> imagespec payload -> bitmap + PNG preview.

The preview and the print job share this one render path. `render()` produces the
bitmap and the PNG together and both are cached, so pressing Print sends exactly
the bitmap that was previewed -- it cannot drift from what was on screen.

All rendering here is blocking CPU work (PIL), so callers must run it in an
executor rather than on the event loop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from io import BytesIO

import qrcode
from imagespec import RenderContext, render
from PIL import Image

from .const import (
    ALIGNMENTS,
    DEFAULT_ALIGN,
    DEFAULT_FONT_SIZE,
    DOTS_PER_LINE,
    FONT_SIZES,
    MAX_LABEL_HEIGHT,
)
from .protocol import crop_to_content, paper_mm, to_bilevel

_LOGGER = logging.getLogger(__name__)

MARGIN = 8
TEXT_WIDTH = DOTS_PER_LINE - 2 * MARGIN
QR_TARGET_PX = 200
QR_BORDER = 1
QR_GAP = 12
TEXT_BLOCK_HEIGHT = 420
MIN_FONT_SIZE = 12
MAX_LINES = 6
PREVIEW_SCALE = 2


@dataclass
class LabelState:
    """What the dashboard controls are currently set to."""

    text: str = ""
    qr: str = ""
    size: str = DEFAULT_FONT_SIZE
    align: str = DEFAULT_ALIGN
    copies: int = 1


@dataclass
class RenderedLabel:
    """One render, cached so preview and print stay identical."""

    bitmap: Image.Image
    png: bytes
    height_px: int
    paper_mm: float = field(default=0.0)


def qr_geometry(data: str, target_px: int = QR_TARGET_PX) -> tuple[int, int]:
    """Return (boxsize, pixel_size) for a QR centred at a predictable width.

    imagespec's `width`/`height` options only upscale by whole factors, so the
    rendered code can end up smaller than the box and sit off-centre. Computing
    the module count here lets us pass an exact `boxsize` and centre it properly.
    """
    qr = qrcode.QRCode(border=QR_BORDER, box_size=1)
    qr.add_data(data)
    qr.make(fit=True)
    modules = qr.modules_count + 2 * QR_BORDER
    boxsize = max(1, target_px // modules)
    return boxsize, modules * boxsize


def build_payload(state: LabelState) -> list[dict]:
    """Translate the GUI state into an imagespec payload."""
    payload: list[dict] = []
    y = MARGIN

    if state.qr:
        boxsize, size_px = qr_geometry(state.qr)
        payload.append(
            {
                "type": "qrcode",
                "data": state.qr,
                "x": (DOTS_PER_LINE - size_px) // 2,
                "y": y,
                "boxsize": boxsize,
                "border": QR_BORDER,
                "eclevel": "m",
            }
        )
        y += size_px + QR_GAP

    if state.text:
        align = state.align if state.align in ALIGNMENTS else DEFAULT_ALIGN
        payload.append(
            {
                # text_fit, never text_box: text_box draws a filled badge with
                # inverted text, which a thermal printer renders as a black slab.
                "type": "text_fit",
                "value": state.text,
                "x": MARGIN,
                "y": y,
                "width": TEXT_WIDTH,
                "height": TEXT_BLOCK_HEIGHT,
                "size": FONT_SIZES.get(state.size, FONT_SIZES[DEFAULT_FONT_SIZE]),
                "min_size": MIN_FONT_SIZE,
                "max_lines": MAX_LINES,
                "align": align,
                "valign": "top",
                "fit": "shrink",
            }
        )

    return payload


def render_payload(
    payload: list[dict],
    *,
    height: int | None = None,
    dither: bool = False,
    context: RenderContext | None = None,
) -> Image.Image:
    """Render an imagespec payload to a cropped, 1-bit, printer-width bitmap."""
    if not payload:
        return Image.new("1", (DOTS_PER_LINE, 8), 1)

    canvas_height = height or MAX_LABEL_HEIGHT
    ctx = context or RenderContext()
    rgb = render(
        payload,
        width=DOTS_PER_LINE,
        height=canvas_height,
        background="white",
        dither=False,
        context=ctx,
    )
    bitmap = to_bilevel(rgb, dither=dither)
    # Only auto-crop when the caller did not pin an explicit height.
    return bitmap if height else crop_to_content(bitmap, margin=MARGIN)


def to_preview_png(bitmap: Image.Image, scale: int = PREVIEW_SCALE) -> bytes:
    """Upscale the exact print bitmap for on-screen legibility.

    NEAREST is deliberate: the preview shows the true dot pattern the print head
    will burn, not a smoothed approximation of it.
    """
    preview = bitmap.convert("L").resize(
        (bitmap.width * scale, bitmap.height * scale), Image.Resampling.NEAREST
    )
    buffer = BytesIO()
    preview.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


class LabelComposer:
    """Holds the current label state and its cached render."""

    def __init__(self) -> None:
        self.state = LabelState()
        self._context = RenderContext()
        self._cached: RenderedLabel | None = None

    @property
    def cached(self) -> RenderedLabel | None:
        """The most recent render, or None if nothing has been rendered yet."""
        return self._cached

    def render(self) -> RenderedLabel:
        """Render the current state. Blocking -- call from an executor."""
        bitmap = render_payload(build_payload(self.state), context=self._context)
        rendered = RenderedLabel(
            bitmap=bitmap,
            png=to_preview_png(bitmap),
            height_px=bitmap.height,
            paper_mm=paper_mm(bitmap.height),
        )
        self._cached = rendered
        return rendered

    def render_once(
        self, payload: list[dict], *, height: int | None = None, dither: bool = False
    ) -> Image.Image:
        """Render an ad-hoc payload without disturbing the composer's cache."""
        return render_payload(payload, height=height, dither=dither, context=self._context)
