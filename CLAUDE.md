# CLAUDE.md — Phomemo T02 Home Assistant integration

Full project context for Claude Code. Read this before doing anything else.

---

## Project Goal

A HACS-installable Home Assistant custom integration (`phomemo_t02`) that prints
to a Phomemo T02 Bluetooth thermal printer, with:

1. A **label composer** driven from a dashboard — text, QR data, font size,
   justification, copies, and a **live preview** of the exact bitmap to be printed.
2. Actions for automations (`print`, `print_text`, `print_qr`, `feed`).
3. A **notify** target.
4. **Grocy** grocycode QR label printing via Grocy's label printer webhook.

---

## Infrastructure Context

**Owner:** Alexandre (Montreal/Quebec area, home lab)

**Home lab stack:**
- **Proxmox** — main hypervisor (`pm-1.lan.internal` / `192.168.7.5`)
- **OpenMediaVault** — NAS VM, NFS shares
- **Docker / Portainer** — container management (includes **Grocy**)
- **Home Assistant** — Bluetooth integration enabled; an **ESP32 running ESPHome**
  acts as the Bluetooth proxy that reaches the printer
- **OpenWRT** — router

**Printer:** Phomemo T02, BLE, address `9C:A8:02:DB:13:95`, advertises as `T02`.

---

## Architecture

```
GUI entities (text/select/number) ──┐
Grocy ─POST→ HA webhook ─→ automation ├─→ imagespec.render() ─→ PIL 1-bit bitmap
notify / actions ───────────────────┘                 │
                                        ┌─────────────┴─────────────┐
                                        ↓                           ↓
                                image entity (PNG preview)     protocol.py
                                                               ESC/POS raster
                                                                     ↓
                                                               printer.py
                                                     chunked GATT writes → 0xff02
                                                                     ↓
                                        HA bluetooth → ESPHome proxy (BLE) → T02
```

**The integration never imports `bleak` for device discovery.** It resolves the
device via `homeassistant.components.bluetooth.async_ble_device_from_address`,
which is what makes the ESPHome proxy route work. Direct bleak scanning does not
see proxy-visible devices.

---

## Module Breakdown

| File | Responsibility |
|---|---|
| `protocol.py` | **Pure.** PIL image → bytes. No I/O, no HA imports. Fully unit-tested. |
| `composer.py` | Label state → imagespec payload → cached (bitmap, PNG, mm). Pure, blocking. |
| `printer.py` | BLE transport: connect, MTU probe, chunked writes, idle disconnect. |
| `coordinator.py` | Ties composer + printer together; owns `preview_updated`. |
| `config_flow.py` | Bluetooth discovery (matches `local_name`) + options flow. |
| `entity.py` | Shared base: device info, naming, listener subscription. |
| `text/select/number.py` | Composer inputs. All `RestoreEntity`. |
| `image.py` | The live preview. |
| `button.py` / `notify.py` | Print, test print, feed; notification target. |

---

## Key Design Decisions

- **One render path.** `composer.render()` produces the bitmap *and* the PNG
  together and caches both. The print button sends the **cached bitmap**, so the
  print cannot drift from the preview. Never re-render on print.
- **`image_last_updated` is bumped by the coordinator**, never inside
  `async_image()`. That is HA's documented pattern and is what triggers the
  frontend to refetch. Changing this breaks the live preview.
- **Use `text_fit`, never `text_box`.** `text_box` is a *badge* element: filled
  rounded rect (`fill` defaults to black) with `color` defaulting to white. On a
  thermal printer that burns a solid slab. Its `width` key is the **outline
  width**, not a wrap width. `text_fit` word-wraps, takes `align`, and defaults to
  black.
- **Discovery matches `local_name`, not service UUID.** The T02 does not
  advertise its `ff00` service. A `service_uuid` matcher would never fire.
- **Rendering runs in an executor.** PIL and imagespec are blocking; they must
  never run on the event loop.
- **Idle disconnect.** An ESP32 proxy has only ~3 connection slots, so the link is
  dropped between prints rather than held open.
- **No density/energy command.** Verified unnecessary on the T02; output is sharp
  without it.

---

## Verified Hardware Facts

Measured, not assumed — full detail in `docs/protocol.md`.

- Service `ff00`; write `ff02` (**supports write-without-response**); notify `ff03`
- **MTU 200** on a local adapter → 197-byte writes
- **384 dots = 48 bytes/line**, 203 DPI, 8 dots/mm
- Raster blocks capped at **255 lines**
- Throughput **12.4 KB/s** locally (11,536 bytes / 59 writes / 0.91 s)
- `ff03` emits `01 01` while printing (diagnostic only; not used for flow control)

---

## Testing

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

`tests/conftest.py` loads `protocol.py` through a synthetic package so the tests
run **without Home Assistant installed**. Keep `protocol.py` free of HA imports or
this breaks.

`tools/print_test.py` exercises real hardware standalone:

```bash
python tools/print_test.py scan
python tools/print_test.py probe 9C:A8:02:DB:13:95
python tools/print_test.py print 9C:A8:02:DB:13:95 --text "HELLO" --qr "grocy:p:1"
```

---

## Gotchas

- **Entity IDs slug from the friendly name, not the entity key.** With
  `_attr_has_entity_name`, key `label_qr` named "QR data" becomes
  `text.<device>_qr_data`; translation_key `align` named "Justification" becomes
  `select.<device>_justification`. Don't guess dashboard entity IDs from the code
  keys — derive them from display names or read them from a live instance.
- **The image preview refreshes on the entity's state, not `entity_picture`.**
  An `ImageEntity`'s state is its `image_last_updated` timestamp, which the
  frontend watches to refetch. `entity_picture` embeds an access token that
  rotates on a timer, not per render, so it is the wrong signal to check.
- **The printer sleeps** and stops advertising. This is the most common runtime
  failure and cannot be fixed in software — the error messages say so explicitly.
  The config flow has a manual free-text address step so a printer can still be
  added while asleep (it stays unavailable until the next print wakes it).
- **Throughput over an ESPHome proxy is lower than local** and the negotiated MTU
  may differ, which is why chunk size and delay are options rather than constants.
- **Windows paths:** the Bash tool is Git Bash. Python invoked from it needs
  Windows-style paths (`C:\...`), not MSYS `/c/...` paths.
- **Home Assistant cannot be pip-installed on this dev machine.** `lru-dict`
  needs MSVC build tools, and HA does not support Windows anyway. To validate HA
  API usage without installing it, download the wheel and read the source:

  ```bash
  .venv/Scripts/python.exe -m pip download homeassistant --no-deps \
      --only-binary=:all: -d <dir>
  unzip -q <dir>/homeassistant-*.whl -d <src>
  ```

  Then grep `<src>/homeassistant/...`. Use ripgrep (the Grep tool); a recursive
  shell `grep` over that tree times out. `pyflakes` catches undefined and unused
  names across the integration without HA present.

---

## Workflow — After Every Modification

1. **Create a GitHub issue** (`gh issue create`) describing the bug found or
   improvement made — root cause, impact, fix
2. **Commit** the changed files with a clear message
3. **Push** to GitHub

This keeps a full trace of every change alongside the reasoning behind it.
