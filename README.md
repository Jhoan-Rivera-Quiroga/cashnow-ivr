# Cash Now Test Strips — Inbound Call IVR (Vapi AI)

An AI phone agent for **(602) 800-9040** powered by **Vapi AI** (voice layer)
and **Claude** (conversation). When someone calls to sell diabetic supplies,
the agent:

1. Schedules a draft pickup order (name, address, items, preferred time)
2. Walks callers through the website to place their own request
3. Transfers to a live representative during business hours

Works in **English and Spanish**.

---

## Architecture

```
Caller dials (480) 690-3536
        |
        | call-forwarded to
        v
Twilio number +16029058480  ---->  Vapi AI (handles voice)
                                        |
                                        |--- Claude (conversation brain)
                                        |--- ElevenLabs (human-like voice)
                                        |--- Deepgram (speech recognition)
                                        |
                                        |-- tool call webhooks -->  This Flask app (Render)
                                                                         |
                                                                         |---> Detrack API
                                                                         |---> Twilio SMS
```

**Vapi** owns the call: it does speech-to-text, runs Claude, and speaks
responses back via text-to-speech. When Claude calls a "tool" (save order,
send SMS, etc.), Vapi POSTs to this Flask app on Render.

---

## Files

```
app.py               Vapi tool webhook server (the only voice-related code left)
config.py            All settings from environment variables
detrack_client.py    Creates draft Collection jobs in Detrack
sms_client.py        Sends SMS (website link, dispatch-failure alerts)
hours.py             Business-hours check for live rep availability
products_catalog.py  Loads data/products.json for the system prompt
data/products.json   ~315 items with currently-buying flags
Procfile             Tells Render how to start the app (gunicorn)
requirements.txt     Python dependencies
```

Files no longer used by the app (kept for reference / rollback):
`claude_agent.py`, `twiml_helpers.py`, `session_store.py`, `prompts.py`

---

## Deployment — Complete Step-by-Step

---

### Step 1: Render — Deploy the Webhook Server

The Flask app on Render handles tool calls from Vapi. It must be deployed
and running before you configure Vapi.

#### 1a. Push code to GitHub (if not already done)

```powershell
cd "C:\Users\user\OneDrive\Escritorio\cashnow_ivr\cashnow_ivr"
git add .
git commit -m "Migrate to Vapi AI"
git push
```

Render deploys automatically when GitHub is updated.

#### 1b. Environment variables in Render

Go to your Render service → **Environment** tab. Keep or add these variables.
Remove any that are no longer needed (marked below).

| Variable | Value | Status |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | your Twilio SID | keep |
| `TWILIO_AUTH_TOKEN` | your Twilio token | keep |
| `TWILIO_MAIN_NUMBER` | `+16029058480` | keep (used for outbound SMS "From") |
| `DETRACK_API_KEY` | your Detrack key | keep |
| `DETRACK_DRY_RUN` | `true` (until verified) | keep |
| `DETRACK_BASE_URL` | `https://app.detrack.com/api/v2` | keep |
| `DISPATCH_ALERT_PHONE` | `+16029058480` | keep |
| `COMPANY_NAME` | `Cash Now Test Strips` | keep |
| `WEBSITE_URL` | `https://www.cashnowteststrips.com` | keep |
| `WEBSITE_SELL_URL` | `https://www.cashnowteststrips.com/collections/all-products` | keep |
| `WEBSITE_PICKUP_FORM_URL` | `https://www.cashnowteststrips.com/pages/local-pickups-request-form` | keep |
| `SUPPORT_EMAIL` | `support@cashnowteststrips.com` | keep |
| `BUSINESS_TZ` | `America/Phoenix` | keep |
| `BUSINESS_OPEN_TIME` | `10:00` | keep |
| `BUSINESS_CLOSE_TIME` | `21:30` | keep |
| `BUSINESS_DAYS` | `0,1,2,3,4,5,6` | keep |
| `SESSION_TTL_SECONDS` | `3600` | keep |
| `PORT` | `5000` | keep |
| `FLASK_DEBUG` | `false` | keep |
| `ANTHROPIC_API_KEY` | — | **remove** (Vapi handles Claude directly) |
| `CLAUDE_MODEL` | — | **remove** (set in Vapi dashboard) |
| `CLAUDE_MAX_TOKENS` | — | **remove** (set in Vapi dashboard) |
| `TWILIO_VALIDATE_SIGNATURE` | — | **remove** (no more Twilio voice webhooks) |
| `REP_PHONE_NUMBER` | — | **remove** (set in Vapi dashboard) |
| `REP_DIAL_TIMEOUT` | — | **remove** (set in Vapi dashboard) |

#### 1c. Confirm the webhook server is running

Visit `https://YOUR-RENDER-URL.onrender.com/health` in a browser.
You should see: `{"status": "ok"}`

Keep your Render URL handy — you will paste it into Vapi in Step 2g.

---

### Step 2: Vapi — Create the AI Assistant

#### 2a. Create a Vapi account

Go to **vapi.ai** → Sign Up. Vapi has a free trial with included minutes.
Paid usage is billed per minute of call time (~$0.05–$0.15/min depending
on voice and model).

#### 2b. Add your Anthropic API key to Vapi

1. In the Vapi dashboard, go to **Settings** (bottom left) → **Provider Keys**
2. Find **Anthropic** → click **+ Add Key**
3. Paste your Anthropic API key (starts with `sk-ant-api03-`)
4. Save

This lets Vapi use Claude as the conversation model on your behalf.

#### 2c. Create the assistant

1. Go to **Assistants** (left sidebar) → **+ Create Assistant**
2. Choose **Blank Assistant**
3. Name it: `Cash Now IVR`

#### 2d. Configure the model

In the assistant editor:

1. Under **Model**, select **Anthropic**
2. Model: `claude-sonnet-4-6` (recommended) or `claude-haiku-4-5-20251001` (faster, less accurate)
3. Max Tokens: `400`
4. Temperature: `0.3` (keeps responses consistent and on-topic)

#### 2e. Set the first message

This is what the assistant says the moment it picks up the call.
Paste this exactly into the **First Message** field:

```
Thanks for calling Cash Now Test Strips! If you have diabetic supplies to sell and would like to schedule a pickup, press 1 or just tell me. For help ordering on our website, press 2. To speak with a representative, press 3. Para español, oprima 9.
```

#### 2f. Set the system prompt

Paste the entire block below into the **System Prompt** field:

---

```
You are the phone assistant for Cash Now Test Strips, a business that buys diabetic supplies — test strips, CGM sensors and transmitters (Dexcom, FreeStyle Libre), insulin pumps and supplies (Omnipod, Tandem, Medtronic), pen needles, lancets, glucose meters, and select insulin and medications — for cash. A driver goes to the seller's location, picks up the items, inspects them, and pays cash on the spot.

SERVICE AREAS: Phoenix, Mesa, Chandler, Surprise, Buckeye, San Tan Valley, Maricopa, Casa Grande and surrounding areas; Tucson; Las Vegas and Henderson; Cincinnati and Dayton; Los Angeles, Long Beach, Anaheim, Redlands, Palm Springs and surrounding areas; Chicago; Detroit; Houston; Dallas; San Antonio; Tampa. If the caller is outside these areas, let them know a driver may not be available but still collect their info — the team follows up either way.

BUSINESS HOURS FOR LIVE REPRESENTATIVE: 10 AM to 9:30 PM, 7 days a week, Arizona time.

WHAT THIS CALL DOES AND DOES NOT DO:
- This call only creates a DRAFT pickup order. Nothing is confirmed on this call.
- No prices are discussed or quoted on this call. Pricing is confirmed by the live representative in person, based on item condition and expiration.
- No pickup date or time is confirmed on this call. A live rep will always call back to confirm the exact window before any driver is dispatched.
- This call simply collects the caller's information so the team can follow up.

---

MENU — when the call starts, route the caller based on their choice:
- 1 or "schedule" or "sell" or "pickup" → PICKUP FLOW
- 2 or "website" or "online" or "order" → WEBSITE HELP FLOW
- 3 or "representative" or "agent" or "human" → TRANSFER to live rep
- 9 or "español" or "Spanish" → switch to Spanish, call set_language with "es", repeat the menu in Spanish

---

PICKUP FLOW:
Collect the following. ALL FIELDS ARE OPTIONAL. If the caller cannot provide something, note it and move on immediately. A live representative fills in any gaps later.

1. full_name — seller's full name
2. phone — best callback number. Ask "Is the number you're calling from the best one to reach you?" rather than asking them to read digits. If they don't provide one, use the number they called from.
3. address — full pickup address (street, city, state). If they don't have it handy, skip it.
4. items — for each item: what it is, how many boxes or units, and the expiration date (approximate is fine). If they cannot give details, capture whatever they say.
5. pickup_date and pickup_window — their preferred date and rough time window. This is a preference only, not a confirmed time. If they do not know, skip it.

Save each piece immediately using the update_pickup_info tool as soon as you hear it. Do not wait until everything is collected.

Remind the caller once (naturally, not on every turn) to text photos of their items to +16029058480, the same number they called. Let them know photos help the live rep confirm and expedite the pickup. It is optional but strongly encouraged. If they agree, call update_pickup_info with photo_provided set to true.

Once you have collected what the caller can provide, read back a brief summary of everything and ask if it sounds correct. Once they confirm, call finalize_pickup and say: "You are all set! A live representative will call you back to confirm pricing and your exact pickup window. Thank you for calling Cash Now Test Strips."

---

WEBSITE HELP FLOW:
Walk the caller through placing their own pickup request on cashnowteststrips.com one step at a time. Check in after each step before moving to the next.

Step 1: Go to cashnowteststrips.com on any phone or computer browser.
Step 2: Tap Sell your products in the menu, or use the search box to find their specific item — test strips, CGM sensors, insulin pumps, meters, lancets, and so on — or browse by brand.
Step 3: Select the item and condition to see the payout amount, then add it to their quote. They can add multiple items like a shopping cart.
Step 4: Go to their cart and proceed to the Local Pickup Request Form at cashnowteststrips.com/pages/local-pickups-request-form, fill in their name, phone, address, and preferred pickup time, and submit.

After explaining step 1, offer to text them a direct link. If they say yes, call send_website_link.
If the caller seems confused, says it is too complicated, or asks you to just do it for them, warmly offer to collect their information right now over the phone. If they agree, call switch_to_pickup_flow and transition naturally.

---

GENERAL RULES:
- You are a phone voice assistant. Replies are converted to speech. Never use markdown, bullet points, asterisks, pound signs, or emojis.
- Keep replies short and natural — 1 to 3 sentences per turn, like a real phone agent. Ask one question at a time.
- Speak numbers, dates, and addresses naturally as they would sound out loud.
- Mirror the caller's language at all times. If they speak Spanish, respond entirely in Spanish and call set_language with "es". If they switch back to English, call set_language with "en".
- Never invent information the caller has not given you. If unsure, ask.
- If the caller goes off topic, gently steer back. Brief legitimate questions about the business — hours, what items are bought, service areas — are fine to answer.
- If the caller asks for a human, representative, agent, or person at any point, tell them you are connecting them now. Do not keep talking after that.
- If the conversation is complete and the caller says goodbye, say a brief friendly farewell.
```

---

#### 2g. Add tools

In the assistant editor, go to the **Tools** section → **+ Add Tool**.

Add the following tools one by one. For every custom tool, set the
**Server URL** to:
`https://YOUR-RENDER-URL.onrender.com/vapi/tools`

---

**Tool 1: update_pickup_info**

Type: `Function`

```json
{
  "name": "update_pickup_info",
  "description": "Save or update information collected for the pickup order. Call this as soon as you learn any new piece of information. Only include fields you actually learned this turn. For items, always pass the complete current list.",
  "parameters": {
    "type": "object",
    "properties": {
      "full_name": { "type": "string", "description": "Seller's full name" },
      "phone": { "type": "string", "description": "Best callback phone number" },
      "address": { "type": "string", "description": "Full pickup address" },
      "pickup_date": { "type": "string", "description": "Requested pickup date, e.g. 2026-06-25" },
      "pickup_window": { "type": "string", "description": "Requested time window, e.g. 2:00 PM - 4:00 PM" },
      "photo_provided": { "type": "boolean", "description": "True if caller agreed to text photos" },
      "extra_notes": { "type": "string", "description": "Any other notes from the caller" },
      "items": {
        "type": "array",
        "description": "Complete current list of items the caller wants to sell",
        "items": {
          "type": "object",
          "properties": {
            "description": { "type": "string" },
            "quantity": { "type": "integer" },
            "expiration": { "type": "string" }
          },
          "required": ["description"]
        }
      }
    }
  }
}
```

---

**Tool 2: finalize_pickup**

Type: `Function`

```json
{
  "name": "finalize_pickup",
  "description": "Call this only after you have read back a summary of everything collected and the caller has confirmed it is correct. This creates the draft order for the dispatch team.",
  "parameters": {
    "type": "object",
    "properties": {}
  }
}
```

---

**Tool 3: set_language**

Type: `Function`

```json
{
  "name": "set_language",
  "description": "Call this whenever you switch the language you are responding in so the system can track it correctly.",
  "parameters": {
    "type": "object",
    "properties": {
      "language": {
        "type": "string",
        "enum": ["en", "es"],
        "description": "Language you are now responding in."
      }
    },
    "required": ["language"]
  }
}
```

---

**Tool 4: send_website_link**

Type: `Function`

```json
{
  "name": "send_website_link",
  "description": "Send the caller a text message with a direct link to the website pickup request page.",
  "parameters": {
    "type": "object",
    "properties": {
      "phone": {
        "type": "string",
        "description": "Phone number to text. If not provided, the caller's number is used."
      }
    }
  }
}
```

---

**Tool 5: switch_to_pickup_flow**

Type: `Function`

```json
{
  "name": "switch_to_pickup_flow",
  "description": "Call this when the caller wants to stop using the website and have you collect their pickup information over the phone instead.",
  "parameters": {
    "type": "object",
    "properties": {}
  }
}
```

---

**Tool 6: check_business_hours**

Type: `Function`

```json
{
  "name": "check_business_hours",
  "description": "Check whether the business is currently open for live representative calls. Call this before telling a caller whether a live rep is available.",
  "parameters": {
    "type": "object",
    "properties": {}
  }
}
```

---

**Tool 7: Transfer Call (Vapi built-in)**

Type: `transferCall` (select from Vapi's built-in tool types — do NOT use Function type)

- Destination type: `number`
- Phone number: `+18886040655`
- Description: `Transfer the caller to a live representative when they request one or when the conversation cannot continue.`

---

**Tool 8: End Call (Vapi built-in)**

Type: `endCall` (select from Vapi's built-in tool types)

- Description: `End the call after the conversation is complete and the caller has said goodbye.`

---

#### 2h. Configure the voice

1. In the assistant editor, go to the **Voice** section
2. Provider: **ElevenLabs**
3. Voice: **Rachel** (natural, professional female voice — or browse and pick any you prefer)
4. For Spanish callers: Vapi can use a different voice per language. Under **Voice** settings, look for language-specific voice overrides and set Spanish to **Valentina** or another Spanish ElevenLabs voice.

If ElevenLabs requires an API key:
- Go to elevenlabs.io → sign up (free tier available)
- Copy your API key
- In Vapi → Settings → Provider Keys → ElevenLabs → paste key

---

#### 2i. Set the server URL for all custom tools

For each of the custom tools you added (update_pickup_info, finalize_pickup,
set_language, send_website_link, switch_to_pickup_flow, check_business_hours):

- Open the tool
- Set **Server URL** to: `https://YOUR-RENDER-URL.onrender.com/vapi/tools`
- Save

---

#### 2j. Save the assistant

Click **Save** or **Publish** in the top right of the assistant editor.

---

### Step 3: Connect Your Twilio Number to Vapi

Vapi can import your Twilio number directly and handles all the webhook
configuration automatically.

1. In Vapi, go to **Phone Numbers** (left sidebar) → **+ Add Phone Number**
2. Select **Import from Twilio**
3. Enter:
   - Twilio Account SID: `AC0fad0104bf8cc8d9e845c35bcb5a12b4`
   - Twilio Auth Token: your auth token
   - Phone Number: `+16029058480`
4. Click **Import**
5. Once imported, assign your assistant to this number:
   - Click on the number → **Inbound** → select `Cash Now IVR`
6. Save

Vapi automatically updates the Twilio webhook — you do not need to change
anything in the Twilio console for the webhook.

---

### Step 4: Verify Call Forwarding

Callers dial **(480) 690-3536**. That number must forward to **+16029058480**
(the Twilio/Vapi number). Confirm this forwarding is active in whatever
system hosts the 480 number (Zoom Phone, cell carrier, etc.).

---

### Step 5: Set Up UptimeRobot (keep Render awake)

Render's free tier sleeps after 15 minutes of no traffic. UptimeRobot pings
your server every 5 minutes to keep it awake 24/7.

1. Go to **uptimerobot.com** → create a free account
2. Add New Monitor:
   - Type: **HTTP(s)**
   - URL: `https://YOUR-RENDER-URL.onrender.com/health`
   - Interval: **5 minutes**
3. Save

---

### Step 6: Test the Full Flow

Call **(480) 690-3536** and test each scenario:

**Option 1 — Pickup scheduling:**
- Give your name, address, one item with a quantity and expiration
- Say you prefer a pickup window
- Confirm the summary when read back
- Check Render logs for `finalize_pickup` being called
- If `DETRACK_DRY_RUN=true`, check `orders_log.jsonl` on the Render server

**Option 2 — Website help:**
- Ask for help ordering online
- Follow the steps
- Ask the agent to send you a link — confirm you receive the SMS

**Option 3 — Transfer:**
- Ask for a representative
- Confirm the call transfers to +18886040655

**Option 9 / Spanish:**
- Say "español" at the menu
- Confirm the agent switches to Spanish and the voice changes

**Silence test:**
- Say nothing for a turn
- Agent should ask you to repeat

Monitor every test call in Vapi's **Calls** tab — you can see full transcripts,
tool calls made, and latency per turn.

---

### Step 7: Enable Real Detrack (after testing)

Once test calls look correct in the logs:

1. Render → **Environment** → change `DETRACK_DRY_RUN` from `true` → `false`
2. Make one real end-to-end test call
3. Confirm a Collection job appears in your Detrack dashboard with the right fields

Before setting `DETRACK_DRY_RUN=false`, review `orders_log.jsonl` on Render
to verify the payload format matches what your Detrack account expects.
See `detrack_client.py` for field mapping details.

---

## Rolling Back to the Old Twilio/Flask Setup

All previous code is preserved in git. To go back:

```powershell
git checkout main
git push origin main --force
```

Then in Render, redeploy from the `main` branch. In the Twilio console,
restore the webhook for +16029058480 to point to your Render URL + `/voice`.

---

## Updating the Product Catalog

`data/products.json` is a flat list of items with a `currently_buying` flag.
Edit it directly if your buying list changes, then push to GitHub:

```powershell
git add data/products.json
git commit -m "Update product catalog"
git push
```

---

## Scaling Notes

- Default Procfile runs 1 gunicorn worker — fine for this workload since
  the server only handles brief tool-call webhooks, not full conversations.
- If you run multiple workers, set `REDIS_URL` in Render so sessions are
  shared. `session_store.py` supports this — no code changes needed.
- Vapi handles call scaling on their end automatically.

---

## Environment Variables Quick Reference (Render)

| Variable | Purpose |
|---|---|
| `TWILIO_ACCOUNT_SID` | Sending SMS |
| `TWILIO_AUTH_TOKEN` | Sending SMS |
| `TWILIO_MAIN_NUMBER` | SMS "From" number |
| `DETRACK_API_KEY` | Submitting jobs to Detrack |
| `DETRACK_DRY_RUN` | `true` = log only, `false` = live API |
| `DETRACK_BASE_URL` | Detrack API endpoint |
| `DISPATCH_ALERT_PHONE` | Gets SMS if Detrack fails |
| `COMPANY_NAME` | Used in SMS messages |
| `WEBSITE_PICKUP_FORM_URL` | Link sent via SMS in Option 2 |
| `BUSINESS_TZ` | Timezone for hours check |
| `BUSINESS_OPEN_TIME` | Hours open (HH:MM) |
| `BUSINESS_CLOSE_TIME` | Hours close (HH:MM) |
| `BUSINESS_DAYS` | Days staffed (0=Mon, 6=Sun) |
| `SESSION_TTL_SECONDS` | How long to keep call sessions |
| `PORT` | Port for gunicorn (default 5000) |
| `FLASK_DEBUG` | `false` in production |
