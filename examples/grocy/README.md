# Printing Grocy labels on the T02

Grocy's label printer feature POSTs to a webhook when you click *Print label*.
Home Assistant webhooks need no authentication token, so Grocy can call one
directly — no bridge service in between.

```
Grocy UI  ──POST──▶  HA webhook  ──▶  automation  ──▶  phomemo_t02.print  ──▶  T02
```

## 1. Pick a webhook ID

Any hard-to-guess string. This example uses `phomemo_grocy_label`. Because the
endpoint is unauthenticated, prefer a random ID and keep `local_only: true` so it
only accepts requests from your LAN.

## 2. Configure Grocy

Add to Grocy's `config.php` (verify the setting names against the `config-dist.php`
shipped with your version — they have changed across releases):

```php
Setting('FEATURE_FLAG_LABEL_PRINTER', true);
Setting('LABEL_PRINTER_WEBHOOK', 'http://192.168.7.10:8123/api/webhook/phomemo_grocy_label');
Setting('LABEL_PRINTER_RUN_SERVER', true);   // POST from the Grocy container, not the browser
Setting('LABEL_PRINTER_HOOK_JSON', true);    // send JSON rather than form fields
Setting('LABEL_PRINTER_PARAMS', []);
```

Replace the IP with your Home Assistant address. Restart Grocy afterwards.

- `LABEL_PRINTER_RUN_SERVER = true` makes the Grocy **container** issue the POST.
  Keep it true: the container can reach HA even when the browser cannot.
- `LABEL_PRINTER_HOOK_JSON = true` matches the `trigger.json` templates below. If
  you leave it false, Grocy sends form fields and you must use `trigger.data`
  instead.

## 3. Add the automation

Copy `automation.yaml` into Home Assistant (Settings → Automations → Edit in YAML).

## What Grocy sends

| Field | Example | Used here |
|---|---|---|
| `grocycode` | `grocy:p:42` | yes — the QR payload |
| `product` | `Coffee beans` | yes — the caption |
| `due_date` | `DD: 2026-06-09` | no |
| `details` | full product object | no |
| `stock_entry` | stock entry object | only for stock-entry labels |

The layout lives in the automation, not in Python, so you can retune spacing and
font sizes without restarting Home Assistant.

## Verifying

Click *Print label* on any Grocy product. A label should print within a couple of
seconds. **Scan it with your phone** — it must decode to `grocy:p:<id>`. If it
decodes, Grocy will recognise it when scanned back in.

## Troubleshooting

- **Nothing prints.** Check the automation traces first (Settings → Automations →
  the automation → Traces). If there is no trace, the POST never arrived — check
  Grocy's URL and that `LABEL_PRINTER_RUN_SERVER` is true.
- **Trace runs but the print fails.** The printer is almost certainly asleep; it
  stops advertising when it powers down. Press its power button and retry.
- **The QR will not scan.** Increase `boxsize`, or shorten the data. Error
  correction is set to `m`; raising it to `h` adds redundancy but enlarges the code.
