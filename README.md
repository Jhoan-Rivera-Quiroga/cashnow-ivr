# Cash Now Test Strips - Inbound Call IVR

An AI phone agent for **(602) 800-9040**. When someone calls to sell
diabetic supplies, this app:

1. **Schedules a pickup** - has a natural conversation to collect the
   caller's name, phone, address, items (with quantity + expiration date),
   and preferred pickup time, then creates a **draft Collection job in
   Detrack** for your team to review and dispatch.
2. **Helps with the website** - walks the caller step-by-step through
   placing their own request on cashnowteststrips.com, can text them the
   link, or switch into option 1 and do it for them.
3. **Transfers to a live rep** - if the caller asks for a person, and it's
   within business hours; otherwise explains your hours and offers options
   1/2 instead.

The conversation is powered by Claude (Anthropic) and works in **English and
Spanish**.

---

## How it works (architecture)

```
Caller dials (602) 800-9040
        |
        v
  Twilio phone number  ---webhook--->  This Flask app (Railway/Render/etc.)
        |                                     |
        |  <Gather> speech/DTMF               |---> Claude (Anthropic API)
        |  <Say> text-to-speech               |       - drives the conversation
        |  <Dial> to live rep                 |       - calls "tools" to save data
        v                                      |---> Detrack API (draft Collection job)
   Caller hears responses                      |---> Twilio SMS (website link, alerts)
```

Each time the caller finishes speaking, Twilio POSTs the transcript to this
app. The app sends the conversation so far to Claude, which replies with
what to say next AND (behind the scenes) calls "tools" to save information
or trigger actions - all in a single API call per turn, to keep the
conversation snappy.

---

## 1. Twilio setup

### Get your phone number working

You said (602) 800-9040 is a real number you use today. You have two paths:

**Option A - Port the number into Twilio (recommended long-term)**
This makes Twilio the carrier for the number. In the Twilio Console go to
**Phone Numbers → Port In**, and follow the wizard. This takes several days
and requires your current carrier's account info.

**Option B - Forward calls to a Twilio number (fastest to get started)**
1. Buy a new Twilio number (any area code is fine - it never has to be
   user-facing).
2. From wherever (602) 800-9040 currently lives - Zoom Phone, a cell
   carrier, etc. - set up **unconditional call forwarding** to the new
   Twilio number's full E.164 number (e.g. `+16025550000`).
3. Update `TWILIO_MAIN_NUMBER` in your environment to the **original**
   number `+16028009040` (this is only used for the "text us a photo"
   instructions and outgoing SMS "From" - if you forward calls, texts to
   602-800-9040 won't reach Twilio unless you also forward/port SMS; see
   note below).

> **Note on SMS**: The bot offers to text the caller a link, and texts you
> an alert if a Detrack draft fails to save. These messages are sent
> **from** `TWILIO_MAIN_NUMBER`. If you go with Option B and 602-800-9040
> isn't on Twilio, set `TWILIO_MAIN_NUMBER` to your new Twilio number
> instead - update the "text us a photo" wording in `prompts.py`
> accordingly, or simply mention texting photos to whatever number shows up
> on the caller's phone as the caller ID.

### Configure the webhook

Once deployed (see Section 3), go to your Twilio number's configuration page
and set:

- **A call comes in** → Webhook → `https://YOUR-APP-URL/voice` → HTTP POST

That's the only webhook you need to set manually - every other route
(`/menu`, `/converse`, `/transfer`, `/transfer-status`) is reached via
`<Redirect>`/`<Gather action=...>`/`<Dial action=...>` from `/voice`.

---

## 2. Zoom Phone (Option 3 - live transfer)

You mentioned you're not sure whether you have Zoom Phone IVR. **You don't
need it** - this app *is* the IVR. All you need from Zoom (or wherever your
team currently answers calls) is **one phone number Twilio can dial** when a
caller asks for a representative.

- If your team uses **Zoom Phone**: get the direct E.164 number for the
  person/queue who should receive transferred calls (Zoom Phone numbers
  work fine as a normal PSTN number - Twilio just dials it like any other
  phone number). Put it in `REP_PHONE_NUMBER`.
- If your team uses **cell phones**: just put a cell number in
  `REP_PHONE_NUMBER`.
- You can point `REP_PHONE_NUMBER` at a **Zoom Phone call queue's** number
  too, so it rings whoever's available.

If Zoom Phone *does* have an auto-receptionist/IVR already in front of your
team's numbers, that's fine and unaffected - this app's transfer just dials
that number like any caller would.

---

## 3. Deploying the app

This is a standard Flask app - any host that runs Python works (Railway,
Render, Fly.io, a VPS, etc.). Railway/Render are easiest:

1. Push this folder to a new GitHub repo.
2. On Railway/Render, create a new **Web Service** from that repo.
3. It will detect `Procfile` and `requirements.txt` automatically
   (`gunicorn app:app`).
4. Set all the environment variables from `.env.example` in the host's
   dashboard (see Section 4 for what each one means).
5. Deploy. You'll get a public URL like `https://cashnow-ivr.up.railway.app`.
6. Use that URL (+ `/voice`) as the Twilio webhook (Section 1).

### Running locally (for testing before you go live)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your real keys
export $(grep -v '^#' .env | xargs)   # load .env into the shell
python app.py
```

To let Twilio reach your laptop, use [ngrok](https://ngrok.com/):
`ngrok http 5000`, then set the Twilio webhook to the ngrok HTTPS URL +
`/voice`. While testing this way, you can set `TWILIO_VALIDATE_SIGNATURE=false`
to skip signature checks if ngrok/Twilio URL mismatches cause 403s - just
remember to set it back to `true` before going live.

---

## 4. Environment variables

See `.env.example` for the full list with comments. The most important ones
to get right before go-live:

| Variable | What it's for |
|---|---|
| `ANTHROPIC_API_KEY` | Powers the conversation. Get one at console.anthropic.com. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | From the Twilio Console. Used for sending SMS and validating webhook signatures. |
| `TWILIO_MAIN_NUMBER` | Used in spoken/SMS text when telling callers what number to text photos to, and as the "From" for SMS. |
| `REP_PHONE_NUMBER` | Where Option 3 transfers go. |
| `DETRACK_API_KEY` | From Detrack → Integrations → API Key. |
| `DETRACK_DRY_RUN` | **Leave as `true` until you've completed Section 5.** |
| `DISPATCH_ALERT_PHONE` | Optional - gets a text if a Detrack draft fails to save, so no order is lost. |
| `BUSINESS_OPEN_TIME` / `BUSINESS_CLOSE_TIME` | Currently `10:00` / `21:30`, every day, Arizona time - matches what you told us. Change anytime without code changes. |

---

## 5. Detrack - verify before going live

You confirmed you have a Detrack API key, but Detrack accounts can have
custom required fields. `detrack_client.py` builds a "Collection" job using
Detrack's documented v2 schema:

```
POST https://app.detrack.com/api/v2/dn/jobs
Header: X-API-KEY: <your key>
Body: {"data": {"type": "Collection", "do_number": ..., "date": ...,
                "deliver_to_collect_from": ..., "phone_number": ...,
                "address": ..., "items": [...], "notes": ..., "status": "info_recv"}}
```

**Before flipping `DETRACK_DRY_RUN` to `false`:**

1. Keep it `true` and run a few test calls (see Section 6). Every "finalized"
   order is appended to `orders_log.jsonl` on the server with the exact
   payload that *would* be sent - review a few of these.
2. In your Detrack dashboard, manually create one "Collection" job and note
   what fields/statuses show up, OR call
   `GET https://app.detrack.com/api/v2/dn/jobs/<id>` with your API key for an
   existing job to see the exact field names your account returns.
3. If anything differs (e.g. your account uses a different status name than
   `info_recv`, or has required custom fields), edit the `_build_payload`
   function in `detrack_client.py` to match.
4. Set `DETRACK_DRY_RUN=false` and do one real end-to-end test call.

Every draft order's notes field starts with:
`*** AI-GENERATED DRAFT - PLEASE REVIEW & CONFIRM PRICING BEFORE DISPATCH ***`
- pricing is intentionally NOT decided by the bot (it depends on condition
and exact expiration, which your team confirms).

---

## 6. Testing the conversation

You can call your Twilio number directly once `/voice` is wired up, in
either English or Spanish (press 9, or just start speaking Spanish).

Things worth testing:
- **Option 1** end to end - give a name, address, a couple of items with
  quantities/expirations, and a pickup time. Confirm the summary, say "yes",
  and check `orders_log.jsonl` on the server for the draft.
- **Option 2** - ask for website help, then mid-way say "actually can you
  just do it for me" and confirm it switches into the pickup flow smoothly.
- **Option 3** - during business hours, confirm it rings `REP_PHONE_NUMBER`;
  outside business hours, confirm it states your hours and offers 1/2.
- **Spanish** - press 9 (or say "español") at the main menu, and confirm the
  whole conversation continues in Spanish with a Spanish voice.
- **Silence/mumbling** - say nothing for a turn; it should ask you to repeat
  once, then offer a transfer if it still can't hear you.

---

## 7. Project structure

```
app.py                 Flask app + Twilio webhook routes (the "phone tree")
claude_agent.py        Claude conversation engine + tool definitions
prompts.py             System prompts for the pickup & webhelp flows
products_catalog.py    Loads/formats data/products.json for Claude's context
data/products.json     ~315 items from your price sheet (name, category,
                        currently-buying flag) - regenerate this if your
                        catalog changes (see below)
detrack_client.py      Builds & sends draft Collection jobs to Detrack
sms_client.py          Sends SMS (website link, dispatch-failure alerts)
session_store.py       Per-call conversation state (in-memory or Redis)
twiml_helpers.py       TwiML builders (Gather/Say/Dial) with EN/ES voices
hours.py               Business-hours check for Option 3
config.py              All settings, read from environment variables
```

### Updating the product catalog

`data/products.json` is a flat list of
`{"name": ..., "category": ..., "currently_buying": true/false}` extracted
from your price sheet. It's only used to give Claude a sense of what you buy
and what you're not currently taking - the bot never quotes prices. To
update it, edit the JSON directly, or re-run a similar extraction against a
new price sheet export.

---

## 8. Scaling notes

- Default `Procfile` runs **1 worker** so the in-memory session store works
  correctly. This comfortably handles far more than 200 calls/day for a
  conversational IVR (each call only needs the worker for the brief moments
  between Twilio webhooks).
- If you need multiple workers/dynos, set `REDIS_URL` so all workers share
  call state - `session_store.py` already supports this, no code changes
  needed.
- Claude API costs: each turn is one API call with a few thousand tokens of
  system prompt + the running transcript. At ~200 calls/day with ~6-8 turns
  each, this is a modest, predictable cost - monitor usage in the Anthropic
  console.

---

## 9. Things you may want to customize

- **Greeting wording** - `MENU_TEXT` in `app.py`.
- **What counts as "pickup" / "website" / "representative" / "Spanish"** in
  speech - the `*_KEYWORDS` lists in `app.py`.
- **Service area list / business description / required fields** -
  `prompts.py`.
- **Hours / days** - `.env` (`BUSINESS_*` variables), no code change needed.
