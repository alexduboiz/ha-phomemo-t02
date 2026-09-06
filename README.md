# Phomemo T02 for Home Assistant

Print labels on a Phomemo T02 Bluetooth thermal printer from Home Assistant —
with a **label composer you drive from a dashboard**: type text, choose size and
justification, see the rendered label, press print.

Works over an **ESPHome Bluetooth proxy** or a local Bluetooth adapter. The
integration goes through Home Assistant's Bluetooth stack, so either route works
without configuration.

## Features

- **Live preview.** A `picture-entity` card shows the exact 384-dot bitmap that
  will be printed. Preview and print share one render path, so what you see is
  what comes out of the printer.
- **Auto-height labels.** Labels crop to their content, so no paper is wasted and
  you never guess a height. The preview reports the millimetres needed.
- **Text, QR codes and barcodes**, rendered with
  [imagespec](https://github.com/eigger/imagespec).
- **Notify target**, so any automation can print a notification.
- **Grocy integration** — click *Print label* in Grocy and a grocycode QR prints.
  See [`examples/grocy/`](examples/grocy/).
- No custom Lovelace cards, no HACS frontend resources, no extra containers.

## Requirements

- Home Assistant 2024.12 or newer
- A Phomemo T02
- A Bluetooth route to it: a local adapter, or an ESP32 running ESPHome with
  `bluetooth_proxy` and `active: true`

## Installation

**HACS** — add this repository as a custom repository of type *Integration*,
install it, then restart Home Assistant.

**Manual** — copy `custom_components/phomemo_t02` into your `config/custom_components`
directory and restart.

Then switch the printer on. It should be discovered automatically under
**Settings → Devices & services**. If not, add it manually with
**Add integration → Phomemo T02**.

> The printer must be **powered on** to be discovered or to print. It sleeps to
> save battery and stops advertising when it does; Home Assistant cannot wake it.

## The label composer

Add the card from [`examples/dashboard/label_composer.yaml`](examples/dashboard/label_composer.yaml).

| Entity | Purpose |
|---|---|
| `image.*_label_preview` | Live preview of the bitmap to be printed |
| `text.*_label_text` | Label text (wraps and shrinks to fit) |
| `text.*_label_qr` | Optional QR payload; blank means no QR |
| `select.*_font_size` | Small / Medium / Large / Extra large |
| `select.*_justification` | Left / centre / right |
| `number.*_copies` | How many to print |
| `button.*_print_label` | Prints exactly what is previewed |
| `button.*_test_print` | Fixed self-test label |
| `button.*_feed_paper` | Advances the paper for tearing off |

Composer fields are restored across restarts.

## Actions

| Action | Purpose |
|---|---|
| `phomemo_t02.print_text` | Print wrapped text |
| `phomemo_t02.print_qr` | Print a QR code with an optional caption |
| `phomemo_t02.print` | Print a raw imagespec payload — full layout control |
| `phomemo_t02.feed` | Advance the paper |

```yaml
- action: phomemo_t02.print_qr
  data:
    data: "https://www.home-assistant.io"
    caption: "Home Assistant"
    size: Medium
```

> When writing a raw `payload`, use **`text_fit`** for text, never `text_box`.
> `text_box` draws a filled badge with inverted text, which a thermal printer
> renders as a solid black slab.

## Options

**Settings → Devices & services → Phomemo T02 → Configure** exposes the BLE
transport tuning. Defaults suit a local adapter (measured MTU 200, ~12 KB/s).
Throughput through an ESPHome proxy is lower — if prints garble or time out,
raise *Delay between writes* first, then lower *Maximum bytes per write*.

*Disconnect after idle* releases the connection between prints so a Bluetooth
proxy connection slot is not held open (an ESP32 has only three by default).

## Troubleshooting

| Symptom | Cause |
|---|---|
| Not discovered / "was not found" | Printer asleep. Press its power button. |
| Garbled or repeated output | Buffer overrun — raise the inter-write delay. |
| Blank paper feeds | Paper is in backwards; the coated side must face the head. |
| QR will not scan | Increase `boxsize`, shorten the data, or raise `eclevel` to `h`. |

Enable debug logging to see per-print timing and throughput:

```yaml
logger:
  logs:
    custom_components.phomemo_t02: debug
```

## Protocol

The T02's BLE protocol was verified against real hardware rather than assumed —
see [`docs/protocol.md`](docs/protocol.md) for the measured GATT table, command
sequences and geometry. [`tools/print_test.py`](tools/print_test.py) reproduces
that test standalone, without Home Assistant:

```bash
python tools/print_test.py scan
python tools/print_test.py probe <address>
python tools/print_test.py print <address> --text "HELLO" --qr "grocy:p:1"
```

## Credits

- [vivier/phomemo-tools](https://github.com/vivier/phomemo-tools),
  [jpurnell/T02Protocol](https://github.com/jpurnell/T02Protocol) and
  [mkuhlmann/pyphomemo](https://github.com/mkuhlmann/pyphomemo) for the
  reverse-engineering groundwork.
- [eigger/hass-niimbot](https://github.com/eigger/hass-niimbot) for the
  BLE-label-printer integration pattern, and `imagespec` for rendering.
