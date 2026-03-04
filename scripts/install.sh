#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Installation script for BOT-AUTO-TRADE-IG on Ubuntu 24.04
# ============================================================

echo "=== Bot Auto Trade IG - Installation Ubuntu 24.04 ==="

# Check Ubuntu version
if ! grep -q "24.04" /etc/os-release 2>/dev/null; then
    echo "Warning: This script is designed for Ubuntu 24.04"
fi

# Update system
echo ">>> Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y

# Install prerequisites
echo ">>> Installing prerequisites..."
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    make \
    ufw \
    openssl

# Install Docker (official method)
echo ">>> Installing Docker..."
if ! command -v docker &>/dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Add current user to docker group
    sudo usermod -aG docker "$USER"
    echo ">>> Docker installed. You may need to log out and back in for group changes."
else
    echo ">>> Docker already installed."
fi

# Configure firewall
echo ">>> Configuring firewall..."
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (for Let's Encrypt challenge)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw --force enable

# Create application directory
APP_DIR="/opt/bot-auto-trade-ig"
echo ">>> Setting up application directory at ${APP_DIR}..."
sudo mkdir -p "$APP_DIR"
sudo chown "$USER":"$USER" "$APP_DIR"

# Copy project files if running from repo
if [ -f "docker-compose.yml" ]; then
    echo ">>> Copying project files..."
    cp -r . "$APP_DIR/"
fi

# Setup environment file with auto-generated secrets
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"

        # Generate secure passwords automatically
        DB_PASS=$(openssl rand -hex 16)
        REDIS_PASS=$(openssl rand -hex 16)
        SECRET_KEY=$(openssl rand -hex 32)
        GRAFANA_PASS=$(openssl rand -hex 8)

        sed -i "s/change_me_strong_password_here/${DB_PASS}/" "$APP_DIR/.env"
        sed -i "s/REDIS_PASSWORD=change_me_strong_password_here/REDIS_PASSWORD=${REDIS_PASS}/" "$APP_DIR/.env"
        sed -i "s/change_me_generate_with_openssl_rand_hex_32/${SECRET_KEY}/" "$APP_DIR/.env"
        sed -i "s/admin_change_me/${GRAFANA_PASS}/" "$APP_DIR/.env"

        echo ">>> Created .env with auto-generated passwords"
        echo ">>> DB_PASSWORD=${DB_PASS}"
        echo ">>> REDIS_PASSWORD=${REDIS_PASS}"
        echo ">>> GRAFANA_PASSWORD=${GRAFANA_PASS}"
        echo ">>> Save these passwords if needed!"
    fi
fi

# Create log directory
mkdir -p "$APP_DIR/logs"

echo ""
echo "=============================================="
echo "  Installation complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo ""
echo "  1. cd $APP_DIR"
echo ""
echo "  2. Edit .env and set your domain:"
echo "     nano .env"
echo "     -> DOMAIN=trading.yourdomain.com"
echo "     -> LETSENCRYPT_EMAIL=you@yourdomain.com"
echo ""
echo "  3. Build and start all services:"
echo "     make build"
echo "     make up"
echo ""
echo "  4. Setup SSL certificate (requires domain pointing to this server):"
echo "     make ssl DOMAIN=trading.yourdomain.com EMAIL=you@email.com"
echo ""
echo "  5. Open your browser:"
echo "     https://trading.yourdomain.com"
echo ""
echo "  6. Create your admin account (first-time setup screen)"
echo ""
echo "  7. Configure IG Markets credentials in: Config > IG Account"
echo ""
echo "  8. Add markets to watchlist in: Config > Markets"
echo ""
echo "  9. Configure risk parameters and start the bot in: Config > Risk & Bot"
echo ""
echo "For logs:        make logs"
echo "For dev mode:    make dev"
echo "To stop:         make down"
