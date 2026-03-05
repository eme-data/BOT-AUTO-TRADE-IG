#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# BOT-AUTO-TRADE-IG — Interactive installer for Ubuntu 22/24
# ============================================================
# Run as root:  sudo bash scripts/install.sh
#
# This script:
#   1. Installs Docker & Docker Compose
#   2. Auto-generates all secrets (DB, Redis, JWT/encryption, Grafana)
#   3. Asks for domain name + email for Let's Encrypt
#   4. Builds & starts all services
#   5. Obtains SSL certificate automatically
#   6. Sets up cron for backups + SSL renewal
# ============================================================

APP_DIR="/opt/bot-auto-trade-ig"
REPO_URL="https://github.com/eme-data/BOT-AUTO-TRADE-IG.git"

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

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

if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root."
    echo "  Usage: sudo bash scripts/install.sh"
    exit 1
fi

if ! grep -qE "Ubuntu (22|24)" /etc/os-release 2>/dev/null; then
    warn "This script is designed for Ubuntu 22.04/24.04. Proceed with caution."
fi

# ----------------------------------------------------------
# Step 1: Install system dependencies
# ----------------------------------------------------------
info "Step 1/7 — Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release git make openssl ufw > /dev/null 2>&1

# ----------------------------------------------------------
# Step 2: Install Docker
# ----------------------------------------------------------
info "Step 2/7 — Installing Docker..."
if ! command -v docker &>/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin > /dev/null 2>&1
    info "Docker installed."
else
    info "Docker already installed — $(docker --version)"
fi

# ----------------------------------------------------------
# Step 3: Configure firewall
# ----------------------------------------------------------
info "Step 3/7 — Configuring firewall..."
ufw allow 22/tcp   > /dev/null 2>&1
ufw allow 80/tcp   > /dev/null 2>&1
ufw allow 443/tcp  > /dev/null 2>&1
ufw --force enable > /dev/null 2>&1
info "Firewall configured (SSH, HTTP, HTTPS)."

# ----------------------------------------------------------
# Step 4: Get project files
# ----------------------------------------------------------
info "Step 4/7 — Setting up project at ${APP_DIR}..."

if [ -d "$APP_DIR/.git" ]; then
    info "Project already exists — pulling latest changes..."
    cd "$APP_DIR"
    git pull --ff-only
elif [ -f "docker-compose.yml" ]; then
    # Running from within a cloned repo — copy to APP_DIR
    info "Copying project files to ${APP_DIR}..."
    mkdir -p "$APP_DIR"
    cp -a . "$APP_DIR/"
    cd "$APP_DIR"
else
    info "Cloning repository..."
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# ----------------------------------------------------------
# Step 5: Interactive configuration
# ----------------------------------------------------------
info "Step 5/7 — Configuring environment..."

# Skip config if .env already exists
if [ -f "$APP_DIR/.env" ]; then
    warn ".env already exists. Skipping configuration."
    warn "Delete .env and re-run the installer to reconfigure."
else
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
    if [[ "$DOMAIN" != "localhost" ]]; then
        ask "Email for Let's Encrypt SSL certificate: "
        read -r LETSENCRYPT_EMAIL
        if [[ -n "$LETSENCRYPT_EMAIL" ]]; then
            SETUP_SSL=true
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
fi

# Load variables from .env for later steps
export $(grep -v '^#' "$APP_DIR/.env" | grep -v '^\s*$' | xargs)

# Determine if SSL should be set up
SETUP_SSL=${SETUP_SSL:-false}
if [[ "$SETUP_SSL" == false && "${DOMAIN:-localhost}" != "localhost" && -n "${LETSENCRYPT_EMAIL:-}" ]]; then
    SETUP_SSL=true
fi

# ----------------------------------------------------------
# Step 6: Build and start services
# ----------------------------------------------------------
info "Step 6/7 — Building Docker images (this may take a few minutes)..."

# Use HTTP-only nginx config initially if SSL will be set up
# (cert doesn't exist yet, so nginx would fail with the SSL config)
if [[ "$SETUP_SSL" == true ]] || [[ ! -d "/etc/letsencrypt/live/${DOMAIN:-localhost}" ]]; then
    cp "$APP_DIR/nginx/conf.d/app-http-only.conf.tpl" "$APP_DIR/nginx/conf.d/app.conf.template"
    info "Using HTTP-only config (SSL will be configured after certificate is obtained)."
fi

cd "$APP_DIR"
docker compose build
docker compose up -d

# Wait for services to be healthy
info "Waiting for services to start..."
sleep 15

# Check services
if docker compose ps --format '{{.Status}}' | grep -qi "up"; then
    info "All services started successfully."
else
    warn "Some services may not have started. Check with: docker compose ps"
    docker compose ps
fi

# ----------------------------------------------------------
# Step 7: SSL certificate (if domain provided)
# ----------------------------------------------------------
if [[ "$SETUP_SSL" == true ]]; then
    info "Step 7/7 — Obtaining SSL certificate for ${DOMAIN}..."
    echo ""
    warn "Make sure your domain ${DOMAIN} points to this server's IP address!"
    SERVER_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || echo "unknown")
    info "This server's public IP: ${SERVER_IP}"
    echo ""
    ask "Press Enter to continue with SSL setup (or Ctrl+C to skip)..."
    read -r

    # Obtain certificate via certbot in Docker
    if docker compose run --rm certbot certonly \
        --webroot -w /var/www/certbot \
        --email "$LETSENCRYPT_EMAIL" \
        --agree-tos --no-eff-email \
        -d "$DOMAIN"; then

        # Switch to SSL nginx config
        cp "$APP_DIR/nginx/conf.d/app-ssl.conf.tpl" "$APP_DIR/nginx/conf.d/app.conf.template"
        docker compose restart nginx
        info "SSL certificate obtained and nginx configured with HTTPS!"

        # Setup auto-renewal cron (runs as root)
        CRON_SSL="0 3 1,15 * * cd $APP_DIR && docker compose run --rm certbot renew --webroot -w /var/www/certbot --quiet && docker compose restart nginx"
        (crontab -l 2>/dev/null | grep -v "certbot renew" || true; echo "$CRON_SSL") | crontab -
        info "SSL auto-renewal cron configured (1st & 15th of each month)."
    else
        error "SSL certificate generation failed."
        echo ""
        echo "  Possible causes:"
        echo "    - Domain ${DOMAIN} does not point to this server"
        echo "    - Port 80 is not reachable from the internet"
        echo ""
        echo "  You can retry later with:"
        echo "    cd $APP_DIR && make ssl DOMAIN=$DOMAIN EMAIL=$LETSENCRYPT_EMAIL"
        echo ""
    fi
else
    info "Step 7/7 — Skipping SSL (no domain configured)."
fi

# ----------------------------------------------------------
# Setup backup cron
# ----------------------------------------------------------
info "Setting up daily backup cron (3:00 AM)..."
chmod +x "$APP_DIR/scripts/backup.sh"
CRON_BACKUP="0 3 * * * cd $APP_DIR && bash scripts/backup.sh"
(crontab -l 2>/dev/null | grep -v "backup.sh" || true; echo "$CRON_BACKUP") | crontab -
info "Database backup scheduled daily at 3:00 AM."

# ----------------------------------------------------------
# Summary
# ----------------------------------------------------------
SERVER_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || echo 'YOUR_IP')

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}  ${BOLD}Installation complete!${NC}                              ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Dashboard:${NC}"
if [[ "$SETUP_SSL" == true ]] && [[ -d "/etc/letsencrypt/live/${DOMAIN:-localhost}" ]] 2>/dev/null; then
    echo -e "    URL:      ${CYAN}https://${DOMAIN}${NC}"
else
    echo -e "    URL:      ${CYAN}http://${SERVER_IP}${NC}"
fi
echo -e "    Login:    ${CYAN}${ADMIN_USERNAME:-${ADMIN_USER:-admin}}${NC} / (password you entered)"
echo ""
echo -e "  ${BOLD}Grafana:${NC}"
echo -e "    URL:      ${CYAN}http://${SERVER_IP}:3001${NC}"
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
