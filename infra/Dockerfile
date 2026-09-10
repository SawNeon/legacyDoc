# Python 3.12: versao com wheels garantidos para asyncpg e tree-sitter.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# git e necessario em runtime: o worker clona repositorios.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Camada de dependencias separada do codigo, para aproveitar o cache do Docker
# quando so o codigo muda.
COPY pyproject.toml ./
COPY packages ./packages
COPY apps ./apps
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --upgrade pip && pip install .

COPY infra/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

RUN useradd --create-home --uid 10001 legacydoc \
 && mkdir -p /var/legacydoc/tmp /var/legacydoc/storage \
 && chown -R legacydoc:legacydoc /var/legacydoc /app

USER legacydoc

EXPOSE 8000

# O entrypoint espera o banco antes de entregar o controle ao CMD.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["uvicorn", "legacydoc_api.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
