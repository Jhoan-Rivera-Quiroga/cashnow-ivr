"""
Central configuration for the Cash Now Test Strips voice IVR.

Everything here is read from environment variables so the same code can run
locally (with a .env file) and in production (Railway / Render / etc.) without
any changes. See .env.example for the full list of variables.
"""

import os
from zoneinfo import ZoneInfo


def _bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "1024"))

# ---------------------------------------------------------------------------
# Twilio
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
# The Cash Now Twilio number that customers call (E.164 format, e.g. +16028009040)
TWILIO_MAIN_NUMBER = os.environ.get("TWILIO_MAIN_NUMBER", "+16028009040")
# Set to "true" while testing so Twilio webhook signature validation is skipped
TWILIO_VALIDATE_SIGNATURE = _bool("TWILIO_VALIDATE_SIGNATURE", "true")

# ---------------------------------------------------------------------------
# Live representative transfer (Option 3)
# ---------------------------------------------------------------------------
# Number to ring for a live rep. This can be a Zoom Phone DID, a Zoom Phone
# call queue number, or a personal cell - anything Twilio can dial.
REP_PHONE_NUMBER = os.environ.get("REP_PHONE_NUMBER", "")
# How long (seconds) to ring the rep before giving up
REP_DIAL_TIMEOUT = int(os.environ.get("REP_DIAL_TIMEOUT", "20"))

# ---------------------------------------------------------------------------
# Business hours (Option 3 availability)
# ---------------------------------------------------------------------------
BUSINESS_TZ = ZoneInfo(os.environ.get("BUSINESS_TZ", "America/Phoenix"))
# 24h "HH:MM" strings
BUSINESS_OPEN_TIME = os.environ.get("BUSINESS_OPEN_TIME", "10:00")
BUSINESS_CLOSE_TIME = os.environ.get("BUSINESS_CLOSE_TIME", "21:30")
# Days the rep line is staffed: 0=Mon ... 6=Sun. Default = every day.
BUSINESS_DAYS = [int(d) for d in os.environ.get("BUSINESS_DAYS", "0,1,2,3,4,5,6").split(",")]

# ---------------------------------------------------------------------------
# Detrack
# ---------------------------------------------------------------------------
DETRACK_API_KEY = os.environ.get("DETRACK_API_KEY", "")
DETRACK_BASE_URL = os.environ.get("DETRACK_BASE_URL", "https://app.detrack.com/api/v2")
# When true, no real API call is made - the payload is only logged/saved.
# Use this until the Detrack field-mapping below is confirmed against the
# real account.
DETRACK_DRY_RUN = _bool("DETRACK_DRY_RUN", "true")

# ---------------------------------------------------------------------------
# Company info / links used by the bot
# ---------------------------------------------------------------------------
COMPANY_NAME = os.environ.get("COMPANY_NAME", "Cash Now Test Strips")
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://www.cashnowteststrips.com")
WEBSITE_SELL_URL = os.environ.get("WEBSITE_SELL_URL", "https://www.cashnowteststrips.com/collections/all-products")
WEBSITE_PICKUP_FORM_URL = os.environ.get(
    "WEBSITE_PICKUP_FORM_URL",
    "https://www.cashnowteststrips.com/pages/local-pickups-request-form",
)
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@cashnowteststrips.com")

# Internal alert number/email - where a notification goes if Detrack creation
# fails so a human can create the job manually (no lead is ever silently lost)
DISPATCH_ALERT_PHONE = os.environ.get("DISPATCH_ALERT_PHONE", "")

# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------
# Webhook URL for the channel that receives caller escalation alerts.
# Override via DISCORD_WEBHOOK_URL env var in Render (recommended — keep this
# URL out of git history once you have it set in Render).
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# ---------------------------------------------------------------------------
# Session storage
# ---------------------------------------------------------------------------
# Optional. If set, sessions are stored in Redis (recommended for production
# with >1 worker process). If empty, an in-memory store is used - fine for a
# single worker / local testing.
REDIS_URL = os.environ.get("REDIS_URL", "")
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "3600"))

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
PORT = int(os.environ.get("PORT", "5000"))
DEBUG = _bool("FLASK_DEBUG", "false")
