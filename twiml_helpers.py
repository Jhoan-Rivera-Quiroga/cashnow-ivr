"""
Small helpers for building Twilio TwiML responses, with English/Spanish
voice + speech-recognition language switching based on session["language"].
"""

from twilio.twiml.voice_response import VoiceResponse, Gather, Dial

VOICES = {
    "en": {"say_voice": "Polly.Joanna-Neural", "say_lang": "en-US", "gather_lang": "en-US"},
    "es": {"say_voice": "Polly.Lupe-Neural", "say_lang": "es-US", "gather_lang": "es-US"},
}

NO_INPUT_TEXT = {
    "en": "Sorry, I didn't catch that.",
    "es": "Lo siento, no le escuche.",
}

GOODBYE_TEXT = {
    "en": "Thanks for calling. Goodbye!",
    "es": "Gracias por llamar. Adios!",
}


def _voices(language: str) -> dict:
    return VOICES.get(language, VOICES["en"])


def gather_response(
    say_text: str,
    action_url: str,
    language: str = "en",
    hints: str | None = None,
    timeout: int = 6,
    num_digits: int | None = None,
) -> VoiceResponse:
    """
    <Gather> that speaks `say_text`, then posts the result (speech or DTMF)
    to `action_url`. actionOnEmptyResult ensures we get a callback even if
    the caller says nothing, so our handler can decide whether to re-prompt,
    transfer, or hang up.
    """
    vr = VoiceResponse()
    v = _voices(language)

    gather_kwargs = dict(
        input="speech dtmf",
        action=action_url,
        method="POST",
        timeout=timeout,
        speech_timeout="auto",
        language=v["gather_lang"],
        action_on_empty_result=True,
    )
    if num_digits:
        gather_kwargs["num_digits"] = num_digits
    if hints:
        gather_kwargs["hints"] = hints

    gather = Gather(**gather_kwargs)
    gather.say(say_text, voice=v["say_voice"], language=v["say_lang"])
    vr.append(gather)

    # Only reached if Twilio itself fails to invoke the action (rare).
    vr.redirect(action_url, method="POST")
    return vr


def say_and_redirect(say_text: str, redirect_url: str, language: str = "en") -> VoiceResponse:
    vr = VoiceResponse()
    v = _voices(language)
    if say_text:
        vr.say(say_text, voice=v["say_voice"], language=v["say_lang"])
    vr.redirect(redirect_url, method="POST")
    return vr


def say_and_hangup(say_text: str, language: str = "en") -> VoiceResponse:
    vr = VoiceResponse()
    v = _voices(language)
    if say_text:
        vr.say(say_text, voice=v["say_voice"], language=v["say_lang"])
    vr.say(GOODBYE_TEXT.get(language, GOODBYE_TEXT["en"]), voice=v["say_voice"], language=v["say_lang"])
    vr.hangup()
    return vr


def dial_representative(say_text: str, rep_number: str, timeout: int, action_url: str, language: str = "en") -> VoiceResponse:
    vr = VoiceResponse()
    v = _voices(language)
    if say_text:
        vr.say(say_text, voice=v["say_voice"], language=v["say_lang"])
    dial = Dial(timeout=timeout, action=action_url, method="POST")
    dial.number(rep_number)
    vr.append(dial)
    return vr
