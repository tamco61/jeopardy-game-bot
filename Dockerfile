FROM python:3.12-slim

# Install uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Copy only necessary files for dependency installation to leverage cache
COPY pyproject.toml uv.lock ./

# Install dependencies without copying the whole project first
RUN /bin/uv sync --frozen --no-install-project

# Copy the rest of the application
COPY . .

# Final sync to install the project itself
RUN /bin/uv sync --frozen
