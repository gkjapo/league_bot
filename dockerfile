# Use Python 3.11 slim
FROM python:3.11-slim

# Set a working directory
WORKDIR /app

# Install system dependencies (required for python-dotenv, sqlite, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Run the bot
CMD ["python3", "bot.py"]
