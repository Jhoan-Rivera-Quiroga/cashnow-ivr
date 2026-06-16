"""
Business-hours check for the live-representative transfer (Option 3).
"""

from datetime import datetime, time as dtime

import config


def is_open(now: datetime | None = None) -> bool:
    now = now or datetime.now(config.BUSINESS_TZ)
    if now.weekday() not in config.BUSINESS_DAYS:
        return False
    open_t = dtime.fromisoformat(config.BUSINESS_OPEN_TIME)
    close_t = dtime.fromisoformat(config.BUSINESS_CLOSE_TIME)
    return open_t <= now.time() <= close_t


def _fmt(t_str: str) -> str:
    h, m = (int(x) for x in t_str.split(":"))
    period = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {period}" if m else f"{h12} {period}"


def hours_message(language: str = "en") -> str:
    open_str = _fmt(config.BUSINESS_OPEN_TIME)
    close_str = _fmt(config.BUSINESS_CLOSE_TIME)
    if language == "es":
        return (
            f"Nuestros representantes estan disponibles de {open_str} a "
            f"{close_str}, hora de Arizona, los siete dias de la semana."
        )
    return (
        f"Our representatives are available from {open_str} to {close_str} "
        f"Arizona time, seven days a week."
    )
