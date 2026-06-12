Make.com Scenario Blueprint for OROVA → Notion

IMPORTANT: This is a manual blueprint, not a Make-exported scenario file. Make does not accept arbitrary JSON as a scenario import.

Overview
- Purpose: receive OROVA lead webhooks and create Notion database items.
- Two options: (A) Use Make's Notion module (preferred). (B) Use Make HTTP module to call Notion API (fallback).

Prerequisites
- Notion: create an integration and copy the Internal Integration Token (NOTION_TOKEN).
- Share your Notion database with the integration (the DB ID is the string you already have).
- Make: an account and ability to create a Scenario.
- From the repo: set `OROVA_SECRET` and `MAKE_NOTION_WEBHOOK_URL` in `.env` or Render context.

Step-by-step (Preferred — Notion module)
1. In Make, create a new Scenario.
2. Add module: Webhooks → Custom Webhook. Name it `orova_leads_webhook` and Save. Copy the generated webhook URL.
3. Add a filter immediately after the webhook to validate the secret:
   - Condition: `secret` (from webhook) equals your `OROVA_SECRET` value.
   - This prevents unauthenticated submissions.
4. Add module: Notion → Create a Database Item.
   - Authenticate using your `NOTION_TOKEN` (Internal Integration Token).
   - For Database, select your database (or paste the Database ID if asked).
   - Map fields from the webhook to Notion properties:
     - Title/Name (title) ← `business`
     - Owner (rich_text or text) ← `owner`
     - Email (email or rich_text) ← `email`
     - Phone (phone number or rich_text) ← `phone`
     - Website (url) ← `website` or `url`
     - Status (select) ← `status` (ensure your DB has appropriate Select options)
     - Score (number) ← `score`
     - Notes (rich_text) ← `notes`
     - Source (text) ← `source`
5. Save Scenario. Turn on Scenario or use `Run once` to test.

Fallback (HTTP → Notion API)
If the Notion module isn't available, use HTTP module with these settings:
- Module: HTTP → Make a request
- Method: POST
- URL: https://api.notion.com/v1/pages
- Headers:
  - Authorization: Bearer {NOTION_TOKEN}
  - Notion-Version: 2022-06-28
  - Content-Type: application/json
- Body type: Raw
- Request content: Paste the JSON from `notion_http_body.json` and map webhook fields into the values.

Example Notion HTTP body (template file included): replace `DATABASE_ID` and mapped values.

Sample webhook payload (for "Run once" capture or manual tests): see `sample_webhook_payload.json`.

Testing locally (curl)
- Once you copy the Make webhook URL (CALLER_WEBHOOK_URL), run this from your machine to simulate OROVA:

```bash
curl -X POST CALLER_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d @make_blueprint/sample_webhook_payload.json
```

Repo integration
- After you confirm Make webhook URL, add it to `.env` as `MAKE_NOTION_WEBHOOK_URL` and set `OROVA_SECRET`.
- Optionally add `NOTION_TOKEN` and `NOTION_DATABASE_ID` to Render context.

Notes and troubleshooting
- Ensure Notion DB has properties matching types used above; adjust mappings in Make accordingly.
- If using the HTTP module, check response codes 200/201/202; log errors in Make to inspect payload.
- If your DB uses Select/Status options, create those choices in Notion before sending.

Files included:
- notion_http_body.json — HTTP body template for Notion API.
- sample_webhook_payload.json — sample payload for testing.

If you want, paste your Make webhook URL and I'll patch `.env` and run a test POST from the repo.