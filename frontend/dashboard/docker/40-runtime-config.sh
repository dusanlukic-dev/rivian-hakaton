#!/bin/sh
# Runs at container start (nginx image hook): what only the host knows, for the phone QR on the car screen.
# HOST_IP = the laptop's LAN IP (start.ps1 sets it in docker/.env), BACKEND_PORT = the coordinator's port on the host.
set -e
cat > /usr/share/nginx/html/runtime-config.js <<EOF
window.__RUNTIME__ = { lanIp: "${HOST_IP:-}", backendPort: ${BACKEND_PORT:-8000} };
EOF
echo "runtime-config.js: lanIp=${HOST_IP:-<none>} backendPort=${BACKEND_PORT:-8000}"
