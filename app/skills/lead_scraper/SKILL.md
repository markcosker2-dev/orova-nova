# LeadScraper Skill

**Description**: Systematically searches for, extracts, and qualifies potential sales leads based on an Ideal Customer Profile (ICP).

## Procedure

1. **Parameter Initialization**:
   - Define the target industry, geography, and company size.
   - Specify the "Qualification Criteria" (e.g., recent funding, specific tech stack, or job openings).

2. **Search and Discovery**:
   - Use `mcp_exa_search` or `web_search` (Firecrawl) to identify target company domains or LinkedIn profiles.
   - If using the **Nous Portal**, leverage the cloud browser (`browser_use`) to navigate to directory listings or "Team" pages.

3. **Data Extraction**:
   - Extract key data points: Name, Title, Verified Email, LinkedIn URL, and Company Description.
   - Use the **Scrapling MCP server** for structured extraction from complex web surfaces.

4. **Qualification (Cognitive Layer)**:
   - Match extracted data against the ICP defined in `USER.md`.
   - Score the lead (0.0 to 1.0) based on relevance.
   - Filter out any leads that trigger the `rule_data_leakage` or `rule_injection_detection` in the **Semantic Firewall**.

5. **Reporting & Approval**:
   - Format the qualified leads into a summary.
   - Use the **OpenClaw Gateway** to send the report to the user via Telegram or WhatsApp.
   - **Guardrail**: Require explicit user approval before moving to an automated outreach stage.

6. **Feedback Loop**:
   - Record the outcome in `app/core/self_learning.py` to refine future search patterns and improve lead scoring accuracy.
