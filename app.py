"""
Cash Now Test Strips - Retell Tool Webhook Server

Retell AI handles the voice layer: answering calls, speech-to-text,
talking to Claude, and text-to-speech. This Flask app only handles the
tool-call webhooks that Claude triggers mid-conversation — saving pickup
info, creating Detrack jobs, sending SMS messages.

Routes:
  POST /retell/tools    - Retell sends one tool call here per request
  POST /retell/webhook  - Retell call lifecycle events (call_ended, etc.)
  GET  /health          - health check for Render / UptimeRobot
"""

import json
import logging
import threading

from flask import Flask, request, jsonify

import config
import detrack_client
import hours
import sms_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Per-call session store
# Tracks pickup info collected across multiple tool calls within one call.
# Keyed by Retell call ID. Cleared when the order is finalized or call ends.
# ---------------------------------------------------------------------------

_sessions: dict = {}
_sessions_lock = threading.Lock()


def _get_session(call_id: str) -> dict:
    with _sessions_lock:
        if call_id not in _sessions:
            _sessions[call_id] = {
                "collected": {},
                "items": [],
                "language": "en",
            }
        return _sessions[call_id]


def _clear_session(call_id: str):
    with _sessions_lock:
        _sessions.pop(call_id, None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


@app.route("/retell/tools", methods=["POST"])
def retell_tools():
    """
    Retell posts here when Claude calls a tool.
    One tool call per request; respond with {"result": "..."}
    """
    body = request.get_json(force=True) or {}

    call_info = body.get("call", {})
    call_id = call_info.get("call_id", "unknown")
    caller_number = call_info.get("from_number", "")

    logger.info("Retell raw body keys: %s", list(body.keys()))
    logger.info("Retell raw body: %s", body)

    tool_name = body.get("name", "")
    args = body.get("args") or body.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, TypeError):
            args = {}

    logger.info("Tool call: %s | args: %s | call: %s", tool_name, args, call_id)
    session = _get_session(call_id)
    result = _execute_tool(tool_name, args, session, call_id, caller_number)

    return jsonify({"result": result})


@app.route("/retell/webhook", methods=["POST"])
def retell_webhook():
    """
    Retell general webhook for call lifecycle events.
    Used to clear the session when a call ends.
    """
    body = request.get_json(force=True) or {}
    event = body.get("event", "")

    if event == "call_ended":
        call_id = body.get("call", {}).get("call_id", "")
        if call_id:
            _clear_session(call_id)
            logger.info("Call %s ended — session cleared.", call_id)

    return jsonify({}), 200


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _execute_tool(
    name: str, args: dict, session: dict, call_id: str, caller_number: str
) -> str:

    if name == "update_pickup_info":
        collected = session["collected"]
        for key in (
            "full_name", "phone", "address", "pickup_date",
            "pickup_window", "photo_provided", "extra_notes",
        ):
            if key in args:
                collected[key] = args[key]
        if "items" in args:
            session["items"] = args["items"]
        logger.info("Pickup info updated for call %s: %s", call_id, collected)
        return "Saved."

    elif name == "finalize_pickup":
        collected = session["collected"]
        order = {
            "name": collected.get("full_name", ""),
            "phone": collected.get("phone") or caller_number,
            "address": collected.get("address", ""),
            "pickup_date": collected.get("pickup_date", ""),
            "pickup_window": collected.get("pickup_window", ""),
            "items": session.get("items", []),
            "photo_provided": collected.get("photo_provided", False),
            "extra_notes": collected.get("extra_notes", ""),
            "language": session.get("language", "en"),
            "call_sid": call_id,
        }
        result = detrack_client.create_draft_collection(order)
        if not result.get("ok"):
            logger.error(
                "Detrack draft failed for call %s: %s",
                call_id, result.get("error"),
            )
            sms_client.alert_dispatch_failure(
                order, result.get("error", "unknown error")
            )
        _clear_session(call_id)
        return (
            "Draft order created successfully."
            if result.get("ok")
            else "Order saved locally; Detrack sync failed."
        )

    elif name == "set_language":
        lang = args.get("language", "en")
        if lang in ("en", "es"):
            session["language"] = lang
        return f"Language set to {lang}."

    elif name == "send_website_link":
        phone = args.get("phone") or caller_number
        ok = sms_client.send_pickup_form_link(phone, session.get("language", "en"))
        return "Link sent." if ok else "Failed to send link."

    elif name == "switch_to_pickup_flow":
        return "Switched to pickup flow."

    elif name == "check_business_hours":
        is_open = hours.is_open()
        msg = hours.hours_message(session.get("language", "en"))
        return f"{'Open' if is_open else 'Closed'}. {msg}"

    else:
        logger.warning("Unknown tool called: %s", name)
        return f"Unknown tool: {name}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
