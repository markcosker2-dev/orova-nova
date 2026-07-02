# OROVA — Oracle Cloud Deployment Runbook

## 1. Instance Provisioning
- Provider: Oracle Cloud Infrastructure (OCI).
- Shape: **VM.Standard.A1.Flex** (ARM64 Ampere).
- Compute: 4 OCPUs, 24GB RAM.
- OS: **Ubuntu 22.04 LTS (Aarch64)**.
- Boot Volume: 100GB (Performance 20 VPU).

## 2. Environment Preparation

```bash
# Update and Install PyEnv dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y make build-essential libssl-dev zlib1g-dev \
libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev \
libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev git \
nginx certbot python3-certbot-nginx

# Install Chrome for ARM64 (Crucial for Playwright/Scrapling fallback)
sudo apt install -y chromium-browser
export CHROME_PATH=/usr/bin/chromium-browser

# Install Python 3.11.4 via pyenv
curl https://pyenv.run | bash
# Add pyenv to ~/.bashrc, then source ~/.bashrc
pyenv install 3.11.4
pyenv global 3.11.4
```

## 3. Deployment Steps

```bash
# 1. Clone Repo
git clone <repo_url> /opt/orova
cd /opt/orova/openclaw_instance

# 2. Setup Virtual Environment
python -m venv venv
source venv/bin/activate

# 3. Install packages
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium

# 4. Setup Directories
sudo mkdir -p /opt/orova/data
sudo chown -R ubuntu:ubuntu /opt/orova/data
```

## 4. Configuration
Create a `.env` in `/opt/orova/openclaw_instance/.env` matching your local environment variables. Ensure `DATA_DIR=/opt/orova/data` is set.

## 5. Systemd Setup
Create `/etc/systemd/system/orova.service`:

```ini
[Unit]
Description=OROVA Mission Control Daemon
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/orova/openclaw_instance
Environment="PATH=/opt/orova/openclaw_instance/venv/bin"
EnvironmentFile=/opt/orova/openclaw_instance/.env
ExecStart=/opt/orova/openclaw_instance/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 7860

Restart=always
TimeoutStartSec=10
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable orova
sudo systemctl start orova
```

## 6. Nginx & Reverse Proxy (Optional)

In `/etc/nginx/sites-available/orova`:

```nginx
server {
    server_name dashboard.orova.co;
    
    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/orova /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d dashboard.orova.co
```
