---
description: Run the full OROVA Lead Generation Cycle (Scrape -> Enrich -> Prepare for Calls)
---

This workflow automates the daily lead generation process for OROVA.

1. **Scrape New Leads**
   Run the scraper to find new potential business in targeted niches.
   ```bash
   python scraper.py
   ```

2. **Run The Hunter (Enrichment)**
   Run the batch processor to:
   - Filter out duplicates.
   - Use "The Hunter" agent to find Owner names for leads with missing info.
   - Score leads 0-10 using Gemini.
   ```bash
   python batch_processor.py
   ```

3. **Verify Output**
   Check the `qualified_leads.csv` file to see the new "HOT" leads ready for calling.
   ```bash
   type qualified_leads.csv
   ```

4. **Ready for Calling**
   The leads are now ready. You can manually start the caller or ask me to do it.
   ```bash
   python retell_caller.py list
   ```
