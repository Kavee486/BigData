# Lightweight image for the pure-Python components: streaming producer,
# daily batch source, alerts engine and the FastAPI serving layer.
FROM python:3.11-slim-bookworm

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

CMD ["python", "--version"]
