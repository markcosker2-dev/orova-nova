#!/bin/bash

set -e

echo "Starting Oracle Cloud ARM64 setup for Ubuntu 22.04..."

# Update system packages
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
echo "Installing Python 3.11 and virtual environment support..."
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# Install Chromium and verify ARM64 compatibility
echo "Installing Chromium browser..."
sudo apt install -y chromium-browser
echo "Verifying Chromium ARM64 compatibility..."
chromium --version
if [[ $? -ne 0 ]]; then
    echo "Error: Chromium installation failed. ARM64 compatibility issue."
    exit 1
fi
echo "Chromium installed successfully on ARM64."

# Install nginx and certbot
echo "Installing nginx and certbot..."
sudo apt install -y nginx certbot python3-certbot-nginx

# Create Python virtual environment
echo "Creating Python virtual environment..."
python3.11 -m venv venv

# Install Python dependencies (assuming requirements.txt exists)
echo "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
else
    echo "Warning: requirements.txt not found. Please ensure dependencies are installed manually."
fi
deactivate

# Set up environment file template
echo "Setting up environment file template..."
if [ -f .env.example ]; then
    cp .env.example .env
    echo "Copied .env.example to .env. Please edit .env with your configuration."
else
    touch .env
    echo "# Environment variables template
# Add your configuration here
DATABASE_URL=your_database_url
SECRET_KEY=your_secret_key
DEBUG=False
ALLOWED_HOSTS=your_domain.com" > .env
    echo "Created .env template. Please edit with your actual values."
fi

# Create systemd service for auto-start
echo "Creating systemd service..."
SERVICE_FILE="/etc/systemd/system/orova.service"
sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=OROVA Application Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin
ExecStart=$(pwd)/venv/bin/python app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable orova.service

# Open firewall ports
echo "Configuring firewall..."
sudo ufw --force enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Provide next steps
echo ""
echo "Setup complete! Next steps:"
echo "1. Edit the .env file with your specific configuration values."
echo "2. If using a database, ensure it's set up and accessible."
echo "3. Start the service: sudo systemctl start orova.service"
echo "4. Check service status: sudo systemctl status orova.service"
echo "5. View logs: sudo journalctl -u orova.service -f"
echo "6. Obtain SSL certificate: sudo certbot --nginx -d yourdomain.com"
echo "7. Reboot the system to ensure everything starts automatically."
echo ""
echo "Your OROVA application is now configured for Oracle Cloud ARM64."