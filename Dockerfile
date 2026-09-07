FROM python:3.14-slim

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# use the image's interpreter rather than letting uv download a second one
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# install dependencies first so this layer is cached until the lockfile changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY README.md ./
COPY src/ src/
COPY tests/ tests/
RUN uv sync --frozen

CMD ["uv", "run", "python", "-m", "gameprice_index.main"]
