#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# BOT-AUTO-TRADE-IG — Interactive installer for Ubuntu 24.04
# ============================================================
# This script:
#   1. Installs Docker & Docker Compose
#   2. Auto-generates all secrets (DB, Redis, JWT/encryption, Grafana)
#   3. Asks for domain name + email for Let's Encrypt
#   4. Builds & starts all services
#   5. Obtains SSL certificate automatically
#   6. Sets up cron for backups + SSL renewal
# ============================================================

APP_DIR="/opt/bot-auto-trade-ig"
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}BOT AUTO TRADE IG — Installation${NC}               ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  Automated Trading Bot for IG Markets            ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
}

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; }
ask()     { echo -e -n "${CYAN}[?]${NC} $1"; }

# ----------------------------------------------------------
# Pre-flight checks
# ----------------------------------------------------------
banner

if [[ $EUID -eq 0 ]]; then
    error "Do not run this script as root. Run as a regular user with sudo access."
    exit 1
fi

if ! grep -qE "Ubuntu (22|24)" /etc/os-release 2>/dev/null; then
    warn "This script is designed for Ubuntu 22.04/24.04. Proceed with caution."
fi

# ----------------------------------------------------------
# Step 1: Install system dependencies
# ----------------------------------------------------------
info "Step 1/7 — Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release git make openssl ufw > /dev/null

# ----------------------------------------------------------
# Step 2: Install Docker
# ----------------------------------------------------------
info "Step 2/7 — Installing Docker..."
if ! command -v docker &>/dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin > /dev/null
    sudo usermod -aG docker "$USER"
    info "Docker installed. Group membership will apply after re-login."
else
    info "Docker already installed — $(docker --version)"
fi

# ----------------------------------------------------------
# Step 3: Configure firewall
# ----------------------------------------------------------
info "Step 3/7 — Configuring firewall..."
sudo ufw allow 22/tcp   > /dev/null 2>&1   # SSH
sudo ufw allow 80/tcp   > /dev/null 2>&1   # HTTP (Let's Encrypt + redirect)
sudo ufw allow 443/tcp  > /dev/null 2>&1   # HTTPS
sudo ufw --force enable > /dev/null 2>&1
info "Firewall configured (SSH, HTTP, HTTPS)."

# ----------------------------------------------------------
# Step 4: Setup project directory
# ----------------------------------------------------------
info "Step 4/7 — Setting up project directory..."
sudo mkdir -p "$APP_DIR"
sudo chown "$USER":"$USER" "$APP_DIR"

if [ -f "docker-compose.yml" ]; then
    # Running from within the repo
    rsync -a --exclude='.git' --exclude='node_modules' --exclude='__pycache__' . "$APP_DIR/"
elif [ -d "$APP_DIR/docker-compose.yml" ]; then
    info "Project files already present."
else
    # Clone from GitHub
    ask "GitHub repository URL (e.g. https://github.com/user/BOT-AUTO-TRADE-IG.git): "
    read -r REPO_URL
    git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

# ----------------------------------------------------------
# Step 5: Interactive configuration
# ----------------------------------------------------------
info "Step 5/7 — Configuring environment..."

echo ""
echo -e "${BOLD}All passwords and secrets will be auto-generated.${NC}"
echo -e "${BOLD}IG Markets credentials can be configured later via the web admin.${NC}"
echo ""

# --- Domain ---
ask "Domain name (e.g. trading.mydomain.com) or press Enter for IP-only access: "
read -r DOMAIN
DOMAIN="${DOMAIN:-localhost}"

LETSENCRYPT_EMAIL=""
SETUP_SSL=false
if [[ "$DOMAIN" != "localhost" && "$DOMAIN" != *"."*"."* ]] || [[ "$DOMAIN" == *"."*"."* ]]; then
    if [[ "$DOMAIN" != "localhost" ]]; then
        ask "Email for Let's Encrypt SSL certificate: "
        read -r LETSENCRYPT_EMAIL
        if [[ -n "$LETSENCRYPT_EMAIL" ]]; then
            SETUP_SSL=true
        fi
    fi
fi

# --- Admin account ---
ask "Dashboard admin username [admin]: "
read -r ADMIN_USER
ADMIN_USER="${ADMIN_USER:-admin}"

while true; do
    ask "Dashboard admin password (min 8 chars): "
    read -rs ADMIN_PASS
    echo ""
    if [[ ${#ADMIN_PASS} -ge 8 ]]; then
        break
    fi
    warn "Password must be at least 8 characters."
done

# --- Auto-generate all secrets ---
info "Generating secure passwords and keys..."
DB_PASSWORD=$(openssl rand -hex 16)
REDIS_PASSWORD=$(openssl rand -hex 16)
DASHBOARD_SECRET_KEY=$(openssl rand -hex 32)
GRAFANA_PASSWORD=$(openssl rand -base64 12 | tr -d '=/+' | head -c 16)

# --- Write .env ---
cat > "$APP_DIR/.env" <<ENVEOF
# ============================================================
# BOT-AUTO-TRADE-IG — Auto-generated configuration
# Generated on $(date -Iseconds)
# ============================================================
# IG credentials are configured via the web admin interface.
# Do NOT edit secrets below unless you know what you're doing.
# Changing DASHBOARD_SECRET_KEY will invalidate all encrypted
# settings stored in the database.
# ============================================================

# Database (TimescaleDB)
DB_HOST=timescaledb
DB_PORT=5432
DB_NAME=trading_db
DB_USER=trader
DB_PASSWORD=${DB_PASSWORD}

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=${REDIS_PASSWORD}

# Dashboard
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8000
DASHBOARD_SECRET_KEY=${DASHBOARD_SECRET_KEY}

# Admin account (used for first-time setup)
ADMIN_USERNAME=${ADMIN_USER}
ADMIN_PASSWORD=${ADMIN_PASS}

# Domain & SSL
DOMAIN=${DOMAIN}
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL}

# Monitoring
GRAFANA_PASSWORD=${GRAFANA_PASSWORD}

# Bot
BOT_LOG_LEVEL=INFO
ENVEOF

chmod 600 "$APP_DIR/.env"
info ".env created with auto-generated secrets."

# ----------------------------------------------------------
# Step 6: Build and start services
# ----------------------------------------------------------
info "Step 6/7 — Building Docker images (this may take a few minutes)..."

# Use HTTP-only nginx config initially (before SSL cert exists)
if [[ "$SETUP_SSL" == true ]]; then
    cp "$APP_DIR/nginx/conf.d/app-http-only.conf" "$APP_DIR/nginx/conf.d/app.conf.bak" 2>/dev/null || true
    # Temporarily use HTTP-only config for initial startup
    cp "$APP_DIR/nginx/conf.d/app-http-only.conf" "$APP_DIR/nginx/conf.d/app.conf"
fi

# Need to use sg to apply docker group in current session if just added
if groups | grep -q docker; then
    docker compose build
    docker compose up -d
else
    info "Applying docker group (using sg)..."
    sg docker -c "docker compose build"
    sg docker -c "docker compose up -d"
fi

# Wait for services to be healthy
info "Waiting for services to start..."
sleep 10

# Check services
if docker compose ps | grep -q "Up"; then
    info "All services started successfully."
else
    warn "Some services may not have started. Check with: docker compose ps"
fi

# ----------------------------------------------------------
# Step 7: SSL certificate (if domain provided)
# ----------------------------------------------------------
if [[ "$SETUP_SSL" == true ]]; then
    info "Step 7/7 — Obtaining SSL certificate for ${DOMAIN}..."
    echo ""
    warn "Make sure your domain ${DOMAIN} points to this server's IP address!"
    ask "Press Enter to continue with SSL setup (or Ctrl+C to skip)..."
    read -r

    # Obtain certificate
    if docker compose run --rm certbot certonly \
        --webroot -w /var/www/certbot \
        --email "$LETSENCRYPT_EMAIL" \
        --agree-tos --no-eff-email \
        -d "$DOMAIN"; then

        # Restore full SSL nginx config
        if [[ -f "$APP_DIR/nginx/conf.d/app.conf.bak" ]]; then
            # Use the SSL-enabled template
            cp "$APP_DIR/nginx/conf.d/app-ssl.conf" "$APP_DIR/nginx/conf.d/app.conf"
        fi

        # Restart nginx with SSL config
        docker compose restart nginx
        info "SSL certificate obtained and configured!"

        # Setup auto-renewal cron
        (crontab -l 2>/dev/null || true; echo "0 3 1,15 * * cd $APP_DIR && docker compose run --rm certbot renew --webroot -w /var/www/certbot --quiet && docker compose restart nginx") | sort -u | crontab -
        info "SSL auto-renewal cron configured (1st & 15th of each month)."
    else
        error "SSL certificate generation failed. You can retry later with:"
        echo "  cd $APP_DIR && make ssl DOMAIN=$DOMAIN EMAIL=$LETSENCRYPT_EMAIL"
    fi
else
    info "Step 7/7 — Skipping SSL (no domain configured)."
fi

# ----------------------------------------------------------
# Setup backup cron
# ----------------------------------------------------------
info "Setting up daily backup cron (3:00 AM)..."
chmod +x "$APP_DIR/scripts/backup.sh"
(crontab -l 2>/dev/null || true; echo "0 3 * * * cd $APP_DIR && bash scripts/backup.sh") | sort -u | crontab -

# ----------------------------------------------------------
# Summary
# ----------------------------------------------------------
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}  ${BOLD}Installation complete!${NC}                          ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Dashboard:${NC}"
if [[ "$SETUP_SSL" == true ]]; then
    echo -e "    URL:      ${CYAN}https://${DOMAIN}${NC}"
else
    echo -e "    URL:      ${CYAN}http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):80${NC}"
fi
echo -e "    Login:    ${CYAN}${ADMIN_USER}${NC} / (password you entered)"
echo ""
echo -e "  ${BOLD}Grafana:${NC}"
echo -e "    URL:      ${CYAN}http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):3001${NC}"
echo -e "    Login:    ${CYAN}admin${NC} / ${CYAN}${GRAFANA_PASSWORD}${NC}"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo -e "    1. Log into the dashboard"
echo -e "    2. Go to ${BOLD}Settings > IG Account${NC} — enter your IG API credentials"
echo -e "    3. Go to ${BOLD}Settings > Markets${NC} — add markets to watch"
echo -e "    4. Go to ${BOLD}Settings > Strategies${NC} — enable trading strategies"
echo -e "    5. Start the bot from the dashboard"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "    ${CYAN}cd $APP_DIR${NC}"
echo -e "    ${CYAN}make logs${NC}        — view live logs"
echo -e "    ${CYAN}make restart${NC}     — restart bot & dashboard"
echo -e "    ${CYAN}make backup${NC}      — backup database now"
echo -e "    ${CYAN}make down${NC}        — stop all services"
echo ""
echo -e "  ${YELLOW}Save the Grafana password above — it won't be shown again!${NC}"
echo ""
