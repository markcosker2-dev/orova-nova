# -*- coding: utf-8 -*-
"""
OROVA Core Engine — Universal Email Outreach
Refactored from email_agent.py. Templates loaded from vertical config.
"""

import os
import re
import time
import json
import datetime
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UniversalEmailAgent:
    """Industry-agnostic cold email agent driven by vertical config."""

    def __init__(self, vertical_name: str, email_user: str = None, email_pass: str = None):
        from Core_Engine.config import load_vertical
        self.vertical = load_vertical(vertical_name)
        self.vertical_name = vertical_name
        self.templates = self.vertical.get("email_templates", {})

        self.email_user = email_user or os.environ.get("EMAIL_USER", "markcosker2@gmail.com")
        self.email_pass = email_pass or os.environ.get("EMAIL_PASS")
        self.daily_limit = int(os.environ.get("DAILY_EMAIL_LIMIT", "10"))

        # AI Setup
        self.client = None
        self.model_id = 'gemini-2.5-flash'
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}")

    def generate_email(self, lead: dict) -> dict:
        """Generate personalized cold email using AI + vertical template."""
        if not self.client:
            return None

        business = lead.get("Business Name", "your company")
        owner = lead.get("Decision Maker", "there")
        icebreaker = lead.get("Icebreaker", "")
        service = lead.get("Primary_Service", "services")

        if "N/A" in str(owner) or len(str(owner)) < 3:
            owner = "there"
        else:
            owner = str(owner).split()[0]

        # Load template rules from config
        sender_name = self.templates.get("sender_name", "Mark")
        agency_name = self.templates.get("agency_name", "OROVA")
        value_prop = self.templates.get("value_proposition",
            "filling your calendar with high-ticket clients automatically")
        tone = self.templates.get("tone", "conversational, 5th-grade reading level")

        prompt = f"""
You are a "Cold Email Sniper" for {agency_name}.

Recipient: {owner} (Owner of {business}, a {service} business)
Sender: {sender_name} from {agency_name}
Observation: "{icebreaker}"

GUIDELINES:
1. **Brevity:** 50-125 words. Short & scannable.
2. **Tone:** {tone}. No marketing fluff.
3. **Subject Line:** Lowercase, 2-5 words, looks like internal email.
4. **Hook:** Start with the specific observation to prove you're not a bot.
5. **Value:** Talk about "{value_prop}" — not AI features.
6. **Soft Ask:** Don't ask for meeting time. Ask for interest.
7. **Formatting:** NO em-dashes. Simple commas or periods. Like a phone text.

Return JSON:
{{
    "subject": "lowercase subject line",
    "body": "The email body..."
}}
"""
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model_id, contents=prompt
                )
                text = response.text.replace('```json', '').replace('```', '').strip()
                return json.loads(text)
            except Exception as e:
                if "429" in str(e):
                    wait = 30
                    match = re.search(r'retry in (\d+\.?\d*)s', str(e))
                    if match:
                        wait = float(match.group(1)) + 1
                    time.sleep(wait)
                else:
                    logger.error(f"AI Error: {e}")
                    return None
        return None

    def send_batch(self, csv_file: str = None, min_score: int = 7):
        """Send daily batch of cold emails."""
        if csv_file is None:
            csv_file = f"qualified_{self.vertical_name.lower()}.csv"

        logger.info(f"--- OROVA Email Agent — {self.vertical_name} ---")

        if not os.path.exists(csv_file):
            logger.error(f"{csv_file} not found. Run scraper + scorer first.")
            return

        df = pd.read_csv(csv_file)

        if "Emailed" not in df.columns:
            df["Emailed"] = False

        targets = df[
            (df["AI_Score"] >= min_score) &
            (df["Emailed"] == False) &
            (df["Contact Email"].notna()) &
            (df["Contact Email"] != "N/A")
        ].head(self.daily_limit)

        if targets.empty:
            logger.info("No new targets found.")
            return

        logger.info(f"Found {len(targets)} targets")

        # Connect to Gmail
        try:
            import yagmail
            yag = yagmail.SMTP(self.email_user, self.email_pass)
            logger.info("Connected to Gmail")
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return

        sent = 0
        for idx, row in targets.iterrows():
            to_email = row["Contact Email"]
            logger.info(f"Generating for {row['Business Name']} ({to_email})...")

            content = self.generate_email(row.to_dict())
            if not content:
                continue

            print(f"\n{'='*50}")
            print(f"TO: {to_email}")
            print(f"SUBJECT: {content['subject']}")
            print(f"BODY:\n{content['body']}")
            print(f"{'='*50}")

            confirm = input(">>> Send? (y/n): ").strip().lower()
            if confirm != "y":
                print("  [SKIPPED]")
                continue

            try:
                yag.send(to=to_email, subject=content["subject"], contents=content["body"])
                print("  [SENT] ✅")
                df.at[idx, "Emailed"] = True
                df.at[idx, "Emailed_Date"] = datetime.date.today()
                sent += 1
                df.to_csv(csv_file, index=False)
                time.sleep(10)
            except Exception as e:
                print(f"  [FAILED] ❌ {e}")

        logger.info(f"Batch complete. Sent {sent} emails.")


if __name__ == "__main__":
    import sys
    vertical = sys.argv[1] if len(sys.argv) > 1 else "Automotive"
    print(f"\n📧 OROVA Email Agent — Vertical: {vertical}\n")
    agent = UniversalEmailAgent(vertical)
    agent.send_batch()
