#!/usr/bin/env bash
# Troca a OPENAI_API_KEY do .env da v2 sem colar a chave no terminal.
# Uso: bash trocar-chave-openai.sh [arquivo-com-a-chave]   (padrao: /root/nova-chave.txt)
set -euo pipefail

ARQUIVO="${1:-/root/nova-chave.txt}"
PASTA="/opt/legacydoc-v2"
ENV_FILE="$PASTA/.env"

if [ ! -s "$ARQUIVO" ]; then
  echo "O arquivo $ARQUIVO nao existe ou esta vazio."
  exit 1
fi

CHAVE="$(sed 's/^\xEF\xBB\xBF//' "$ARQUIVO" | tr -d '\r\n\t "'"'"' ')"

if [[ ! "$CHAVE" =~ ^sk-[A-Za-z0-9_-]{20,}$ ]]; then
  echo "O conteudo do arquivo nao parece uma chave da OpenAI (deve comecar com sk-)."
  echo "Nada foi alterado."
  exit 1
fi

STATUS="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $CHAVE" https://api.openai.com/v1/models)"

if [ "$STATUS" != "200" ]; then
  echo "A OpenAI recusou esta chave (HTTP $STATUS). Nada foi alterado."
  exit 1
fi

BACKUP="$ENV_FILE.bak-$(date +%F-%H%M%S)"
cp -p "$ENV_FILE" "$BACKUP"
chmod 600 "$BACKUP"

awk -v chave="$CHAVE" '
  /^OPENAI_API_KEY=/ { print "OPENAI_API_KEY=" chave; trocou = 1; next }
  { print }
  END { if (!trocou) print "OPENAI_API_KEY=" chave }
' "$ENV_FILE" > "$ENV_FILE.tmp"
chmod 600 "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"

shred -u "$ARQUIVO" 2>/dev/null || rm -f "$ARQUIVO"

cd "$PASTA/infra"
docker compose --env-file ../.env up -d --force-recreate api worker >/dev/null 2>&1

echo "Chave valida (termina em ...${CHAVE: -4}) e aplicada."
echo "API e workers recriados. Backup do .env anterior: $BACKUP"
