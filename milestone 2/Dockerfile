FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_KIND=Freight APP_DATA_DIR=/var/lib/freightquote
WORKDIR /opt/freightquote
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./
RUN mkdir -p /var/lib/freightquote && python _vendor_bundle.py
EXPOSE 8000
# One app process: embedded SQLite connection and worker logic are not multiprocess-safe.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
