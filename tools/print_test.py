"""Standalone Phomemo T02 probe + print test (no Home Assistant required).

Run this FIRST, from a machine with a Bluetooth radio and the printer powered on
and nearby. It establishes ground truth for the protocol before any integration
code is written:

    python tools/print_test.py scan
    python tools/print_test.py probe <address>
    python tools/print_test.py print <address> --text "HELLO"
    python tools/print_test.py print <address> --qr "grocy:p:1" --text "Coffee"

Written against bleak 3.x.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from bleak import BleakClient, BleakScanner
from PIL import Image, ImageChops, ImageDraw, ImageFont

# --- Protocol constants (see docs/protocol.md) -----------------------------
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff03-0000-1000-8000-00805f9b34fb"

DOTS_PER_LINE = 384
BYTES_PER_LINE = DOTS_PER_LINE // 8  # 48

CMD_INIT = bytes([0x1B, 0x40])
CMD_RASTER_HDR = bytes([0x1D, 0x76, 0x30, 0x00])
MAX_LINES_PER_BLOCK = 255


def cmd_justify(n: int) -> bytes:
    return bytes([0x1B, 0x61, n])


def cmd_feed(n: int) -> bytes:
    return bytes([0x1B, 0x64, n])


def cmd_energy(n: int) -> bytes:
    """Unverified on the T02 -- print with and without it to find out."""
    return bytes([0x1B, 0x4E, 0x0D, n])


# --- Raster encoding -------------------------------------------------------
def pack_image(img: Image.Image) -> bytes:
    """Pack a 1-bit PIL image into MSB-first rows. Bit set = burn = black."""
    if img.width != DOTS_PER_LINE:
        raise ValueError(f"image must be exactly {DOTS_PER_LINE}px wide, got {img.width}")
    img = img.convert("1")
    px = img.load()
    out = bytearray()
    for y in range(img.height):
        for xb in range(BYTES_PER_LINE):
            byte = 0
            for bit in range(8):
                # PIL mode "1": 0 = black. Printer: bit set = burn = black.
                if px[xb * 8 + bit, y] == 0:
                    byte |= 0x80 >> bit
            out.append(byte)
    return bytes(out)


def encode_print(img: Image.Image, energy: int | None = None, feed: int = 3) -> bytes:
    """Full byte stream for one print job."""
    data = pack_image(img)
    stream = bytearray()
    stream += CMD_INIT
    if energy is not None:
        stream += cmd_energy(energy)
    stream += cmd_justify(0)

    for start in range(0, img.height, MAX_LINES_PER_BLOCK):
        lines = min(MAX_LINES_PER_BLOCK, img.height - start)
        stream += CMD_RASTER_HDR
        stream += bytes([BYTES_PER_LINE & 0xFF, BYTES_PER_LINE >> 8, lines & 0xFF, lines >> 8])
        stream += data[start * BYTES_PER_LINE : (start + lines) * BYTES_PER_LINE]

    stream += cmd_feed(feed)
    return bytes(stream)


# --- Test image ------------------------------------------------------------
def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def build_test_image(text: str | None, qr_data: str | None) -> Image.Image:
    """Compose on a tall canvas, then crop to content -- the auto-height approach."""
    canvas = Image.new("1", (DOTS_PER_LINE, 1200), 1)  # 1 = white
    draw = ImageDraw.Draw(canvas)
    y = 8

    if qr_data:
        import qrcode

        qr = qrcode.QRCode(border=1, box_size=6)
        qr.add_data(qr_data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("1")
        canvas.paste(qr_img, ((DOTS_PER_LINE - qr_img.width) // 2, y))
        y += qr_img.height + 12

    if text:
        font = _font(48)
        width = draw.textlength(text, font=font)
        draw.text(((DOTS_PER_LINE - width) // 2, y), text, font=font, fill=0)
        y += 60

    # Full-width bar: shows the true printable width and head alignment.
    draw.rectangle([0, y + 4, DOTS_PER_LINE - 1, y + 12], fill=0)

    # getbbox() finds non-zero pixels; in mode "1" black is 0, so invert first.
    bbox = ImageChops.invert(canvas.convert("L")).getbbox()
    if bbox is None:
        raise SystemExit("nothing to print")
    height = min(canvas.height, bbox[3] + 8)
    height += (-height) % 8
    return canvas.crop((0, 0, DOTS_PER_LINE, height))


# --- BLE -------------------------------------------------------------------
async def cmd_scan(_args: argparse.Namespace) -> None:
    print("Scanning 12s for BLE devices (printer must be ON)...\n")
    found = await BleakScanner.discover(timeout=12.0, return_adv=True)
    rows = []
    for addr, (dev, adv) in found.items():
        name = adv.local_name or dev.name or "(unnamed)"
        has_ff00 = any(u.lower().startswith("0000ff00") for u in adv.service_uuids)
        rows.append((has_ff00, name, addr, adv.rssi, list(adv.service_uuids)))
    rows.sort(key=lambda r: (not r[0], -r[3]))
    for has_ff00, name, addr, rssi, uuids in rows:
        flag = "  <-- advertises ff00, LIKELY THE PRINTER" if has_ff00 else ""
        print(f"{name:<28} {addr}  rssi={rssi}{flag}")
        if uuids:
            print(f"{'':<28} uuids={uuids}")
    print("\nLook for a device named like T02. Use its address with the probe command.")


async def cmd_probe(args: argparse.Namespace) -> None:
    print(f"Connecting to {args.address}...")
    async with BleakClient(args.address, timeout=25.0) as client:
        print(f"connected={client.is_connected}  mtu_size={client.mtu_size}")
        print(f"  -> max write payload without response: {client.mtu_size - 3} bytes\n")
        for service in client.services:
            print(f"service {service.uuid}  ({service.description})")
            for char in service.characteristics:
                print(f"   char {char.uuid}  props={char.properties}")
                for desc in char.descriptors:
                    print(f"        desc {desc.uuid}")
        print("\nExpected: service 0000ff00, write char 0000ff02, notify char 0000ff03.")


def _notify_logger(_sender, data: bytearray) -> None:
    print(f"  <- notify: {data.hex(' ')}")


async def cmd_print(args: argparse.Namespace) -> None:
    img = build_test_image(args.text, args.qr)
    print(f"Image: {img.width}x{img.height}px  ({img.height / 8:.1f} mm of paper)")
    if args.dump:
        img.save(args.dump)
        print(f"Saved preview to {args.dump}")

    payload = encode_print(img, energy=args.energy, feed=args.feed)
    print(f"Payload: {len(payload)} bytes")
    print(f"  header: {payload[:16].hex(' ')}")
    if args.dry_run:
        print("--dry-run: not sending.")
        return

    async with BleakClient(args.address, timeout=25.0) as client:
        mtu = client.mtu_size
        chunk = args.chunk or max(20, mtu - 3)
        char = client.services.get_characteristic(WRITE_UUID)
        if char is None:
            raise SystemExit(f"write characteristic {WRITE_UUID} not found")
        no_resp = "write-without-response" in char.properties
        print(f"connected  mtu={mtu}  chunk={chunk}  write_without_response={no_resp}")

        try:
            await client.start_notify(NOTIFY_UUID, _notify_logger)
        except Exception as err:  # noqa: BLE001 - notify is optional
            print(f"(notify unavailable: {err})")

        start = time.monotonic()
        writes = 0
        for i in range(0, len(payload), chunk):
            await client.write_gatt_char(char, payload[i : i + chunk], response=not no_resp)
            writes += 1
            if args.delay:
                await asyncio.sleep(args.delay / 1000)
        elapsed = time.monotonic() - start

        print(
            f"\nSent {len(payload)} bytes in {writes} writes, {elapsed:.2f}s "
            f"({len(payload) / elapsed / 1024:.2f} KB/s)"
        )
        await asyncio.sleep(2.0)  # let the printer drain before disconnecting


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan", help="list nearby BLE devices").set_defaults(func=cmd_scan)

    probe = sub.add_parser("probe", help="dump GATT services/characteristics + MTU")
    probe.add_argument("address")
    probe.set_defaults(func=cmd_probe)

    pr = sub.add_parser("print", help="render and print a test label")
    pr.add_argument("address")
    pr.add_argument("--text", default="HELLO")
    pr.add_argument("--qr", default=None)
    pr.add_argument("--energy", type=int, default=None, help="try 0-255; omit to skip the command")
    pr.add_argument("--feed", type=int, default=3)
    pr.add_argument("--chunk", type=int, default=None, help="bytes per GATT write (default mtu-3)")
    pr.add_argument("--delay", type=float, default=0, help="ms between writes")
    pr.add_argument("--dump", default=None, help="save the bitmap to this PNG")
    pr.add_argument("--dry-run", action="store_true")
    pr.set_defaults(func=cmd_print)

    args = parser.parse_args()
    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
