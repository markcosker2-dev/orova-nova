# Lightweight Python image for Render Free Tier
FROM python:3.11-slim

# Set environment variables for better performance
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# [SECURITY] Create a non-root user 'nova'
RUN useradd -m nova && chown -R nova:nova /app

# [P2] FIXED: Ensure PATH is set BEFORE pip install so scripts are recognized
ENV PATH="/home/nova/.local/bin:${PATH}"

USER nova

# Install dependencies (as nova user)
COPY --chown=nova:nova requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application code
COPY --chown=nova:nova . .

# Expose Gateway port
EXPOSE 18789

# Default command
CMD ["python", "app/main.py"]
