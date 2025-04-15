# Stage 1: Builder stage with build dependencies and Rust
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies and Rust
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    pkg-config \
    libssl-dev \
    gcc \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add Rust to PATH
ENV PATH="/root/.cargo/bin:${PATH}"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt \
    && pip install --no-cache-dir /wheels/*

# --- Stage 2: Final stage ---
FROM python:3.11-slim

WORKDIR /app

# Install only necessary runtime dependencies (if any)
# RUN apt-get update && apt-get install -y --no-install-recommends some-runtime-lib && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Command will be specified in docker-compose.yml
# Expose port if running directly (though docker-compose handles this)
# EXPOSE 8000
