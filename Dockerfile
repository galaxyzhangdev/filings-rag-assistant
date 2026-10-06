# Slim Python base matching .python-version; uv copied from its official image, pinned to the local version.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /bin/

WORKDIR /app

# Install locked runtime dependencies first, so this layer is cached until pyproject.toml/uv.lock change.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# Source last (filtered by the .dockerignore allowlist: no .env, data/, or notes).
COPY . .

# Run from the venv built above; don't re-sync (or pull dev deps) at container start.
ENV UV_NO_SYNC=1
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
