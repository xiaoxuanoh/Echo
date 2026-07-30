FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ocr.txt ./

ARG INSTALL_OCR=false
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_OCR" = "true" ]; then pip install --no-cache-dir -r requirements-ocr.txt; fi

COPY app ./app

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
