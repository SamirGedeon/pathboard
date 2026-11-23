FROM node:24.22-bookworm-slim AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build
FROM python:3.12-slim-bookworm AS api
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/pathboard ./pathboard
COPY --from=web /build/web/dist /app/web/dist
RUN mkdir /app/var && chown 65532:65532 /app/var
ENV PATH="/app/backend/.venv/bin:$PATH" DB_PATH=/app/var/pathboard.sqlite WEB_DIR=/app/web/dist APP_ENV=production
USER 65532:65532
EXPOSE 8000
CMD ["uvicorn","pathboard.main:create_app","--factory","--no-proxy-headers","--host","0.0.0.0","--port","8000"]
