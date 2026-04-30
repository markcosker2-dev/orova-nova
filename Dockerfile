# Use official Playwright image for Lead Hunter compatibility
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium && \
    rm -rf /root/.cache/pip

# Copy application code
COPY . .

# Expose Gateway and Health ports
# Note: Render only supports one exposed port per service, usually $PORT
EXPOSE 18789 10000

# Default command
CMD ["python", "app/main.py"]
