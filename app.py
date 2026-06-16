"""
Cash Now Test Strips - Inbound Call IVR

Flask app exposing the Twilio Voice webhooks for (602) 800-9040:

  POST /voice            - entry point, plays the main menu
  POST /menu             - routes the caller's menu choice
  POST /converse         - multi-turn Claude conversation (pickup or webhelp)
  POST /transfer         - Option 3: live rep transfer (business-hours aware)
  POST /transfer-status  - <Dial> action callback (rep didn't answer, etc.)
  GET  /health           - simple health check for the hosting platform

See README.md for Twilio configuration and deployment instructions.
"""

import logging
from functools import wraps

from flask import Flask, request, abort
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

import claude_agent
import config
import hours
import twiml_helpers
from session_store import get_session, save_session, clear_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Twilio request signature validation
# ---------------------------------------------------------------------------

def validate_twilio_request(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config.TWILIO_VALIDATE_SIGNATURE:
            return f(*args, **kwargs)

        validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
        signature = request.headers.get("X-Twilio-Signature", "")
        url = request.url
        # Most hosting platforms terminate TLS at a proxy and forward to
        # Flask over plain HTTP - reconstruct the public HTTPS URL so the
        # signature (computed by Twilio against the HTTPS URL) matches.
        if request.headers.get("X-Forwarded-Proto", "").lower() == "https" and url.startswith("http://"):
            url = "https://" + url[len("http://"):]

        if not validator.validate(url, request.form, signature):
            logger.warning("Invalid Twilio signature for %s", url)
            abort(403)
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Menu copy (English / Spanish)
# ---------------------------------------------------------------------------

MENU_HINTS = (
    "schedule a pickup, sell my test strips, sell diabetic supplies, "
    "website, order online, representative, agent, espanol, spanish"
)

MENU_TEXT = {
    "en": (
        "Thanks for calling Cash Now Test Strips! If you have diabetic "
        "supplies to sell and would like to schedule a pickup, press 1, or "
        "just tell me. For help ordering on our website, press 2. To speak "
        "with a representative, press 3. Para espanol, oprima 9."
    ),
    "es": (
        "Gracias por llamar a Cash Now Test Strips. Si tiene articulos "
        "diabeticos para vender y quiere agendar una recogida, oprima 1 o "
        "digamelo. Para ayuda con su pedido en el sitio web, oprima 2. Para "
        "hablar con un representante, oprima 3."
    ),
}

RETRY_PREFIX = {
    "en": "Sorry, I didn't catch that. ",
    "es": "Lo siento, no le entendi. ",
}

KICKOFF_PICKUP = {
    "en": (
        "(The caller chose to schedule a pickup to sell diabetic supplies. "
        "Greet them briefly in one short sentence and ask for their full "
        "name to begin.)"
    ),
    "es": (
        "(El cliente eligio agendar una recogida para vender articulos "
        "diabeticos. Saludelo brevemente en una oracion corta y pidale su "
        "nombre completo para comenzar.)"
    ),
}

KICKOFF_WEBHELP = {
    "en": (
        "(The caller chose to get help ordering on the website. Greet them "
        "briefly in one short sentence and start guiding them through step "
        "1.)"
    ),
    "es": (
        "(El cliente eligio recibir ayuda para hacer su pedido en el sitio "
        "web. Saludelo brevemente en una oracion corta y empiece a guiarlo "
        "con el primer paso.)"
    ),
}

PICKUP_KEYWORDS = [
    "sell", "pickup", "pick up", "schedule", "appointment", "buy", "cash",
    "vender", "recoger", "recogida", "cita", "venta", "comprar",
]
WEBHELP_KEYWORDS = [
    "website", "online", "web", "order online", "site", "internet",
    "pagina", "sitio",
]
TRANSFER_KEYWORDS = [
    "representative", "agent", "human", "person", "operator", "someone",
    "representante", "persona", "agente", "alguien", "operador",
]
SPANISH_KEYWORDS = ["espanol", "español", "spanish"]


def _classify_menu_choice(digits: str, speech: str):
    speech_l = speech.lower()
    if digits == "9" or any(k in speech_l for k in SPANISH_KEYWORDS):
        return "spanish"
    if digits == "1" or any(k in speech_l for k in PICKUP_KEYWORDS):
        return "pickup"
    if digits == "2" or any(k in speech_l for k in WEBHELP_KEYWORDS):
        return "webhelp"
    if digits == "3" or any(k in speech_l for k in TRANSFER_KEYWORDS):
        return "transfer"
    return None


def _menu_gather(session: dict, retry: bool = False):
    language = session.get("language", "en")
    text = MENU_TEXT[language]
    if retry:
        text = RETRY_PREFIX[language] + text
    return twiml_helpers.gather_response(text, "/menu", language, hints=MENU_HINTS, num_digits=1, timeout=6)


def _respond_from_flags(reply_text: str, flags: dict, session: dict, call_sid: str):
    language = session.get("language", "en")

    if flags.get("transfer_requested"):
        save_session(call_sid, session)
        return str(twiml_helpers.say_and_redirect(reply_text, "/transfer", language))

    if flags.get("end_call"):
        clear_session(call_sid)
        return str(twiml_helpers.say_and_hangup(reply_text, language))

    save_session(call_sid, session)
    return str(twiml_helpers.gather_response(reply_text, "/converse", language, timeout=8))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


@app.route("/voice", methods=["POST"])
@validate_twilio_request
def voice():
    call_sid = request.form["CallSid"]
    clear_session(call_sid)  # fresh state for every new call
    session = get_session(call_sid)
    save_session(call_sid, session)
    return str(_menu_gather(session))


@app.route("/menu", methods=["POST"])
@validate_twilio_request
def menu():
    call_sid = request.form["CallSid"]
    from_number = request.form.get("From", "")
    digits = request.form.get("Digits", "")
    speech = request.form.get("SpeechResult", "")

    session = get_session(call_sid)
    choice = _classify_menu_choice(digits, speech)

    if choice == "spanish":
        session["language"] = "es"
        save_session(call_sid, session)
        return str(_menu_gather(session))

    if choice == "pickup":
        session["flow"] = "pickup"
        kickoff = KICKOFF_PICKUP[session.get("language", "en")]
        reply_text, flags = claude_agent.converse(session, kickoff, call_sid, from_number)
        return _respond_from_flags(reply_text, flags, session, call_sid)

    if choice == "webhelp":
        session["flow"] = "webhelp"
        kickoff = KICKOFF_WEBHELP[session.get("language", "en")]
        reply_text, flags = claude_agent.converse(session, kickoff, call_sid, from_number)
        return _respond_from_flags(reply_text, flags, session, call_sid)

    if choice == "transfer":
        save_session(call_sid, session)
        return str(twiml_helpers.say_and_redirect("", "/transfer", session.get("language", "en")))

    # Unclear input - retry once, then fall back to a live transfer
    session["menu_retries"] = session.get("menu_retries", 0) + 1
    if session["menu_retries"] >= 2:
        save_session(call_sid, session)
        return str(twiml_helpers.say_and_redirect("", "/transfer", session.get("language", "en")))

    save_session(call_sid, session)
    return str(_menu_gather(session, retry=True))


@app.route("/converse", methods=["POST"])
@validate_twilio_request
def converse():
    call_sid = request.form["CallSid"]
    from_number = request.form.get("From", "")
    digits = request.form.get("Digits", "")
    speech = request.form.get("SpeechResult", "")

    session = get_session(call_sid)
    language = session.get("language", "en")

    user_text = speech or (f"(caller pressed {digits} on the keypad)" if digits else "")

    if not user_text:
        session["empty_count"] = session.get("empty_count", 0) + 1
        if session["empty_count"] >= 2:
            save_session(call_sid, session)
            text = (
                "I'm having trouble hearing you. Let me connect you with a representative."
                if language == "en"
                else "Tengo problemas para escucharle. Le voy a comunicar con un representante."
            )
            return str(twiml_helpers.say_and_redirect(text, "/transfer", language))

        save_session(call_sid, session)
        retry_text = RETRY_PREFIX[language] + (
            "Could you say that again?" if language == "en" else "Puede repetirlo?"
        )
        return str(twiml_helpers.gather_response(retry_text, "/converse", language, timeout=8))

    session["empty_count"] = 0
    reply_text, flags = claude_agent.converse(session, user_text, call_sid, from_number)
    return _respond_from_flags(reply_text, flags, session, call_sid)


@app.route("/transfer", methods=["POST"])
@validate_twilio_request
def transfer():
    call_sid = request.form["CallSid"]
    session = get_session(call_sid)
    language = session.get("language", "en")

    if hours.is_open() and config.REP_PHONE_NUMBER:
        say_text = (
            "One moment, connecting you with a representative."
            if language == "en"
            else "Un momento, le voy a comunicar con un representante."
        )
        save_session(call_sid, session)
        return str(
            twiml_helpers.dial_representative(
                say_text, config.REP_PHONE_NUMBER, config.REP_DIAL_TIMEOUT, "/transfer-status", language
            )
        )

    offer_text = {
        "en": " I can still help you schedule a pickup for your items, or help you order on our website right now. Press 1 to schedule a pickup, or press 2 for website help.",
        "es": " Aun le puedo ayudar a agendar una recogida para sus articulos, o ayudarle con su pedido en el sitio web ahora mismo. Oprima 1 para agendar una recogida, o oprima 2 para ayuda con el sitio web.",
    }
    msg = hours.hours_message(language) + offer_text[language]
    save_session(call_sid, session)
    return str(twiml_helpers.gather_response(msg, "/menu", language, hints=MENU_HINTS, num_digits=1, timeout=8))


@app.route("/transfer-status", methods=["POST"])
@validate_twilio_request
def transfer_status():
    call_sid = request.form["CallSid"]
    session = get_session(call_sid)
    language = session.get("language", "en")
    status = request.form.get("DialCallStatus", "")

    if status == "completed":
        clear_session(call_sid)
        return str(VoiceResponse())

    apology = {
        "en": "Sorry, no one is available right now.",
        "es": "Lo siento, no hay nadie disponible en este momento.",
    }
    offer_text = {
        "en": " I can help you schedule a pickup for your items, or help you order on our website. Press 1 to schedule a pickup, or press 2 for website help.",
        "es": " Le puedo ayudar a agendar una recogida para sus articulos, o ayudarle con su pedido en el sitio web. Oprima 1 para agendar una recogida, o oprima 2 para ayuda con el sitio web.",
    }
    msg = apology[language] + offer_text[language]
    save_session(call_sid, session)
    return str(twiml_helpers.gather_response(msg, "/menu", language, hints=MENU_HINTS, num_digits=1, timeout=8))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
