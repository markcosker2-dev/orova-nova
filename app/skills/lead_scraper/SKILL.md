# LeadScraper Skill

**Description**: Systematically searches for, extracts, and qualifies potential sales leads using a free, Render-safe pipeline (no browser/Playwright dependency).

## Pipeline (Free — $0/month)

```
Search Query → Tavily/Firecrawl/DDG/SerpAPI Maps → Find Business URLs
        │
        ▼
  lead_enrichment.enrich_leads_batch (regex + UnifiedAIClient extraction)
        │  Owner name, email, phone
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
   - Use `find_leads` (`app/skills/lead_finder.py`) — multi-source: Tavily, Firecrawl, DDG, BBB.org, SerpAPI Google Maps
   - Find business URLs with owner names, phones, websites

2. **Enrichment**:
   - `find_leads` auto-enriches results via `app.skills.lead_enrichment.enrich_leads_batch`
   - For existing lead rows, use `app.skills.light_enrich.enrich_lead_lite(lead)`
   - Extracts: owner name, email, phone, business name

3. **Qualification**:
   - Score lead against ICP in `USER.md` (see `app/skills/lead_validator.py`)
   - Filter through Semantic Firewall (no data leakage or injection)

4. **Reporting & Approval**:
   - Format qualified leads → send to user via Telegram/WhatsApp
   - **Guardrail**: Required explicit approval before outreach

5. **Feedback Loop**:
   - Record outcome in `app/core/self_learning.py`
   - Learn which search patterns and niches work best