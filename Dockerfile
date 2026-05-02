# Lightweight Python image for Render Free Tier
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Scrapling
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Gateway port
EXPOSE 18789

# Default command
CMD ["python", "app/main.py"]
