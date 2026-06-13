# LeadScraper Skill

**Description**: Systematically searches for, extracts, and qualifies potential sales leads using a free, AI-powered pipeline.

## Pipeline (Free — $0/month)

```
Search Query → DDG/Google Maps → Find Business URLs
        │
        ▼
  ScrapeGraphAI + Groq (AI extraction)
        │  Owner name, email, phone
        ▼
  HTML fallback scrape (regex extraction)
        │
        ▼
  Semantic Firewall (filter data leakage)
        │
        ▼
  Lead Wiki saved → Report to user → Approval required
        │
        ▼
  Self-learning loop (learn from outcomes)
```

## Procedure

1. **Search & Discovery**:
   - Use `find_leads` / `find_leads_v2` for DDG + Google Maps search
   - Find business URLs with owner names, phones, websites

2. **AI-Powered Extraction (ScrapeGraphAI + Groq)**:
   - `sgai_deep_extract(url)` — Deep scrape a single URL with AI
   - Uses Groq's free tier (30K requests/day)
   - Extracts: owner name, email, phone, business name
   - Three-tier fallback: AI extract → AI search → HTML regex scrape

3. **Unified Enrichment**:
   - `enrich_lead_ai(business_name, url)` — Single call, tries all methods
   - Returns: `{business_name, owner_name, email, phone, source}`

4. **Qualification**:
   - Score lead 0.0–1.0 against ICP in `USER.md`
   - Filter through Semantic Firewall (no data leakage or injection)

5. **Reporting & Approval**:
   - Format qualified leads → send to user via Telegram/WhatsApp
   - **Guardrail**: Required explicit approval before outreach

6. **Feedback Loop**:
   - Record outcome in `app/core/self_learning.py`
   - Learn which search patterns and niches work best