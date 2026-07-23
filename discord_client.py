"""
Posts caller escalation alerts to a Discord channel via webhook.
Called when a caller's request is too complex for the AI agent to handle.
"""

import logging
from datetime import datetime

import requests

import config

logger = logging.getLogger(__name__)


def send_escalation(caller_number: str, caller_request: str) -> bool:
    """
    Post a callback request card to the configured Discord channel.
    Returns True on success, False on any failure.
    """
    if not config.DISCORD_WEBHOOK_URL:
        logger.warning(
            "DISCORD_WEBHOOK_URL not set — escalation not delivered. Request: %s",
            caller_request,
        )
        return False

    now = datetime.now(config.BUSINESS_TZ)
    timestamp = now.strftime("%B %d, %Y %I:%M %p %Z")

    payload = {
        "embeds": [
            {
                "title": "📞 New Callback Request",
                "color": 0xE8A320,
                "fields": [
                    {
                        "name": "From",
                        "value": caller_number or "Unknown",
                        "inline": True,
                    },
                    {
                        "name": "Time",
                        "value": timestamp,
                        "inline": True,
                    },
                    {
                        "name": "Request",
                        "value": caller_request or "(no details provided)",
                        "inline": False,
                    },
                ],
            }
        ]
    }

    try:
        resp = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if resp.status_code in (200, 204):
            logger.info("Discord escalation sent for %s", caller_number)
            return True
        logger.error(
            "Discord webhook returned %s: %s", resp.status_code, resp.text
        )
        return False
    except requests.RequestException:
        logger.exception("Failed to reach Discord webhook for %s", caller_number)
        return False
