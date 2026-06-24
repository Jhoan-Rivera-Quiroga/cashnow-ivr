"""
Per-call conversation state.

Twilio sends one HTTP request per "turn" of the conversation (each time the
caller finishes speaking). Flask is stateless between requests, so we need
somewhere to keep:

  - the running transcript we send to Claude (messages list)
  - the structured fields collected so far (name, address, items, etc.)
  - which flow the caller is in (pickup / webhelp / menu)
  - the detected language

Sessions are keyed by Twilio's CallSid, which is stable for the life of a
single phone call.

For a single-worker deployment, the in-memory store is fine. For production
with multiple gunicorn workers, set REDIS_URL so all workers share state.
"""

import json
import threading
import time
from typing import Optional

import config


class InMemorySessionStore:
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def get(self, call_sid: str) -> Optional[dict]:
        with self._lock:
            entry = self._data.get(call_sid)
            if not entry:
                return None
            value, expires_at = entry
            if expires_at < time.time():
                del self._data[call_sid]
                return None
            return json.loads(value)

    def set(self, call_sid: str, session: dict, ttl: int = None):
        ttl = ttl or config.SESSION_TTL_SECONDS
        with self._lock:
            self._data[call_sid] = (json.dumps(session), time.time() + ttl)

    def delete(self, call_sid: str):
        with self._lock:
            self._data.pop(call_sid, None)


class RedisSessionStore:
    def __init__(self, redis_url: str):
        import redis  # imported lazily so redis isn't a hard dependency

        self._client = redis.from_url(redis_url)

    def get(self, call_sid: str) -> Optional[dict]:
        raw = self._client.get(f"ivr:session:{call_sid}")
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, call_sid: str, session: dict, ttl: int = None):
        ttl = ttl or config.SESSION_TTL_SECONDS
        self._client.set(f"ivr:session:{call_sid}", json.dumps(session), ex=ttl)

    def delete(self, call_sid: str):
        self._client.delete(f"ivr:session:{call_sid}")


def _build_store():
    if config.REDIS_URL:
        return RedisSessionStore(config.REDIS_URL)
    return InMemorySessionStore()


_store = _build_store()


def get_session(call_sid: str) -> dict:
    """Return the session for this call, creating a fresh one if needed."""
    session = _store.get(call_sid)
    if session is None:
        session = {
            "flow": "menu",       # menu | pickup | webhelp | transfer
            "language": "en",     # en | es
            "messages": [],       # Claude conversation transcript
            "collected": {},      # structured fields gathered so far
            "items": [],          # list of items the caller wants to sell
            "finalized": False,
            "turns": 0,
        }
    return session


def save_session(call_sid: str, session: dict):
    _store.set(call_sid, session)


def clear_session(call_sid: str):
    _store.delete(call_sid)
