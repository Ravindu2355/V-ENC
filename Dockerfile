# Use lightweight Python
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system deps (ffmpeg + build tools if needed)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (better caching)
COPY requirements.txt .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Run both Flask + Bot properly
CMD ["bash", "-c", "gunicorn --bind 0.0.0.0:8000 app:app --workers 1 --threads 2 & python3 bot.py"]
