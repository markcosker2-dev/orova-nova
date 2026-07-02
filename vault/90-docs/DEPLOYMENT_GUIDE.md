# OROVA PRODUCTION DEPLOYMENT GUIDE
**Complete End-to-End Setup Instructions**  
**Version:** 1.0  
**Status:** PRODUCTION READY  
**Date:** May 22, 2026

---

## 📋 TABLE OF CONTENTS

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [System Architecture Overview](#system-architecture-overview)
3. [Step-by-Step Deployment](#step-by-step-deployment)
4. [Configuration Guide](#configuration-guide)
5. [Verification & Testing](#verification--testing)
6. [Troubleshooting](#troubleshooting)
7. [Operations Guide](#operations-guide)

---

## ✅ PRE-DEPLOYMENT CHECKLIST

Before you deploy, ensure you have:

### Required Accounts & Access
- [ ] Telegram account with bot created via @BotFather
- [ ] Hosting platform account (Render, Google Cloud, AWS, etc.)
- [ ] Google Cloud project (if using Google Sheets)
- [ ] Text editor or IDE (VS Code recommended)

### Code & Files
- [ ] OROVA codebase cloned/downloaded
- [ ] All dependencies in `requirements.txt`
- [ ] No uncommitted changes
- [ ] No sensitive data in code

### Documentation
- [ ] Read SYSTEM_AUDIT.md
- [ ] Read PRODUCTION_READY.md  
- [ ] This deployment guide understood

---

## 🏗️ SYSTEM ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────┐
│                   OROVA ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────┐
│  Telegram   │ ← User sends message to Telegram bot
│    Bot      │
└──────┬──────┘
       │ POST /telegram
       ↓
┌─────────────────────────────────────────────────────────────┐
│                 FastAPI Web Server                           │
│  (Runs on http://0.0.0.0:7860)                              │
│                                                              │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Mission       │  │ API          │  │ Telegram     │    │
│  │ Control       │  │ Endpoints    │  │ Webhook      │    │
│  │ Dashboard     │  │ (45+)        │  │ Handler      │    │
│  └───────────────┘  └──────────────┘  └──────────────┘    │
│                                              ↓              │
│  ┌────────────────────────────────────────────────────┐   │
│  │         Telegram Queue (50 item bound)             │   │
│  │  - Backpressure handling                          │   │
│  │  - Single worker (serialized processing)          │   │
│  └────────────────────────────────────────────────────┘   │
│                           ↓                                 │
│  ┌────────────────────────────────────────────────────┐   │
│  │         Router & Message Handler                   │   │
│  │  - Input sanitization                             │   │
│  │  - Rate limiting per chat_id                      │   │
│  │  - Routes to appropriate agent (Nova/Hawk/etc)    │   │
│  └────────────────────────────────────────────────────┘   │
│                           ↓                                 │
│  ┌────────────────────────────────────────────────────┐   │
│  │         AI Client & Planner                        │   │
│  │  - Unified AI (OpenAI, Google, Claude failover)   │   │
│  │  - Circuit breakers per provider                  │   │
│  │  - Tool selection & execution                     │   │
│  └────────────────────────────────────────────────────┘   │
│                           ↓                                 │
│  ┌────────────────────────────────────────────────────┐   │
│  │         Skill Execution Layer (30+ Skills)        │   │
│  │  - Lead finding (multi-source)                    │   │
│  │  - Research & enrichment                          │   │
│  │  - Email & content generation                     │   │
│  │  - Analytics & reporting                          │   │
│  └────────────────────────────────────────────────────┘   │
│                           ↓                                 │
└──────────┬──────────────┬────────────────┬─────────────────┘
           ↓              ↓                 ↓
    ┌─────────────┐ ┌──────────────┐ ┌──────────────┐
    │   SQLite    │ │Google Sheets │ │External APIs │
    │  Database   │ │  Sync        │ │(Tavily, etc) │
    └─────────────┘ └──────────────┘ └──────────────┘
           ↑              ↑                 ↑
           └──────────────┴─────────────────┘
                    Response Flow
```

### Key Components

| Component | Purpose | Status |
|-----------|---------|--------|
| **API Server** | Handles HTTP requests | ✅ Ready |
| **Mission Control** | Web dashboard | ✅ Ready |
| **Telegram Queue** | Bounded message buffer | ✅ Ready |
| **Router** | Message routing + security | ✅ Ready |
| **AI Client** | Multi-provider LLM | ✅ Ready |
| **Skills** | 30+ AI tools | ✅ Ready |
| **Database** | SQLite + Sheets sync | ✅ Ready |
| **Worker** | Background jobs | ✅ Ready |

---

## 🚀 STEP-BY-STEP DEPLOYMENT

### Step 1: Create Telegram Bot (5 minutes)

**On Telegram Desktop/Mobile:**

1. Open Telegram
2. Search for `@BotFather`
3. Send `/newbot`
4. Follow prompts:
   - Name: `OROVA Nova` (or your choice)
   - Username: `orova_nova_bot` (must be unique)
5. BotFather will return your **BOT TOKEN** - save it!

Example response:
```
Done! Congratulations on your new bot. 
You will find it at t.me/orova_nova_bot
Use this token to access the HTTP API:
1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
```

**Get Your Chat ID:**

1. Send `/start` to your new bot
2. Search for `@userinfobot`  
3. Send it any message
4. It will return your **USER ID** (Chat ID) - save it!

### Step 2: Deploy to Render (10 minutes)

**If starting fresh:**

1. Go to https://render.com
2. Sign in / create account
3. Click "New +" → "Web Service"
4. Connect GitHub (or paste code)
5. Fill in:
   - **Name:** `orova-nova`
   - **Environment:** `Python 3.11`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Click "Create Web Service"
7. Wait for build (~3-5 minutes)

**If updating existing:**

1. Go to Render dashboard
2. Select your OROVA service
3. Go to Settings → Environment
4. Update any secrets
5. Manually trigger redeploy or push to GitHub

### Step 3: Configure Environment Variables (5 minutes)

**In Render Dashboard:**

Go to Services → Your Service → Environment

Add these secrets:

```
TELEGRAM_BOT_TOKEN = 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
TELEGRAM_CHAT_ID = 123456789

DASHBOARD_API_KEY = nova_admin_2026

RENDER_EXTERNAL_URL = https://orova-nova.onrender.com
```

**Optional (for enhanced features):**

```
APOLLO_API_KEY = <from apollo.io>
TAVILY_API_KEY = <from tavily.com>
FIRECRAWL_API_KEY = <from firecrawl.dev>
```

**If using Google Sheets (Recommended):**

1. Go to Google Cloud Console (console.cloud.google.com)
2. Create new project: "OROVA"
3. Enable APIs:
   - Google Sheets API
   - Google Drive API
4. Create Service Account:
   - IAM & Admin → Service Accounts
   - Create Service Account
   - Add roles: "Editor"
   - Create JSON key
5. Download JSON file
6. Base64 encode it:
   ```bash
   cat service_account.json | base64 -w 0
   ```
7. In Render, add:
   ```
   GOOGLE_CREDENTIALS_JSON = <paste base64 output>
   GOOGLE_SHEETS_WORKBOOK = OROVA CRM
   ```
8. Create Google Sheet:
   - Name: "OROVA CRM"
   - Tabs: Leads, Metrics, CallLog, Meetings
   - Share with service account email

### Step 4: Test Deployment (10 minutes)

**Check Server Health:**

```bash
curl https://orova-nova.onrender.com/health | jq
```

Expected response:
```json
{
  "status": "Operational",
  "uptime": "Running",
  "circuit_breakers": {...},
  "queue_depth": 0,
  "agents_online": 6
}
```

**Check Dashboard:**

Open browser: `https://orova-nova.onrender.com`

You should see Mission Control dashboard

**Test Telegram Bot:**

1. Open your bot on Telegram
2. Send: `/start`
3. Nova should respond: "Hi! I'm Nova..."

**Test Lead Hunting:**

Send to Telegram bot:
```
Find 5 luxury car dealers in California
```

Bot should respond within 2-5 seconds with leads.

### Step 5: Initialize Data (5 minutes)

**Google Sheets Setup (if configured):**

- System auto-syncs on first boot
- Leads automatically save to sheet
- Data persists across restarts

**SQLite Setup (default):**

- Database `orova.db` auto-created
- Data persists locally
- No additional setup needed

---

## ⚙️ CONFIGURATION GUIDE

### Environment Variables Reference

**Required:**
```
TELEGRAM_BOT_TOKEN
  - From @BotFather on Telegram
  - Format: numbers:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
  - Required for: Telegram bot operation

RENDER_EXTERNAL_URL
  - Your deployment URL
  - Format: https://yourdomain.onrender.com
  - Required for: Telegram webhook registration
```

**Recommended:**
```
DASHBOARD_API_KEY
  - Secret for Mission Control API
  - Default: nova_admin_2026
  - Custom value: Any string 16+ chars
  - Used for: /api/* authentication

GOOGLE_CREDENTIALS_JSON
  - Base64-encoded service account JSON
  - From: Google Cloud Console
  - Required for: Google Sheets persistence
  - If not set: Uses SQLite only

GOOGLE_SHEETS_WORKBOOK
  - Name of your Google Sheet
  - Default: OROVA CRM
  - Required: If using Google Sheets
```

**Optional (Enhanced Features):**
```
APOLLO_API_KEY
  - From: apollo.io
  - Enables: Contact enrichment
  - Benefit: Gets owner emails + LinkedIn

TAVILY_API_KEY
  - From: tavily.com
  - Enables: Clean lead search (1,000 free/month)
  - Benefit: Better quality leads

FIRECRAWL_API_KEY
  - From: firecrawl.dev  
  - Enables: Website scraping
  - Benefit: Reliable lead extraction

RETELL_API_KEY
  - From: retellai.com
  - Enables: AI phone calling
  - Benefit: Automated outbound calling

RETELL_FROM_NUMBER
  - Your Retell phone number
  - Format: +1XXXXXXXXXX (with country code)
  - Required for: Phone calling feature

RETELL_AGENT_ID
  - Your Retell agent ID
  - From: Retell dashboard
  - Required for: Phone calling feature
```

### Database Configuration

**SQLite (Default - No Setup)**
```
# Automatic
- Database: orova.db (1-50MB)
- Location: Project root
- Persistence: Until deleted
```

**Google Sheets (Recommended for Production)**
```
# Required steps:
1. Create Google Sheet: "OROVA CRM"
2. Create tabs: Leads, Metrics, CallLog, Meetings
3. Get service account JSON from Google Cloud
4. Set GOOGLE_CREDENTIALS_JSON environment variable
5. Set GOOGLE_SHEETS_WORKBOOK = "OROVA CRM"
6. Share sheet with service account email
7. System syncs automatically
```

---

## ✅ VERIFICATION & TESTING

### Pre-Launch Verification Script

```bash
# Run validation
python validate_system.py

# Should output:
# ✓ 40+ tests passed
# ✓ Pass rate 90%+
# ✓ SYSTEM READY FOR PRODUCTION
```

### Manual Testing Checklist

```
□ Server starts without errors
  curl https://yourdomain/health

□ Dashboard loads
  Open https://yourdomain in browser
  
□ Telegram bot responds
  Send message to bot on Telegram
  
□ Lead hunting works
  Message: "Find 5 leads for luxury car dealers"
  Bot should respond with leads in 2-5 seconds
  
□ Leads saved to database
  Check: https://yourdomain/api/leads
  
□ Mission Control loads
  All 10 screens should be accessible
  
□ Telegram webhook registered
  Check: /health endpoint shows "Operational"
  
□ Security working
  Test API without X-API-Key header
  Should return 403 Unauthorized
```

### Performance Testing

```bash
# Check response time
time curl https://yourdomain/api/health

# Check queue depth
curl https://yourdomain/api/health | jq '.queue_depth'

# Check memory
curl https://yourdomain/api/health | jq '.memory'

# Monitor for 1 hour
watch -n 10 'curl -s https://yourdomain/api/health | jq'
```

---

## 🔧 TROUBLESHOOTING

### Common Issues & Solutions

#### Issue 1: Telegram bot not responding

**Symptoms:** Send message → Bot doesn't reply

**Solution:**
1. Verify TELEGRAM_BOT_TOKEN is set correctly
   ```bash
   curl https://yourdomain/health
   # Check: "Operational" status
   ```

2. Check webhook registration in logs
   ```
   # Look for: "Telegram webhook registered: https://yourdomain/telegram"
   ```

3. Test webhook manually:
   ```bash
   curl -X POST https://yourdomain/telegram \
     -H "Content-Type: application/json" \
     -d '{
       "message": {
         "chat": {"id": 123},
         "text": "hello"
       }
     }'
   ```

4. If still failing:
   - Redeploy application
   - Check firewall allows HTTPS
   - Verify domain is accessible

#### Issue 2: Mission Control dashboard shows blank

**Symptoms:** Page loads but empty/no data

**Solution:**
1. Open browser Developer Tools (F12)
2. Check Network tab for failed requests
3. Verify dashboard secret in localStorage:
   ```javascript
   localStorage.getItem('OROVA_DASHBOARD_SECRET')
   ```
4. Should equal your DASHBOARD_API_KEY
5. Update if needed:
   ```javascript
   localStorage.setItem('OROVA_DASHBOARD_SECRET', 'your-secret-here')
   ```
6. Refresh page

#### Issue 3: Leads not being saved

**Symptoms:** Lead hunt runs but no leads in database

**Solution:**
1. Check database connection:
   ```bash
   curl https://yourdomain/api/leads
   ```
   
2. If empty, manually trigger hunt:
   ```bash
   curl -X POST https://yourdomain/api/actions/hunt-leads \
     -H "X-API-Key: nova_admin_2026"
   ```

3. Check logs for errors:
   ```
   Look for: "[LEAD FINDER]" messages
   Look for: Any exception errors
   ```

4. Verify Google Sheets (if configured):
   - Sheet exists: "OROVA CRM"
   - Tabs exist: Leads, Metrics, CallLog, Meetings
   - Sheet is shared with service account

#### Issue 4: Rate limiting / too many requests

**Symptoms:** Getting 429 or "Rate limit exceeded" errors

**Solution:**
1. Check rate limit status:
   ```bash
   curl https://yourdomain/api/health | jq '.memory.rate_limit'
   ```

2. Wait 30 seconds and retry

3. If persistent:
   - Adjust rate limits in `app/core/hardening.py`
   - Redeploy
   - Or contact support

#### Issue 5: Out of memory / OOM killer

**Symptoms:** Application crashes, restarts

**Solution:**
1. On Render free tier (512MB):
   - Disable optional features
   - Reduce Telegram queue size
   - Enable memory monitoring

2. Check memory status:
   ```bash
   curl https://yourdomain/api/health | jq '.memory'
   ```

3. Upgrade to Render paid tier for more memory

### Debug Mode

Enable detailed logging:

1. Set environment variable:
   ```
   DEBUG=1
   LOG_LEVEL=DEBUG
   ```

2. Restart application

3. Check logs for "DEBUG:" prefixed messages

---

## 📊 OPERATIONS GUIDE

### Daily Operations

**Morning Checklist:**
```
□ Check health status: /api/health
□ Review overnight leads: /api/leads
□ Check email replies: /api/actions/send-emails
□ Review analytics: Mission Control → Analytics screen
```

**Regular Maintenance:**
```
Weekly:
  □ Review system logs
  □ Check database size
  □ Verify backups to Google Drive
  □ Monitor cost tracking (if applicable)

Monthly:
  □ Rotate API keys (optional)
  □ Update dependencies
  □ Review lead quality metrics
  □ Audit skills performance
```

### Monitoring Dashboard

Access real-time metrics:
```
Status Page: https://yourdomain/api/health
Full Metrics: https://yourdomain/api/observability/dashboard
Performance: https://yourdomain/api/observability/performance
Security: https://yourdomain/api/hardening/metrics
```

### Backup & Recovery

**Automatic Backups:**
- SQLite: Create `orova.db` snapshots hourly
- Google Sheets: Backed up to Google Drive
- Cloud backups: Can be restored via `/api/actions/generate-report`

**Manual Backup:**
```bash
curl -X POST https://yourdomain/api/actions/generate-report \
  -H "X-API-Key: nova_admin_2026"
# Returns backup filename
```

**Restore from Backup:**
```bash
# System auto-restores from latest backup on startup
# If database is empty, pulls from Google Sheets
# On restart, previous state is recovered
```

### Scaling for Growth

As you grow:

1. **More Leads:**
   - Upgrade to Render Pro/Paid tier (2GB+ RAM)
   - Add database indexing
   - Enable Redis for caching

2. **More Agents:**
   - Current: 6 agents (Nova, Hawk, Closer, Quill, Sentinel, Oracle)
   - Can be scaled to 10+ agents
   - Increase worker processes

3. **More Clients (Multi-Tenant):**
   - Multi-tenant support built in
   - Create clients via `/api/clients`
   - Switch workspaces in dashboard

---

## 🎉 LAUNCH CHECKLIST

Final checklist before going live:

- [ ] TELEGRAM_BOT_TOKEN configured
- [ ] RENDER_EXTERNAL_URL configured
- [ ] Bot responds to Telegram messages
- [ ] Dashboard loads and functions
- [ ] Lead hunting works end-to-end
- [ ] Leads save to database
- [ ] System health is "Operational"
- [ ] No critical errors in logs
- [ ] API endpoints respond correctly
- [ ] Security headers present
- [ ] API key authentication working
- [ ] Rate limiting active
- [ ] Backup system configured
- [ ] Monitoring set up
- [ ] Team trained on usage
- [ ] Documentation shared
- [ ] Support plan in place

---

## 📞 SUPPORT RESOURCES

**System Status:**
- Health endpoint: `/api/health`
- Dashboard: `/api/observability/dashboard`
- Error logs: Check application logs

**Documentation:**
- PRODUCTION_READY.md - Complete feature list
- SYSTEM_AUDIT.md - Audit results
- This file - Deployment guide

**Troubleshooting:**
- See "Troubleshooting" section above
- Run: `python validate_system.py`
- Check: Application logs

---

## ✅ DEPLOYMENT SUCCESS CRITERIA

Your deployment is successful when:

✅ System Health: "Operational"  
✅ Telegram Bot: Responds to messages  
✅ Dashboard: All screens load  
✅ API: All endpoints respond  
✅ Database: Leads persist  
✅ Security: API key auth active  
✅ Monitoring: Health checks working  

---

## 🚀 YOU'RE READY!

Congratulations! Your OROVA Nova AI Agency Engine is now **LIVE AND OPERATIONAL**.

### What You Can Do Right Now:

1. **Hunt Leads** - Tell Nova: "Find 10 luxury car dealers in Los Angeles"
2. **Review Leads** - Go to Mission Control → Leads screen
3. **Manage Tasks** - Use the Task Board for team coordination
4. **Monitor Performance** - Check Analytics dashboard
5. **Send Emails** - Nova can send outreach automatically
6. **Make Calls** - If Retell.ai configured, Nova makes calls too

### Next Steps:

1. Train your team on the system
2. Configure email templates
3. Set up calling prompts (if using Retell)
4. Monitor first week of operations
5. Optimize based on results

---

**Questions? Something not working?**

1. Check `/api/health` status
2. Run `python validate_system.py`
3. Review troubleshooting section
4. Check application logs

**Enjoy your autonomous AI agency!** 🎉

---

**Document Version:** 1.0  
**Last Updated:** May 22, 2026  
**Status:** ✅ PRODUCTION READY
