# Phomemo T02 — verified BLE protocol

Everything here was **measured against a physical T02**, not copied from another
project. Verified 2026-09-06 with `tools/print_test.py` over a local Windows BLE
adapter (bleak 3.0.2).

## Advertising / discovery

| Property | Value |
|---|---|
| Advertised local name | `T02` |
| Example address | `9C:A8:02:DB:13:95` |
| Service UUIDs in advertisement | **none** |

> **Discovery must match on `local_name`, not service UUID.** The T02 does *not*
> advertise its `ff00` service, so a `service_uuid` matcher in `manifest.json`
> would never fire. This is the single most important discovery finding.

The printer only advertises while awake. It auto-sleeps, after which it disappears
from scans entirely — the most common "it stopped working" cause.

## GATT table (measured)

```
service 00001800  Generic Access Profile
   char 00002a00  ['read']
service 0000ff00  Vendor specific
   char 0000ff01  ['read']
   char 0000ff02  ['write', 'write-without-response']   <-- send raster here
   char 0000ff03  ['notify']  + CCCD 00002902
```

- **Negotiated MTU: 200** → 197-byte write payloads. Far better than the 23-byte
  worst case assumed during planning.
- `ff02` supports **write-without-response**, so writes pipeline without per-packet
  acknowledgement round trips.
- `ff03` emits `01 01` repeatedly while printing — a status/heartbeat. We subscribe
  but do not depend on it for flow control.

## Command sequence (verified working)

| Bytes | Meaning |
|---|---|
| `1b 40` | Initialise (ESC @) |
| `1b 61 n` | Justify: 0 left, 1 centre, 2 right |
| `1d 76 30 00 xL xH yL yH` + data | Raster block (GS v 0) |
| `1b 64 n` | Feed n lines |

- `x` = **bytes** per line = `48`, little-endian → `30 00`
- `y` = **lines** in this block, little-endian
- Blocks are capped at **255 lines**; taller images are split into several blocks.

**No density/energy command is required.** `1b 4e 0d <n>` was *not* sent in the
successful print and output was sharp and fully black. It remains available in the
tool behind `--energy` but is deliberately unused by the integration.

**No footer/finalise sequence is required.** The `1f f0 …` footer seen in M110-family
implementations is not needed on the T02; a trailing feed is sufficient.

## Geometry

| Property | Value |
|---|---|
| Print width | **384 dots = 48 bytes/line** (verified: a full-width bar reaches both paper edges with no offset) |
| Density | 203 DPI, 8 dots/mm |
| Paper | 50 mm, ~48 mm printable |
| Vertical | image height in px ÷ 8 = mm of paper consumed |

## Bit packing

Rows are packed MSB-first, 8 pixels per byte, left to right.
**A set bit burns (black).** In PIL mode `"1"` black is `0`, so the polarity inverts:

```python
if pixel == 0:            # black in PIL
    byte |= 0x80 >> bit   # set bit = burn
```

## Measured throughput

```
11,536 bytes -> 59 writes -> 0.91 s -> 12.37 KB/s
(chunk = mtu-3 = 197, write-without-response, 10 ms inter-chunk delay)
```

A typical QR + name label is ~1 second over a local adapter. Throughput through an
ESPHome Bluetooth proxy will be lower and the negotiated MTU may differ, which is why
chunk size and inter-chunk delay are exposed as options rather than hard-coded.

## Rendering notes (imagespec 0.4.0)

- **Use `text_fit` for label text, never `text_box`.** `text_box` draws a *badge* —
  a filled rounded rectangle, default `fill: black` with default `color: white` — which
  on a thermal printer burns a solid slab. Its `width` key is the **outline width**,
  not a wrap width.
- `text_fit` word-wraps, takes `align` (left/center/right), `valign`, `max_lines`, and
  shrinks from `size` down to `min_size` to fit. Colour defaults to black.
- `RenderContext()` resolves its default font offline; no font download is needed.
- `render()` returns an **RGB** image, so quantise to `"1"` before packing.
