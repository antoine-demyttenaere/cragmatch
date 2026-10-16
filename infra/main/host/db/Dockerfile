# The cloud database image. It sits next to the repo's postgres.Dockerfile because the host is
# Graviton (arm64) and postgis/postgis:17-3.5 has only an amd64 image (checked on Docker Hub,
# 2026-10-14). The PGDG packages below exist for both architectures. The TLS settings live in
# the image so the host and infra/main/host/check-db-image.sh run it the same way.
FROM postgres:17-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 postgresql-17-pgvector \
    && rm -rf /var/lib/apt/lists/*

COPY initdb/ /docker-entrypoint-initdb.d/

CMD ["postgres", "-c", "ssl=on", "-c", "ssl_cert_file=/tls/server.crt", "-c", "ssl_key_file=/tls/server.key"]
