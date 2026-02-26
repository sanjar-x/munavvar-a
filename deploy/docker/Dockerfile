# =============================================================================
# Builder Stage
# =============================================================================
FROM ghcr.io/astral-sh/uv:python3.14-trixie AS builder

# UV configuration
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies without the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy application source code
COPY . /app

# Install the project in non-editable mode
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable



# =============================================================================
# Runtime Stage
# =============================================================================
FROM python:3.14-slim-trixie

# Create non-root user for security
RUN groupadd --system --gid 999 nonroot \
    && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app

# Copy application from builder stage
COPY --from=builder --chown=nonroot:nonroot /app /app

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Make entrypoint script executable
RUN chmod +x /app/scripts/entrypoint.sh

# Switch to non-root user
USER nonroot

# Define default command
CMD ["/app/scripts/entrypoint.sh"]
