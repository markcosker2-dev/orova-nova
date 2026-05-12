#!/usr/bin/env bash
# OROVA Nova — Production Setup Script
# Target: Ubuntu 22.04 ARM64 (Oracle Cloud)
set -euo pipefail

OROVA_USER="orova"
OROVA_HOME="/opt/orova"
OROVA_APP="${OROVA_HOME}/app"
OROVA_DATA="${OROVA_HOME}/data"
PYTHON_VERSION="3.10"

echo "═══════════════════════════════════════════════════════"
echo "  OROVA Nova — Production Deployment"
echo "═══════════════════════════════════════════════════════"

# 1. System Packages
echo "[1/7] Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev \
    python3-pip build-essential git curl wget unzip \
    libxml2-dev libxslt1-dev libffi-dev libssl-dev \
    chromium-browser fonts-liberation libnss3 libatk-bridge2.0-0 \
    libdrm2 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libpangocairo-1.0-0 libgtk-3-0 systemd > /dev/null 2>&1

# 2. Create User
echo "[2/7] Creating user..."
if ! id -u "${OROVA_USER}" > /dev/null 2>&1; then
    useradd --system --home-dir "${OROVA_HOME}" --shell /bin/bash --create-home "${OROVA_USER}"
fi

# 3. Directories
echo "[3/7] Setting up directories..."
mkdir -p "${OROVA_HOME}" "${OROVA_DATA}" "${OROVA_APP}"
chown -R "${OROVA_USER}:${OROVA_USER}" "${OROVA_HOME}"

# 4. Copy Code
echo "[4/7] Deploying code..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "${SCRIPT_DIR}/app" ]; then
    cp -r "${SCRIPT_DIR}/app" "${OROVA_APP}/"
    cp "${SCRIPT_DIR}/requirements.txt" "${OROVA_APP}/"
    cp "${SCRIPT_DIR}/smoke_test.py" "${OROVA_APP}/" 2>/dev/null || true
    [ -f "${SCRIPT_DIR}/.env" ] && cp "${SCRIPT_DIR}/.env" "${OROVA_APP}/"
    [ -f "${SCRIPT_DIR}/.env.example" ] && cp "${SCRIPT_DIR}/.env.example" "${OROVA_APP}/"
    echo "  Code deployed."
else
    echo "  ERROR: app/ not found next to setup.sh"
    exit 1
fi

# 5. Python Env
echo "[5/7] Creating Python environment..."
python${PYTHON_VERSION} -m venv "${OROVA_HOME}/venv"
source "${OROVA_HOME}/venv/bin/activate"
pip install --upgrade pip -q
pip install --no-cache-dir -r "${OROVA_APP}/requirements.txt" -q
playwright install chromium 2>/dev/null || true
playwright install-deps chromium 2>/dev/null || true
deactivate

# 6. Smoke Test
echo "[6/7] Running smoke test..."
source "${OROVA_HOME}/venv/bin/activate"
cd "${OROVA_APP}"
export PYTHONPATH="${OROVA_HOME}"
python smoke_test.py
SMOKE_EXIT=$?
deactivate
if [ $SMOKE_EXIT -ne 0 ]; then
    echo "  SMOKE TEST FAILED. Fix before starting."
    exit 1
fi

# 7. Systemd Services
echo "[7/7] Creating systemd services..."

cat > /etc/systemd/system/orova-nova.service << EOF
[Unit]
Description=OROVA Nova — Autonomous Business OS
After=network-online.target

[Service]
Type=simple
User=${OROVA_USER}
Group=${OROVA_USER}
WorkingDirectory=${OROVA_APP}
Environment=PYTHONPATH=${OROVA_HOME}
Environment=PATH=${OROVA_HOME}/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=${OROVA_HOME}/venv/bin/python -m app.main
Restart=always
RestartSec=15
StartLimitInterval=60
StartLimitBurst=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable orova-nova.service

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  DEPLOYMENT COMPLETE"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  1. Edit ${OROVA_APP}/.env with your API keys"
echo "  2. Start:  systemctl start orova-nova"
echo "  3. Logs:   journalctl -u orova-nova -f"
echo "  4. Health: curl http://localhost:7860/health"
echo ""
