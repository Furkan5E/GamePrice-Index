FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

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
RUN uv sync --frozen --no-dev --extra api --no-install-project

# only the package and its API go into the image; tests, dev tools and the dashboard stay out
COPY --chown=app:app README.md ./
COPY --chown=app:app src/ src/
RUN uv sync --frozen --no-dev --extra api

# call the installed script directly so the container never re-syncs at start-up
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["gameprice-index"]
