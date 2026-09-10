#!/bin/sh
# Entrypoint dos containers de API e worker.
#
# O healthcheck do compose cobre a subida inicial, mas nao um restart do
# Postgres com os servicos ja no ar: nesse caso o container reinicia antes do
# banco voltar e morre em loop. Esperar aqui torna a ordem de subida
# irrelevante.
set -e

TIMEOUT="${DB_WAIT_TIMEOUT:-90}"

echo "[entrypoint] aguardando o banco (ate ${TIMEOUT}s)..."
python -m legacydoc_cli.db wait --timeout "${TIMEOUT}"

# Verificacao de schema apenas informativa: quem migra e o servico `migrate`.
# Falhar aqui deixaria a API fora do ar por um problema que o operador resolve
# com um comando, entao apenas avisamos alto.
if ! python -m legacydoc_cli.db check --tolerante > /dev/null 2>&1; then
    echo "[entrypoint] AVISO: 'db check' reprovou. Rode 'alembic upgrade head'."
fi

echo "[entrypoint] iniciando: $*"
exec "$@"
