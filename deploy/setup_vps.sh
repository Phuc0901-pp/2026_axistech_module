#!/usr/bin/env bash
set -euo pipefail

# Idempotent Ubuntu/Debian VPS bootstrap for AxisTech ISO ERP (Docker + Caddy + Cloudflare)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/4] Checking RAM & configuring 2GB swap if needed..."
TOTAL_MEM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo || echo 2048)
if [ "$TOTAL_MEM_MB" -lt 2048 ] && [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo "  -> Created 2GB swap (RAM=${TOTAL_MEM_MB}MB)"
else
  echo "  -> RAM=${TOTAL_MEM_MB}MB (swap check OK)"
fi

echo "[2/4] Ensuring Docker & Compose plugin are installed..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
fi
if ! docker compose version >/dev/null 2>&1; then
  sudo apt-get update -y && sudo apt-get install -y docker-compose-plugin
fi

echo "[3/4] Opening UFW firewall ports (22, 80, 443)..."
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow 22/tcp >/dev/null || true
  sudo ufw allow 80/tcp >/dev/null || true
  sudo ufw allow 443/tcp >/dev/null || true
  sudo ufw allow 443/udp >/dev/null || true
  echo "  -> UFW rules ensured (run 'sudo ufw enable' manually after verifying SSH)"
fi

echo "[4/4] Generating .env.prod with strong ISO 27001 keys (if absent)..."
if [ ! -f .env.prod ]; then
  cp deploy/.env.prod.example .env.prod
  chmod 600 .env.prod
  BRIDGE_KEY="$(openssl rand -hex 24)"
  WEBHOOK_KEY="$(openssl rand -hex 24)"
  AEAD_KEY="$(openssl rand -hex 32)"
  ERP_API="$(openssl rand -hex 24)"
  ERP_ENC="$(openssl rand -hex 32)"
  PG_PASS="$(openssl rand -hex 20)"

  sed -i "s|CHANGE_ME_BRIDGE_API_KEY|${BRIDGE_KEY}|g" .env.prod
  sed -i "s|CHANGE_ME_WEBHOOK_SECRET|${WEBHOOK_KEY}|g" .env.prod
  sed -i "s|CHANGE_ME_AEAD_KEY|${AEAD_KEY}|g" .env.prod
  sed -i "s|CHANGE_ME_ERP_API_KEY|${ERP_API}|g" .env.prod
  sed -i "s|CHANGE_ME_ERP_AES256GCM_KEY|${ERP_ENC}|g" .env.prod
  sed -i "s|CHANGE_ME_POSTGRES_PASSWORD|${PG_PASS}|g" .env.prod
  echo "  -> Generated .env.prod with randomized crypto & API keys."
else
  echo "  -> .env.prod already exists (kept unchanged)."
fi

cat <<'EOF'

==================================================================
NEXT STEPS BEFORE STARTING PRODUCTION CONTAINERS:
1. Edit .env.prod:
     nano .env.prod
   Fill in:
     - PUBLIC_DOMAIN=your-domain.example
     - AXISSTREAM_AXISSTREAM_USERNAME=...
     - AXISSTREAM_AXISSTREAM_PASSWORD=...
     - AXISSTREAM_AXISSTREAM_EXCHANGE_TOKEN=...
2. Start 24/7 Docker stack (Bridge + Go ERP + Caddy HTTPS):
     docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
   Or if running via Cloudflare Tunnel (--profile tunnel):
     docker compose -f docker-compose.prod.yml --env-file .env.prod --profile tunnel up -d --build
==================================================================
EOF
