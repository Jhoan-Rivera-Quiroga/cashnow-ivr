"""
Cash Now Test Strips - Vapi Tool Webhook Server

Vapi AI now handles the voice layer: answering calls, speech-to-text,
talking to Claude, and text-to-speech. This Flask app only handles the
tool-call webhooks that Claude triggers mid-conversation — saving pickup
info, creating Detrack jobs, sending SMS messages.

Routes:
  POST /vapi/tools  - Vapi sends tool calls here; we execute and respond
  GET  /health      - health check for Render / UptimeRobot
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
# Keyed by Vapi call ID. Cleared when the order is finalized or call ends.
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


@app.route("/vapi/tools", methods=["POST"])
def vapi_tools():
    """
    Vapi posts here whenever Claude calls a tool during a conversation.
    Supported message types:
      - tool-calls        : Claude called one or more tools; we run them
      - end-of-call-report: call finished; we clean up the session
    """
    body = request.get_json(force=True) or {}
    message = body.get("message", {})
    msg_type = message.get("type", "")

    call_info = message.get("call", {})
    call_id = call_info.get("id", "unknown")
    caller_number = call_info.get("customer", {}).get("number", "")

    if msg_type == "end-of-call-report":
        _clear_session(call_id)
        logger.info("Call %s ended — session cleared.", call_id)
        return jsonify({}), 200

    if msg_type != "tool-calls":
        return jsonify({}), 200

    session = _get_session(call_id)
    tool_calls = message.get("toolCallList", [])
    results = []

    for tc in tool_calls:
        tool_call_id = tc.get("id")
        fn = tc.get("function", {})
        name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            args = {}

        logger.info("Tool call: %s | args: %s | call: %s", name, args, call_id)
        result = _execute_tool(name, args, session, call_id, caller_number)
        results.append({"toolCallId": tool_call_id, "result": result})

    return jsonify({"results": results})


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
            "name": collected.get("full_name", "not provided"),
            "phone": collected.get("phone") or caller_number,
            "address": collected.get("address", "not provided"),
            "pickup_date": collected.get("pickup_date", "not provided"),
            "pickup_window": collected.get("pickup_window", "not provided"),
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
