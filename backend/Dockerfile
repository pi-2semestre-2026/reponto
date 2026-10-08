FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY simulator ./simulator
COPY bootstrap_entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV ML_MODEL_PATH=/app/ml_data/model.txt \
    DATASET_DIR=/datasets \
    PYTHONUNBUFFERED=1

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]