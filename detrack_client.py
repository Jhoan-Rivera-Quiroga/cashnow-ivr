"""
Thin wrapper around the Detrack v2 Jobs API for creating "Collection" jobs
(Cash Now sends a driver to a seller's location to pick up items and pay
them on the spot).

API reference: https://detrackapiv2.docs.apiary.io/#reference/jobs/list-create/create
Auth: header "X-API-KEY: <key>", "Content-Type: application/json"
Endpoint: POST https://app.detrack.com/api/v2/dn/jobs

--------------------------------------------------------------------------
IMPORTANT - VERIFY BEFORE GOING LIVE
--------------------------------------------------------------------------
Detrack accounts can have custom fields / required fields configured
differently. The field names below (`deliver_to_collect_from`,
`phone_number`, `address`, `items`, `notes`, `type`, etc.) match Detrack's
documented v2 schema, but you should:

  1. Keep DETRACK_DRY_RUN=true at first. Every call will be logged to
     orders_log.jsonl instead of hitting the API, so you can review the
     exact payload.
  2. Create one test job manually from the Detrack dashboard, then call
     GET /api/v2/dn/jobs/<id> to see the exact field names your account
     expects, and adjust `_build_payload` below if anything differs.
  3. Once you're happy, set DETRACK_DRY_RUN=false.
--------------------------------------------------------------------------
"""

import json
import logging
import os
import time
from datetime import datetime

import requests

import config

logger = logging.getLogger(__name__)

ORDERS_LOG_PATH = os.path.join(os.path.dirname(__file__), "orders_log.jsonl")


class DetrackError(Exception):
    pass


def _build_payload(order: dict) -> dict:
    """
    Turn our internal `order` dict into a Detrack "Collection" job payload.

    Expected `order` keys:
      - name (str): seller's full name
      - phone (str): callback phone number
      - address (str): full pickup address
      - pickup_date (str): "YYYY-MM-DD"
      - pickup_window (str): human-readable time window, e.g. "2:00 PM - 4:00 PM"
      - items (list[dict]): [{"description": str, "quantity": int, "expiration": str}]
      - photo_provided (bool)
      - language (str): "en" | "es"
      - call_sid (str): Twilio CallSid, for traceability
    """
    items = []
    for item in order.get("items", []):
        desc = item.get("description", "").strip()
        exp = item.get("expiration", "").strip()
        if exp:
            desc = f"{desc} (Exp: {exp})"
        items.append(
            {
                "item_sku": "",
                "description": desc,
                "quantity": item.get("quantity", 1),
                "u_om": "ea",
            }
        )

    notes_lines = [
        "*** AI-GENERATED DRAFT - PLEASE REVIEW & CONFIRM PRICING BEFORE DISPATCH ***",
        f"Source: Inbound phone call ({order.get('call_sid', 'unknown')})",
    ]
    if order.get("pickup_window"):
        notes_lines.append(f"Preferred pickup window: {order['pickup_window']}")
    notes_lines.append(
        "Photo of items: " + ("yes, customer said they will send one" if order.get("photo_provided") else "not provided")
    )
    if order.get("extra_notes"):
        notes_lines.append(f"Additional notes from caller: {order['extra_notes']}")

    payload = {
        "data": {
            "type": "Collection",
            "do_number": f"CN-{int(time.time())}",
            "date": order.get("pickup_date") or datetime.now().strftime("%Y-%m-%d"),
            "deliver_to_collect_from": order.get("name", ""),
            "phone_number": order.get("phone", ""),
            "address": order.get("address", ""),
            "instructions": "\n".join(notes_lines),
            "payment_mode": "cash",
            "items": items,
            "status": "dispatched",
        }
    }
    return payload


def _log_order(order: dict, payload: dict, response: dict | None, dry_run: bool):
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "dry_run": dry_run,
        "order": order,
        "detrack_payload": payload,
        "detrack_response": response,
    }
    try:
        with open(ORDERS_LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        logger.exception("Failed to write order to local log")


def create_draft_collection(order: dict) -> dict:
    """
    Create a draft Detrack Collection job for an inbound "we'll buy your
    supplies" call.

    Returns a dict: {"ok": bool, "detrack_id": str | None, "dry_run": bool, "error": str | None}
    This never raises - callers should always be able to give the customer
    a confident confirmation, even if Detrack creation fails (in which case
    the order is still saved to ORDERS_LOG_PATH for manual follow-up).
    """
    payload = _build_payload(order)

    if config.DETRACK_DRY_RUN or not config.DETRACK_API_KEY:
        _log_order(order, payload, None, dry_run=True)
        logger.info("DETRACK_DRY_RUN active - logged order instead of calling API: %s", payload)
        return {"ok": True, "detrack_id": None, "dry_run": True, "error": None}

    url = f"{config.DETRACK_BASE_URL}/dn/jobs"
    headers = {"X-API-KEY": config.DETRACK_API_KEY, "Content-Type": "application/json"}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp_json = resp.json() if resp.content else {}
    except requests.RequestException as exc:
        logger.exception("Detrack API request failed")
        _log_order(order, payload, {"error": str(exc)}, dry_run=False)
        return {"ok": False, "detrack_id": None, "dry_run": False, "error": str(exc)}

    _log_order(order, payload, resp_json, dry_run=False)

    if resp.status_code not in (200, 201):
        return {
            "ok": False,
            "detrack_id": None,
            "dry_run": False,
            "error": f"Detrack returned {resp.status_code}: {resp_json}",
        }

    detrack_id = None
    data = resp_json.get("data") if isinstance(resp_json, dict) else None
    if isinstance(data, dict):
        detrack_id = data.get("id")
    elif isinstance(data, list) and data:
        detrack_id = data[0].get("id")

    return {"ok": True, "detrack_id": detrack_id, "dry_run": False, "error": None}
