# OROVA — Oracle Cloud Free Tier Deployment
# VM.Standard.A1.Flex | 4 OCPU | 24GB RAM | ARM64 Ampere | FREE FOREVER

## STEP 1 — Provision VM (15 minutes)

1. cloud.oracle.com → Create Account
2. Compute → Create Instance
   - Shape: VM.Standard.A1.Flex (Ampere ARM64)
   - OCPU: 4, Memory: 24GB  ← ALL FREE
   - Image: Ubuntu 22.04 Minimal (ARM64)
   - Networking: Create new VCN OR use existing
   - SSH Keys: Generate or upload your public key
3. Save the instance public IP
4. Open Security List ports:
   Networking → VCN → Security List → Add Ingress:
   - TCP 22   (SSH)
   - TCP 7860 (OROVA dashboard)
   - TCP 80   (HTTP, optional)
   - TCP 443  (HTTPS, if using nginx + certbot)


## STEP 2 — Connect and provision

ssh -i ~/.ssh/your-key.pem ubuntu@YOUR_ORACLE_IP


## STEP 3 — System setup

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip \
  git nginx certbot python3-certbot-nginx \
  curl wget build-essential


## STEP 4 — ARM64 Chromium (CRITICAL — Playwright default x64 won't work)

# Option A: System Chromium (ARM64 native, recommended)
sudo apt install -y chromium-browser

# Verify it works:
chromium-browser --version

# Set environment variable so Playwright/browser_utils.py finds it:
echo "CHROME_PATH=/usr/bin/chromium-browser" >> /etc/orova.env

# Option B: Playwright ARM64 build (if system chromium not available)
# pip install playwright
# PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright playwright install chromium
# Note: Official Playwright ARM64 support added in v1.37. If older, use Option A.


## STEP 5 — Deploy OROVA code

git clone YOUR_REPO_URL /opt/orova
cd /opt/orova
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install Playwright browsers (after setting CHROME_PATH above, may skip)
playwright install chromium || true  # non-fatal if using system chromium


## STEP 6 — Environment file (secrets never in git)

sudo nano /etc/orova.env

# Paste all your environment variables — one per line:
# TELEGRAM_BOT_TOKEN=xxx
# ADMIN_CHAT_ID=xxx
# OPENAI_API_KEY=xxx
# GROQ_API_KEY=xxx
# RETELL_API_KEY=xxx
# RETELL_AGENT_ID=xxx
# RETELL_FROM_NUMBER=+1XXXXXXXXXX
# AGENTMAIL_API_KEY=xxx
# OROVA_API_KEY=xxx
# META_ACCESS_TOKEN=xxx
# META_AD_ACCOUNT_ID=act_xxx
# GOOGLE_APPLICATION_CREDENTIALS=/opt/orova/service_account.json
# CHROME_PATH=/usr/bin/chromium-browser
# VERTICAL_NAME=LuxuryRemodeling
# PORT=7860

sudo chmod 600 /etc/orova.env  # Protect secrets


## STEP 7 — Systemd service (auto-start, auto-restart)

sudo nano /etc/systemd/system/orova.service

[Unit]
Description=OROVA Mission Control
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/orova
EnvironmentFile=/etc/orova.env
ExecStart=/opt/orova/.venv/bin/python app/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=orova

[Install]
WantedBy=multi-user.target


sudo systemctl daemon-reload
sudo systemctl enable orova
sudo systemctl start orova

# Check status:
sudo systemctl status orova
sudo journalctl -u orova -f  # Live logs


## STEP 8 — Data directory (persistent, survives restarts)

sudo mkdir -p /opt/orova/data
sudo chown -R ubuntu:ubuntu /opt/orova/data

# Update your .env / systemd env to point OROVA data here:
# DATA_DIR=/opt/orova/data
# SQLite DB will live at: /opt/orova/data/orova.db


## STEP 9 — Nginx reverse proxy (optional but recommended for HTTPS)

sudo nano /etc/nginx/sites-available/orova

server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    location / {
        proxy_pass         http://localhost:7860;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection 'upgrade';
        proxy_set_header   Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}

sudo ln -s /etc/nginx/sites-available/orova /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# Add SSL (requires domain pointing to this IP):
sudo certbot --nginx -d your-orova-domain.com


## STEP 10 — Update Telegram + Retell webhooks

Retell Dashboard → Agent → Webhook URL:
  http://YOUR_IP:7860/webhook/retell   (or https:// after SSL)

Telegram set webhook (if using webhook mode instead of polling):
  curl "https://api.telegram.org/botTOKEN/setWebhook?url=https://your-domain.com/webhook"


## STEP 11 — Verify deployment

curl http://YOUR_ORACLE_IP:7860/health
# Expected: {"status":"ok","agency":"OROVA","ts":"..."}

# Telegram: /start
# Expected: Nova is online. All systems nominal.


## STEP 12 — First production run

# In Telegram:
# /start                          → Nova initialises
# /help                           → Full command menu
# find 10 luxury renovation leads in Los Angeles   → HAWK activates
# send outreach to found leads                      → ARIA activates


## KEY DIFFERENCES FROM HUGGINGFACE

  HuggingFace                     Oracle Cloud
  ──────────────────────────────────────────────
  Cold starts / sleeps            Always running
  /data/ needs $5/month           /opt/orova/data free
  DNS hacks for Telegram          Standard DNS works
  ARM64 Playwright issues         System chromium solves this
  No static IP                    Static IP assigned free
  Container restarts lose state   Systemd auto-restarts cleanly
  Port 7860 required              Any port (80/443 recommended)


## TROUBLESHOOTING

| Issue | Fix |
|-------|-----|
| Playwright crashes on ARM64 | Set CHROME_PATH=/usr/bin/chromium-browser |
| Telegram bot silent | Check TELEGRAM_BOT_TOKEN in /etc/orova.env |
| Port 7860 unreachable | Check Oracle Security List + UFW: sudo ufw allow 7860 |
| Service crashes on start | sudo journalctl -u orova -n 50 |
| SQLite locked | Only one process should write. Check for zombie processes. |
| Retell call fails silently | Check RETELL_FROM_NUMBER is E.164 (+12137774445) |
