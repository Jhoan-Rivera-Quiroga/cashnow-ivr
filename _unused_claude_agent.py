"""
Claude-powered conversation engine.

Design goal: ONE Anthropic API call per caller turn (important for phone
latency). We achieve this by treating tool calls as "fire and forget" side
effects - Claude is instructed to write its spoken reply (a text block) IN
THE SAME response as any tool_use blocks, so we never need a second
round-trip to get the words to speak back to the caller.

`converse()` is the single entry point used by app.py. It:
  1. Appends the caller's latest utterance to session["messages"]
  2. Calls Claude with the right system prompt + tools for session["flow"]
  3. Applies any tool calls (updating session state / triggering side effects)
  4. Returns the text to speak + a set of flags describing what app.py should
     do next (transfer the call, hang up, send an SMS, switch flows, etc.)
"""

import logging

import anthropic

import config
import detrack_client
import prompts
import sms_client

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOL_SET_LANGUAGE = {
    "name": "set_language",
    "description": "Call this whenever you switch the language you're responding in, so the phone system can use the right voice for text-to-speech.",
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["en", "es"],
                "description": "Language you are now responding in.",
            }
        },
        "required": ["language"],
    },
}

TOOL_TRANSFER = {
    "name": "transfer_to_representative",
    "description": "Call this when the caller asks to speak with a human representative / agent / person, or the request is something you cannot handle on this call.",
    "input_schema": {"type": "object", "properties": {}},
}

TOOL_END_CALL = {
    "name": "end_call",
    "description": "Call this when the conversation is complete and the caller is ready to hang up (after you've said goodbye in your reply text).",
    "input_schema": {"type": "object", "properties": {}},
}

TOOL_UPDATE_PICKUP_INFO = {
    "name": "update_pickup_info",
    "description": (
        "Save or update information collected for the pickup order. Call this "
        "as soon as you learn any new piece of information - you don't need to "
        "wait until everything is collected. Only include fields you actually "
        "learned this turn or are updating; omit fields you don't have yet. "
        "For 'items', always pass the COMPLETE current list of items (including "
        "ones mentioned in earlier turns plus any new/updated ones), not just "
        "the newest one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "full_name": {"type": "string", "description": "Seller's full name"},
            "phone": {"type": "string", "description": "Best callback phone number"},
            "address": {"type": "string", "description": "Full pickup address"},
            "pickup_date": {
                "type": "string",
                "description": "Requested pickup date, e.g. '2026-06-17' or 'tomorrow' phrased as an actual date you resolve from today's date.",
            },
            "pickup_window": {
                "type": "string",
                "description": "Requested pickup time window, e.g. '2:00 PM - 4:00 PM'",
            },
            "photo_provided": {
                "type": "boolean",
                "description": "True if the caller agreed to text photos of the items.",
            },
            "extra_notes": {
                "type": "string",
                "description": "Any other relevant notes from the caller for the dispatcher.",
            },
            "items": {
                "type": "array",
                "description": "Complete current list of items the caller wants to sell.",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "expiration": {"type": "string"},
                    },
                    "required": ["description"],
                },
            },
        },
    },
}

TOOL_FINALIZE_PICKUP = {
    "name": "finalize_pickup",
    "description": (
        "Call this ONLY after you have read back a summary of the full order "
        "(name, address, items with quantities/expirations, pickup date/window) "
        "and the caller has explicitly confirmed it is correct. This creates the "
        "draft order for the dispatch team."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

TOOL_SEND_WEBSITE_LINK = {
    "name": "send_website_link",
    "description": "Send the caller a text message with a direct link to the website's pickup request page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "phone": {
                "type": "string",
                "description": "Phone number to text. If not provided, the number the caller is dialing from is used.",
            }
        },
    },
}

TOOL_SWITCH_TO_PICKUP = {
    "name": "switch_to_pickup_flow",
    "description": "Call this when the caller wants you to just collect their pickup info over the phone instead of using the website themselves.",
    "input_schema": {"type": "object", "properties": {}},
}

PICKUP_TOOLS = [
    TOOL_UPDATE_PICKUP_INFO,
    TOOL_FINALIZE_PICKUP,
    TOOL_SET_LANGUAGE,
    TOOL_TRANSFER,
    TOOL_END_CALL,
]

WEBHELP_TOOLS = [
    TOOL_SEND_WEBSITE_LINK,
    TOOL_SWITCH_TO_PICKUP,
    TOOL_SET_LANGUAGE,
    TOOL_TRANSFER,
    TOOL_END_CALL,
]


# ---------------------------------------------------------------------------
# Tool execution (side effects)
# ---------------------------------------------------------------------------

def _apply_tool(name: str, tool_input: dict, session: dict, call_sid: str, caller_number: str, flags: dict):
    if name == "update_pickup_info":
        collected = session.setdefault("collected", {})
        for key in ("full_name", "phone", "address", "pickup_date", "pickup_window", "photo_provided", "extra_notes"):
            if key in tool_input:
                collected[key] = tool_input[key]
        if "items" in tool_input:
            session["items"] = tool_input["items"]

    elif name == "finalize_pickup":
        collected = session.get("collected", {})
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
            "call_sid": call_sid,
        }
        result = detrack_client.create_draft_collection(order)
        session["finalized"] = True
        session["finalize_result"] = result
        flags["finalized"] = True
        if not result.get("ok"):
            logger.error("Detrack draft creation failed for call %s: %s", call_sid, result.get("error"))
            sms_client.alert_dispatch_failure(order, result.get("error", "unknown error"))

    elif name == "set_language":
        lang = tool_input.get("language")
        if lang in ("en", "es"):
            session["language"] = lang

    elif name == "transfer_to_representative":
        flags["transfer_requested"] = True

    elif name == "end_call":
        flags["end_call"] = True

    elif name == "send_website_link":
        phone = tool_input.get("phone") or caller_number
        ok = sms_client.send_pickup_form_link(phone, session.get("language", "en"))
        flags["sms_sent"] = ok

    elif name == "switch_to_pickup_flow":
        session["flow"] = "pickup"
        flags["flow_switched_to"] = "pickup"

    else:
        logger.warning("Unknown tool called by Claude: %s", name)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def converse(session: dict, user_text: str, call_sid: str, caller_number: str) -> tuple[str, dict]:
    """
    Run one turn of conversation.

    Returns (reply_text, flags) where flags may contain:
      - finalized: bool
      - transfer_requested: bool
      - end_call: bool
      - sms_sent: bool
      - flow_switched_to: str
    """
    flags: dict = {}

    if session.get("collected", {}).get("phone") is None:
        session.setdefault("collected", {})["phone"] = caller_number

    session["messages"].append({"role": "user", "content": user_text})

    flow = session.get("flow", "pickup")
    if flow == "webhelp":
        system_prompt = prompts.webhelp_system_prompt(session)
        tools = WEBHELP_TOOLS
    else:
        system_prompt = prompts.pickup_system_prompt(session)
        tools = PICKUP_TOOLS

    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.CLAUDE_MAX_TOKENS,
            system=system_prompt,
            messages=session["messages"],
            tools=tools,
        )
    except Exception:
        logger.exception("Claude API call failed for call %s", call_sid)
        session["messages"].pop()  # don't keep a dangling user message
        fallback = (
            "I'm sorry, I'm having trouble right now. Let me connect you with a "
            "representative."
            if session.get("language", "en") == "en"
            else "Lo siento, estoy teniendo problemas. Le voy a comunicar con un representante."
        )
        flags["transfer_requested"] = True
        return fallback, flags

    reply_text_parts = []
    assistant_content = []

    for block in response.content:
        if block.type == "text":
            reply_text_parts.append(block.text)
            assistant_content.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            assistant_content.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            )
            _apply_tool(block.name, block.input, session, call_sid, caller_number, flags)
            # If switching flows, the flow has changed but the conversation
            # transcript is shared so Claude keeps context; the next turn
            # will use the new system prompt.

    session["messages"].append({"role": "assistant", "content": assistant_content})

    reply_text = " ".join(p.strip() for p in reply_text_parts if p.strip())
    if not reply_text:
        # Claude only called tools with no spoken text (shouldn't normally
        # happen given our prompt, but guard against dead air).
        reply_text = (
            "Got it, one moment."
            if session.get("language", "en") == "en"
            else "Entendido, un momento."
        )

    session["turns"] = session.get("turns", 0) + 1
    return reply_text, flags
