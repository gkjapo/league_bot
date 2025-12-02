FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create entrypoint script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "Waiting for database..."\n\
while ! nc -z db 5432; do\n\
  sleep 0.1\n\
done\n\
echo "Database is ready!"\n\
\n\
echo "Running migrations..."\n\
python migrate.py up\n\
\n\
echo "Starting bot..."\n\
exec python bot.py\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Install netcat for database wait check
RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["/app/entrypoint.sh"]
