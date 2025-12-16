# rss-mailer

App web (Flask) en Docker para monitorizar un feed RSS/Torznab y enviar emails cuando hay coincidencias por keywords.

## Features
- Panel web
- Configuracion de FEED_URL, keywords, intervalo, SMTP
- Historial de coincidencias
- Logs
- Datos persistentes en volumen (`./data`)

## Docker Compose (recomendado)

```yaml
services:
  rss-mailer:
    image: psdani9xo/rss-mailer:latest
    container_name: rss-mailer
    restart: unless-stopped
    ports:
      - "1235:1235"
    environment:
      - DATA_DIR=/data
      - SECRET_KEY=rss_mailer_super_secret_key_2025
    volumes:
      - ./data:/data
