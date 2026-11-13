FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_DATA_DIR=/data HOST=0.0.0.0 PORT=8765
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -m appuser && mkdir -p /data && chown appuser:appuser /data
COPY app.py ./
COPY static/ ./static/
EXPOSE 8765
CMD ["sh","-c","chown appuser:appuser /data && exec gosu appuser python app.py"]
