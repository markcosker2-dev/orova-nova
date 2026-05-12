---
description: Run the daily batch of 10 automated cold emails using The Scribe agent.
---

This workflow runs the `email_agent.py` script to send out a batch of cold emails.

**Safety Rules:**
- Sends Maximum 10 emails per run (to protect Gmail account).
- Only emails leads with AIScore >= 7.
- Checks `qualified_leads.csv` to ensure it never double-emails the same person.

1. **Run The Scribe**
   ```bash
   python email_agent.py
   ```
   *Watch the terminal output to see the AI generating and sending emails in real-time.*
