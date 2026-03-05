.PHONY: build up down restart dev logs test lint clean install backup

# Production
build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

# Development
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

logs:
	docker compose logs -f

logs-bot:
	docker compose logs -f bot

logs-dashboard:
	docker compose logs -f dashboard

# Testing
test:
	docker compose exec bot python -m pytest tests/ -v

test-local:
	python -m pytest tests/ -v

# Code quality
lint:
	ruff check bot/ dashboard/api/ tests/
	ruff format --check bot/ dashboard/api/ tests/

format:
	ruff check --fix bot/ dashboard/api/ tests/
	ruff format bot/ dashboard/api/ tests/

# Database
migrate:
	docker compose exec bot alembic upgrade head

migration:
	docker compose exec bot alembic revision --autogenerate -m "$(MSG)"

# SSL / Let's Encrypt
ssl:
	docker compose run --rm certbot certonly --webroot -w /var/www/certbot \
		--email $(EMAIL) --agree-tos --no-eff-email \
		-d $(DOMAIN)
	cp nginx/conf.d/app-ssl.conf nginx/conf.d/app.conf
	docker compose restart nginx

ssl-renew:
	docker compose run --rm certbot renew --webroot -w /var/www/certbot
	docker compose restart nginx

# Switch to HTTP-only mode (no SSL)
no-ssl:
	cp nginx/conf.d/app-http-only.conf nginx/conf.d/app.conf
	docker compose restart nginx

# Backup
backup:
	bash scripts/backup.sh

# Cleanup
clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Installation (Ubuntu 22/24 — must be run as root)
install:
	@if [ "$$(id -u)" -ne 0 ]; then echo "Run as root: sudo make install"; exit 1; fi
	bash scripts/install.sh

# Frontend
frontend-install:
	cd dashboard/frontend && npm install

frontend-build:
	cd dashboard/frontend && npm run build

frontend-dev:
	cd dashboard/frontend && npm run dev
