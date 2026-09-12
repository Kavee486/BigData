# Lightweight image for the pure-Python components: producers, batch source,
# alerts engine, and the FastAPI serving layer. Spark jobs run in a separate
# image (Dockerfile.spark) since they need a JVM + Spark distribution.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

CMD ["python", "--version"]
