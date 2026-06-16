"""
Small helper around the Twilio REST client for sending SMS messages:
  - the website pickup-form link (Option 2)
  - an internal alert if Detrack draft creation fails (so no lead is lost)
"""

import logging

from twilio.rest import Client

import config

logger = logging.getLogger(__name__)

_client = None
if config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN:
    _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)


def _send(to: str, body: str) -> bool:
    if not _client:
        logger.warning("Twilio credentials not configured - SMS not sent. Would have sent to %s: %s", to, body)
        return False
    try:
        _client.messages.create(to=to, from_=config.TWILIO_MAIN_NUMBER, body=body)
        return True
    except Exception:
        logger.exception("Failed to send SMS to %s", to)
        return False


def send_pickup_form_link(to: str, language: str = "en") -> bool:
    if language == "es":
        body = (
            f"{config.COMPANY_NAME}: Aqui esta el enlace para vender tus articulos "
            f"y agendar tu recogida: {config.WEBSITE_PICKUP_FORM_URL}"
        )
    else:
        body = (
            f"{config.COMPANY_NAME}: Here's the link to sell your items and "
            f"request a pickup online: {config.WEBSITE_PICKUP_FORM_URL}"
        )
    return _send(to, body)


def alert_dispatch_failure(order: dict, error: str) -> bool:
    if not config.DISPATCH_ALERT_PHONE:
        logger.warning("DISPATCH_ALERT_PHONE not set - skipping failure alert. Order: %s", order)
        return False
    body = (
        f"CashNow IVR: Detrack draft creation FAILED ({error}). "
        f"Caller {order.get('name')} / {order.get('phone')} at {order.get('address')}. "
        f"Check orders_log.jsonl on the server for full details (call {order.get('call_sid')})."
    )
    return _send(config.DISPATCH_ALERT_PHONE, body)
