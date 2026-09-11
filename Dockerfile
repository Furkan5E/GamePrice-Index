FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# use the image's interpreter rather than letting uv download a second one
ENV UV_PYTHON_DOWNLOADS=never

# run as an unprivileged user; data/ and plots/ are created up front so mounted volumes stay writable
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data /app/plots \
    && chown -R app:app /app
USER app
ENV MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# install dependencies first so this layer is cached until the lockfile changes
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY --chown=app:app README.md ./
COPY --chown=app:app src/ src/
COPY --chown=app:app tests/ tests/
RUN uv sync --frozen

CMD ["uv", "run", "gameprice-index"]
