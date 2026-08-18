# ---- 前端构建阶段 ----
FROM node:22-slim AS webui
WORKDIR /app/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# ---- 后端运行阶段 ----
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY backend/ /app/backend/
RUN uv sync --project backend --extra server --no-dev

COPY --from=webui /app/frontend/dist /app/frontend/dist

RUN mkdir -p /app/Downloaded
VOLUME ["/app/Downloaded", "/app/config.yml"]

ENTRYPOINT ["uv", "run", "--project", "backend", "douyin-dl"]
CMD ["-c", "config.yml"]
