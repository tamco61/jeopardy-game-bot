FROM python:3.12-slim

# Install uv system dependencies if needed (curl, etc.)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project

COPY . .
RUN uv sync
