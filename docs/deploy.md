# Deploy da v2

Substitui o `DEPLOY.md` da v1. A diferença central: **v1 e v2 têm bancos
separados e rodam lado a lado**, então a troca é reversível.

## Como os dois convivem

```
                    ┌──────────────────────────────┐
   api.dominio ────►│  v2  (Postgres próprio)      │  novo
                    │  API + N workers + migrate   │
                    └──────────────────────────────┘

                    ┌──────────────────────────────┐
   old.dominio ────►│  v1  (SQLite legacydoc.db)   │  intacto, até desligar
                    └──────────────────────────────┘
```

A v1 continua com o `legacydoc.db` dela. A v2 sobe com Postgres novo. Os
usuários são **copiados** uma vez (§4), não compartilhados: a partir daí as
bases divergem, e é isso que torna o rollback possível — se a v2 tiver
problema, a v1 ainda está de pé com os dados dela.

> Não aponte a v2 para o SQLite da v1. Além de o schema ser incompatível, a
> fila depende de `SELECT ... FOR UPDATE SKIP LOCKED`, que o SQLite não tem —
> dois workers pegariam o mesmo job.

## 1. Preparar a VPS

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
sudo usermod -aG docker $USER   # saia e entre de novo para valer
```

## 2. Configurar

```bash
cd /opt/legacydoc
cp .env.example .env
```

Gere os segredos:

```bash
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
```

```bash
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"
```

Preencha no `.env`, mais `OPENAI_API_KEY` e `ALLOWED_ORIGINS` com a URL real do
front. A aplicação **recusa subir** sem `JWT_SECRET_KEY` e recusa `*` em
`ALLOWED_ORIGINS` — as duas falhas que a v1 tinha em produção.

Marque também `TRUST_PROXY_HEADERS=true`. Atrás do nginx toda requisição chega
com o endereço do próprio proxy, então sem isso o rate limit da aplicação
coloca a internet inteira no mesmo balde. Só ligue quando o nginx desta receita
estiver na frente: ligado sem proxy, qualquer chamador forja um
`X-Forwarded-For` e se dá um limite novo.

## 3. Subir

> A v2 escuta em **127.0.0.1:8001**, não 8000 — a v1 ocupa a 8000 e as duas
> precisam conviver. Ajuste com `API_PORT` no `.env` se necessário.

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

A ordem se resolve sozinha: `migrate` espera o Postgres e aplica o schema; API e
worker esperam o `migrate` terminar. O entrypoint também espera o banco a cada
restart, então reiniciar o Postgres não derruba os serviços em loop.

Confira:

```bash
docker compose -f infra/docker-compose.yml exec api python -m legacydoc_cli.db check
```

Deve terminar em `VEREDITO: banco pronto.` Se disser que faltam tabelas, o
`migrate` falhou — veja `docker compose logs migrate`.

## 4. Migrar os usuários da v1

Copie o `legacydoc.db` da v1 para a VPS e simule primeiro:

```bash
docker compose -f infra/docker-compose.yml run --rm -v /caminho/legacydoc.db:/tmp/v1.db api python -m legacydoc_cli.migrate_v1 --source /tmp/v1.db
```

Sem `--apply` nada é gravado. Confira a lista e então aplique:

```bash
docker compose -f infra/docker-compose.yml run --rm -v /caminho/legacydoc.db:/tmp/v1.db api python -m legacydoc_cli.migrate_v1 --source /tmp/v1.db --apply
```

**As senhas continuam valendo.** As duas versões usam
`pwdlib.PasswordHash.recommended()`, que gera argon2id no mesmo formato, e o
hash é copiado byte a byte — verificado, não presumido. Ninguém precisa
redefinir senha.

O comando é idempotente: rodar de novo pula quem já existe. O banco da v1 é
aberto **somente para leitura**, então pode rodar com a v1 no ar.

E-mail inválido ou hash fora do padrão argon2 é ignorado com aviso, em vez de
criar conta em que ninguém consegue entrar.

## 5. Contas para o time

O endpoint HTTP sempre cria no plano Free. Para liberar Pro:

```bash
docker compose -f infra/docker-compose.yml exec api python -m legacydoc_cli.db create-user dev@empresa.com --plan pro
```

A senha é pedida sem eco. Para promover quem já existe, acrescente `--update`.

## 6. Nginx e HTTPS

```bash
sudo cp infra/nginx-legacydoc.conf /etc/nginx/sites-available/legacydoc-v2
sudo ln -s /etc/nginx/sites-available/legacydoc-v2 /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

```bash
sudo certbot --nginx -d api.legacydoc.com.br -d app.legacydoc.com.br
```

Os `server_name` já apontam para `api.legacydoc.com.br` e
`app.legacydoc.com.br`. Note que API e front ficam em **servers
separados** de propósito: no servidor atual o fallback de SPA engole rotas da
API, e foi por isso que `/health` devolvia o `index.html` do front.

## 6.1 Atras da Cloudflare

Na StayCloud os registros do dominio saem com o proxy da Cloudflare ligado. Dois
efeitos, ambos verificados no primeiro deploy:

**O servidor nao enxerga o visitante, so a Cloudflare.** Sem tratamento, todo
mundo conta como o mesmo IP e o limite de requisicoes bloqueia todos juntos.
Instale a configuracao de IP real, que confia no cabecalho `CF-Connecting-IP`
somente quando o pedido vem de um IP oficial da Cloudflare:

```bash
sudo cp infra/nginx-cloudflare-realip.conf /etc/nginx/conf.d/cloudflare-realip.conf
sudo nginx -t && sudo systemctl reload nginx
```

A lista de IPs foi gerada de `cloudflare.com/ips-v4` e `ips-v6`. Ela muda
raramente; regenere se aparecer IP da Cloudflare no log de acesso.

**O HTTPS falha com erro 521 ate existir certificado no servidor.** A Cloudflare
fala HTTPS com a origem, entao a origem precisa escutar na 443. Emita o
certificado com o `certbot` da secao anterior.

Conferencia depois de instalar: um pedido pela Cloudflare deve aparecer no log
com o seu IP real, e um pedido direto ao servidor com `CF-Connecting-IP`
forjado deve aparecer com o IP de quem chamou, nunca com o forjado.

## 7. Escalar

```bash
docker compose -f infra/docker-compose.yml up -d --scale worker=4
```

`SKIP LOCKED` garante que duas réplicas nunca peguem o mesmo job. Dentro de cada
worker, `WORKER_CONCURRENCY` define jobs simultâneos e `CHUNK_CONCURRENCY`
chunks em paralelo por arquivo.

## 8. Backup

O volume do Postgres guarda usuários, jobs, documentos e findings. **É o único
estado que importa** — os artefatos são gerados sob demanda a partir dele.

```bash
docker compose -f infra/docker-compose.yml exec -T postgres pg_dump -U legacydoc legacydoc | gzip > backup-$(date +%F).sql.gz
```

Restaurar:

```bash
gunzip -c backup-2026-09-08.sql.gz | docker compose -f infra/docker-compose.yml exec -T postgres psql -U legacydoc legacydoc
```

Coloque no cron diário. Um backup que nunca foi restaurado não é backup —
teste a restauração numa base descartável antes de precisar.

## 9. Desligar a v1

Só depois de a v2 rodar alguns dias com uso real:

1. Migre os usuários de novo (quem se cadastrou na v1 nesse meio-tempo).
2. Redirecione o domínio antigo para o novo.
3. Guarde o `legacydoc.db` e a pasta `storage/` fora do servidor.
4. Aí sim, desligue.

## Checklist antes de abrir para usuários

- [ ] `JWT_SECRET_KEY` forte, diferente por ambiente
- [ ] `ALLOWED_ORIGINS` com a URL real, sem `*`
- [ ] HTTPS ativo; porta 8000 apenas em loopback; 5432 não exposta
- [ ] `db check` terminando em `banco pronto`
- [ ] Backup no cron **e uma restauração testada**
- [ ] Preços de OpenAI conferidos em `packages/providers/legacydoc_providers/catalog.py`
      (estão `verified=False` e alimentam o faturamento)
- [ ] `TRUST_PROXY_HEADERS=true` **e** o nginx na frente, nunca um sem o outro
