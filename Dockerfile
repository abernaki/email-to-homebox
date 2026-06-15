FROM python:3.11-slim

WORKDIR /app

# System libs required by EasyOCR (OpenCV) and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/ config/
COPY src/ src/

RUN mkdir -p data/logs data/failed data/processed

ENV PYTHONPATH=/app/src

CMD ["python", "src/app.py"]
