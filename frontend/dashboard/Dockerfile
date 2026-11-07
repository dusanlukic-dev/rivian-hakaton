# Car-screen dashboard: production build served by nginx, which also proxies /api to the coordinator and the server
# (same origin, like the Vite dev proxy). Build context = repo root (vite.config.ts reads config/brand.json);
# what goes in: frontend/dashboard/Dockerfile.dockerignore. Run: docker/dashboard.yml.
FROM node:22-alpine AS build
WORKDIR /repo/frontend/dashboard
COPY frontend/dashboard/package.json frontend/dashboard/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY config/brand.json /repo/config/brand.json
COPY frontend/dashboard/ ./
# No VITE_API_URL: the build talks to its own origin (nginx proxies). LAN_IP empty: the container's IP would be
# wrong for the phone QR; the real one comes at run time (runtime-config.js, HOST_IP).
ENV LAN_IP=""
RUN npm run build

FROM nginx:1.29-alpine
COPY --from=build /repo/frontend/dashboard/dist /usr/share/nginx/html
COPY frontend/dashboard/docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY frontend/dashboard/docker/40-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-runtime-config.sh && chmod +x /docker-entrypoint.d/40-runtime-config.sh
ENV COORDINATOR_UPSTREAM=coordinator:8000 SERVER_UPSTREAM=server:8001 HOST_IP="" BACKEND_PORT=8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD wget -qO /dev/null http://127.0.0.1/ || exit 1
