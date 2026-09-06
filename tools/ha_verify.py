"""Verify a deployed Phomemo T02 integration through the Home Assistant REST API.

Reads the base URL and a long-lived access token from the environment so the
token never lands in the repo, a shell history, or a log line:

    HA_URL=http://192.168.7.21:8123 HA_TOKEN=xxxx python tools/ha_verify.py

Checks, in order:
  1. the API answers and the token is valid
  2. the phomemo_t02 entities exist, and prints their real entity_ids
     (so the dashboard YAML can be corrected to match)
  3. the live preview refreshes when a composer field changes -- this is the
     core acceptance test for the image entity
  4. optionally fires a print service (only with --print, since it uses paper)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("HA_URL", "http://192.168.7.21:8123").rstrip("/")
TOKEN = os.environ.get("HA_TOKEN", "")


def _req(method: str, path: str, body: dict | None = None, raw: bool = False):
    import json

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{URL}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = resp.read()
    if raw:
        return payload
    return json.loads(payload) if payload else None


def _get_states() -> list[dict]:
    return _req("GET", "/api/states")


def check_api() -> None:
    print("1. API reachability")
    try:
        message = _req("GET", "/api/")
        print(f"   ok: {message.get('message')}")
    except urllib.error.HTTPError as err:
        sys.exit(f"   FAILED: HTTP {err.code} - is the token valid?")
    except OSError as err:
        sys.exit(f"   FAILED: {err} - is {URL} reachable?")


def find_entities() -> dict[str, dict]:
    print("\n2. phomemo_t02 entities")
    states = _get_states()
    ours = {
        s["entity_id"]: s
        for s in states
        if "phomemo" in s["entity_id"] or "phomemo" in str(s.get("attributes", {})).lower()
    }
    if not ours:
        sys.exit("   FAILED: no phomemo entities found. Is the integration set up?")
    for entity_id, state in sorted(ours.items()):
        extra = ""
        if entity_id.startswith("image."):
            attrs = state.get("attributes", {})
            extra = f"  paper_mm={attrs.get('paper_mm')} height_dots={attrs.get('height_dots')}"
        print(f"   {entity_id:<45} state={state['state']!r}{extra}")
    return ours


def _preview_entity(entities: dict[str, dict]) -> str | None:
    for entity_id in entities:
        if entity_id.startswith("image.") and "preview" in entity_id:
            return entity_id
    return None


def _text_entity(entities: dict[str, dict]) -> str | None:
    for entity_id in entities:
        if entity_id.startswith("text.") and "qr" not in entity_id:
            return entity_id
    return None


def check_preview_refresh(entities: dict[str, dict]) -> None:
    print("\n3. live preview refresh")
    preview = _preview_entity(entities)
    text = _text_entity(entities)
    if not preview or not text:
        print(f"   skipped: preview={preview} text={text}")
        return

    before = _get_state(preview)["attributes"].get("entity_picture", "")
    new_text = f"verify {int(time.time()) % 10000}"
    _req("POST", "/api/services/text/set_value", {"entity_id": text, "value": new_text})
    time.sleep(2.0)
    after_state = _get_state(preview)
    after = after_state["attributes"].get("entity_picture", "")

    print(f"   set {text} = {new_text!r}")
    print(f"   preview entity_picture changed: {before != after}")
    print(f"   preview paper_mm now: {after_state['attributes'].get('paper_mm')}")
    if before == after:
        print("   NOTE: entity_picture token did not change - check image_last_updated")


def _get_state(entity_id: str) -> dict:
    return _req("GET", f"/api/states/{entity_id}")


def do_print(entities: dict[str, dict], data: str, caption: str) -> None:
    print("\n4. print_qr service call")
    device_ok = any(e.startswith("button.") for e in entities)
    if not device_ok:
        print("   skipped: no button entity found to confirm the device")
    _req(
        "POST",
        "/api/services/phomemo_t02/print_qr",
        {"data": data, "caption": caption, "size": "Medium"},
    )
    print(f"   called print_qr(data={data!r}, caption={caption!r}) - check the paper")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", action="store_true", help="also fire a print (uses paper)")
    parser.add_argument("--qr-data", default="grocy:p:1")
    parser.add_argument("--caption", default="HA verify")
    args = parser.parse_args()

    if not TOKEN:
        sys.exit("Set HA_TOKEN (a long-lived access token) in the environment first.")

    print(f"Home Assistant: {URL}\n")
    check_api()
    entities = find_entities()
    check_preview_refresh(entities)
    if args.print:
        do_print(entities, args.qr_data, args.caption)
    print("\nDone.")


if __name__ == "__main__":
    main()
