FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd -m appuser
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY watcher.py /app/watcher.py
COPY templates /app/templates
COPY static /app/static


RUN mkdir -p /data && chown -R appuser:appuser /data /app
USER appuser

EXPOSE 1235
CMD ["python", "/app/app.py"]
