FROM python:3.14-slim

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# use the image's interpreter rather than letting uv download a second one
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY src/ src/
COPY tests/ tests/

CMD ["uv", "run", "python", "-m", "src.main"]