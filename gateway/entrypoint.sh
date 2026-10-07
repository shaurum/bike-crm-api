#!/bin/sh
set -e

if [ -f /certs/cert.pem ] && [ -f /certs/key.pem ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8443}" \
    --ssl-certfile /certs/cert.pem --ssl-keyfile /certs/key.pem
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8443}"
