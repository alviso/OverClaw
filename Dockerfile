FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile
COPY frontend/ ./
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
RUN yarn build

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx curl libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && playwright install chromium

COPY backend/ backend/
COPY --from=frontend-build /app/frontend/build /app/frontend-static
COPY memory/ memory/

# nginx serves frontend static + proxies /api to backend
RUN cat > /etc/nginx/conf.d/default.conf <<'NGINX'
server {
    listen 80;
    root /app/frontend-static;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX
RUN rm -f /etc/nginx/sites-enabled/default

COPY <<'ENTRY' /app/entrypoint.sh
#!/bin/sh
set -e
mkdir -p /app/workspace/projects
cd /app/backend
uvicorn server:app --host 0.0.0.0 --port 8001 &
nginx -g "daemon off;"
ENTRY
RUN chmod +x /app/entrypoint.sh

EXPOSE 80
CMD ["/app/entrypoint.sh"]
