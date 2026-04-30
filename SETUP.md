# Nova Mission Control — Setup Guide

Complete step-by-step to get your system live on HuggingFace.

---

## Files to replace in your project

Drop each file into the matching path in your project:

| This file | Replaces / goes to |
|---|---|
| `main.py` | `main.py` (root — **new file**) |
| `Core_Engine/db_manager.py` | `Core_Engine/db_manager.py` |
| `Core_Engine/lead_scraper.py` | `Core_Engine/lead_scraper.py` |
| `Core_Engine/lead_scorer.py` | `Core_Engine/lead_scorer.py` |
| `Core_Engine/email_outreach.py` | `Core_Engine/email_outreach.py` |
| `Core_Engine/ai_caller.py` | `Core_Engine/ai_caller.py` |
| `Core_Engine/instagram_agent.py` | `Core_Engine/instagram_agent.py` |
| `Core_Engine/crm_sync.py` | `Core_Engine/crm_sync.py` |
| `requirements.txt` | `requirements.txt` |
| `nova.env.example` | Copy to `.env` and fill in values |

---

## Step 1 — Set up your .env

```bash
cp nova.env.example .env
```

Edit `.env` and fill in:
1. `NOVA_API_KEY` — make up any secret string (e.g. `nova-my-secret-2024`)
2. `GOOGLE_API_KEY` — from https://aistudio.google.com/app/apikey (free)
3. `EMAIL_USER` + `EMAIL_PASS` — Gmail + App Password (see below)
4. `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — from @BotFather
5. Everything else can wait until you're ready to use that feature

### Gmail App Password (takes 2 minutes)
1. Go to myaccount.google.com → Security → 2-Step Verification (turn ON)
2. Go to myaccount.google.com → Security → App Passwords
3. Select "Mail" + "Windows Computer" → Generate
4. Paste the 16-character password into EMAIL_PASS (no spaces)

---

## Step 2 — Set up your HuggingFace Space Secrets

In your HuggingFace Space → Settings → Repository Secrets, add each `.env` variable as a secret. HuggingFace injects them as environment variables at runtime.

You do NOT upload your `.env` file — use Secrets instead.

---

## Step 3 — Add the NOVA_API_KEY to your dashboard JS

Open `js/app.js` and find the `apiFetch` function. Update it to send your API key:

```javascript
async function apiFetch(path, opts = {}) {
    opts.headers = opts.headers || {};
    opts.headers['X-API-Key'] = 'YOUR_NOVA_API_KEY_HERE'; // same as in .env
    let fetchPath = path + (path.includes('?') ? '&' : '?') + `client_id=${currentClientId}`;
    const res = await fetch(API + fetchPath, opts);
    return await res.json();
}
```

---

## Step 4 — Set up Retell AI (for calling)

1. Sign up at https://app.retellai.com
2. Create an Agent — set the voice, personality, and set the webhook URL to:
   `https://YOUR-SPACE.hf.space/webhook/retell`
3. Get a phone number from Retell (or bring your own via Twilio)
4. Copy your Agent ID and phone number into `.env`

---

## Step 5 — Set up Google Sheets CRM (optional but recommended)

1. Create a blank Google Sheet
2. Copy the Sheet ID from the URL
3. Create a Service Account: console.cloud.google.com → IAM → Service Accounts
4. Download the JSON key as `service_account.json` and put it in your project root
5. Share your Google Sheet with the service account email address
6. Add the Sheet ID to `.env` as `CRM_SHEET_ID`

---

## Step 6 — Test locally before deploying

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```

Visit http://localhost:7860 — you should see Mission Control.

Test the API: `curl -H "X-API-Key: your-key" http://localhost:7860/health`

---

## Step 7 — Set up Telegram Bot

1. Message @BotFather on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the token into `TELEGRAM_BOT_TOKEN`
4. Start your bot (send it `/start`)
5. Message @userinfobot to get your chat ID
6. Put your chat ID into `TELEGRAM_CHAT_ID`

Once running, you can control everything from your phone:
- `/scrape Automotive "ceramic coating LA" 15`
- `/leads 10`
- `/emailall 70`
- `/report`

---

## How the business loop works

```
/scrape → finds businesses via DuckDuckGo
        → scrapes email + phone from each website
        → scores them 0-100 with Gemini
        → saves to your SQLite database

/emailall 70 → emails every lead with score 70+
             → Gemini writes personalised subject + body
             → marks them "Emailed" in the database

/call [id] → Retell calls the lead
           → Gemini writes the opening script
           → call outcome updates the lead status via webhook

Mission Control dashboard → shows everything in real time
Google Sheets → synced copy you can share with clients
```

---

## Troubleshooting

**Dashboard shows blank / 404 on API calls**
→ Make sure `NOVA_API_KEY` in your JS matches the one in `.env`

**Emails not sending**
→ Check EMAIL_USER and EMAIL_PASS are set correctly
→ Gmail App Password must be 16 chars with no spaces
→ Check `nova.log` for the exact error

**Retell calls failing**
→ Confirm RETELL_FROM_NUMBER includes country code: `+1XXXXXXXXXX`
→ Make sure your Retell Agent webhook is set to your HuggingFace URL

**Telegram bot not responding**
→ Check TELEGRAM_BOT_TOKEN is correct
→ Check `nova.log` for `[TELEGRAM] Bot polling started`

**Google Sheets sync failing**
→ Confirm `service_account.json` is in the project root
→ Confirm the sheet is shared with the service account email
