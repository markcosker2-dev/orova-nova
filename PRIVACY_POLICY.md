# OROVA Privacy Policy

**Last Updated:** May 16, 2026

## 1. Data We Collect

OROVA (Outreach & Revenue Operations via AI) collects and processes the following data to provide its AI-powered sales automation services:

### 1.1 User Data
- **Business Information:** Company name, industry, location, revenue range
- **Contact Information:** Email addresses, phone numbers, business websites
- **Lead Information:** Names, job titles, social profiles, employment history
- **Interaction Data:** Messages, call logs, email records, engagement metrics

### 1.2 Technical Data
- **Usage Logs:** API requests, timestamps, response times, error logs
- **Device Information:** IP address, browser type, operating system
- **Cookies & Tracking:** Session management via secure HTTP-only cookies

### 1.3 Billing Data
- **Payment Information:** Credit card (processed via Stripe, not stored locally), billing address
- **Usage Metrics:** API calls, model selections, storage usage

## 2. How We Use Your Data

We use collected data for:
- Providing and improving AI-powered lead generation and outreach services
- Analytics and performance monitoring
- Fraud prevention and security
- Billing and account management
- Compliance with legal obligations
- Troubleshooting and customer support

**We do NOT:**
- Sell or share personal data with third parties for marketing purposes
- Use data to train generalized AI models without explicit opt-in
- Share data with government entities without proper legal process
- Use data for discriminatory purposes

## 3. Data Storage & Retention

- **Active Data:** Stored in SQLite cache + Google Sheets (persistent, encrypted in transit)
- **Backups:** 6-hour automated snapshots stored in Google Drive (encrypted)
- **Deletion Policy:** Upon account deletion, all user data is purged within 30 days
- **Retention:** Leads/metrics retained for 2 years unless deleted by user

## 4. Third-Party Services

We use the following third-party services:

| Service | Purpose | Data Shared |
|---------|---------|-------------|
| **Google Sheets/Drive** | Data persistence & backup | Leads, metrics, call logs |
| **Telegram** | Message routing | Chat ID, message content |
| **OpenRouter/Groq** | AI processing | Anonymized lead data, queries |
| **Stripe** | Payment processing | Name, email, amount (encrypted) |
| **Cal.com** | Meeting scheduling | Email, availability windows |
| **Apollo.io** | B2B email enrichment | Domain, company name |

**All third-party integrations use encrypted HTTPS, and we enforce data minimization.**

## 5. User Rights

### 5.1 Access & Portability
- Users can request a complete export of their data (CSV/JSON) via `/api/export` endpoint
- Export available within 30 days of request

### 5.2 Deletion (Right to Be Forgotten)
- Users can delete their account and all associated data via dashboard
- Deletion is irreversible and processed within 30 days
- API: `DELETE /api/user/{user_id}` (requires authentication)

### 5.3 Opt-Out
- Users can opt-out of email outreach by replying "STOP" to any email
- Users can disable Telegram notifications in settings

## 6. GDPR & CCPA Compliance

**GDPR (European users):**
- Legal basis: Legitimate interest (business operations) + consent (marketing)
- Data Protection Impact Assessment available upon request
- Data Processing Agreement available for enterprise customers
- EU users have rights to access, rectification, erasure, and portability

**CCPA (California residents):**
- Right to know what personal data is collected
- Right to delete personal data (with exceptions)
- Right to opt-out of data sales (we don't sell data)
- Shines Families Act: OROVA does not knowingly serve users under 13

## 7. Data Security

**Encryption & Protection:**
- HTTPS/TLS for all data in transit
- Google Sheets encryption at rest
- API keys stored as environment variables (not in code)
- Sensitive data (payment info) never cached locally
- Rate limiting: 100 requests/minute per client

**Incident Response:**
- Critical security issues reported to affected users within 72 hours
- Security audits conducted quarterly
- Bug bounty program available at `security@orova.ai`

## 8. Changes to This Policy

We reserve the right to modify this policy. Users will be notified of material changes via email at least 30 days in advance.

## 9. Contact

For privacy-related inquiries:
- **Email:** privacy@orova.ai
- **Response Time:** 14 business days

---
**OROVA Privacy Policy v1.0 | Free Tier Release**
