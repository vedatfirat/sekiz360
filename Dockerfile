FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_DATA_DIR=/data HOST=0.0.0.0
WORKDIR /app
COPY source-part-*.b64 /tmp/source/
RUN pip install --no-cache-dir brotli && \
    cat /tmp/source/source-part-*.b64 | base64 -d > /tmp/source.tar.br && \
    python -c "import brotli,tarfile,io; t=tarfile.open(fileobj=io.BytesIO(brotli.decompress(open('/tmp/source.tar.br','rb').read()))); t.extractall('/app',filter='data')" && \
    pip install --no-cache-dir -r requirements.txt && \
    useradd -r -m appuser && mkdir -p /data && chown appuser:appuser /data && \
    rm -rf /tmp/source /tmp/source.tar.br
USER appuser
EXPOSE 8765
CMD ["python","app.py"]
