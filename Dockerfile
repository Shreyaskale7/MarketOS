FROM python:3.10-slim

# Install system dependencies for psycopg2 and building Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install gunicorn for production
RUN pip install --no-cache-dir gunicorn

# Copy application code
COPY . .

# Set environment variables
ENV PORT=5001
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5001

# Run the API with gunicorn
# --workers 1: Single worker to prevent bootstrap race conditions
# --threads 4: 4 threads for concurrent request handling
# --timeout 600: 10-minute timeout so the bootstrap data fetch doesn't get killed
CMD ["gunicorn", "marketos_api:app", "--bind", "0.0.0.0:5001", "--workers", "1", "--threads", "4", "--timeout", "600"]
