# Legacy Doc v2

API de documentação automática de código: multi-linguagem, orquestração
multi-agente sobre múltiplos fornecedores de LLM, processamento assíncrono em
fila e planos com níveis diferentes de análise.

## Como está organizado

```
apps/
  api/          FastAPI. Só HTTP: valida, autoriza, enfileira. Responde em ms.
  worker/       Processa jobs. É onde clone, LLM e exportação acontecem.
packages/
  core/         Config, modelos, fila, segurança, ingestão de repositório.
  providers/    Camada multi-provedor (OpenAI, Anthropic, Gemini) + roteador.
  parsing/      Tree-sitter: detecção de linguagem, símbolos, chunking por AST.
  agents/       Prompts e orquestrador multi-agente.
  exporters/    Markdown, PDF e JSON.
infra/          Dockerfile e docker-compose.
migrations/     Alembic.
docs/           Contrato da API e OpenAPI.
tests/          92 testes.
```

A separação **api / worker** é o ponto central da arquitetura. Trabalho pesado
nunca roda no processo que atende HTTP.

## Arquitetura

```
                      ┌─────────────┐
   VS Code ─────┐     │  FastAPI    │  valida, autoriza, enfileira
   Front web ───┼────>│  (apps/api) │──┐
   CI ──────────┘     └─────────────┘  │  POST /v1/jobs → 202 em ms
                                       ▼
                            ┌──────────────────────┐
                            │  Postgres            │  banco + fila
                            │  jobs / documents    │  (FOR UPDATE SKIP LOCKED)
                            └──────────────────────┘
                                       ▲
                      ┌────────────────┴────────────────┐
                      │  Worker × N (apps/worker)       │
                      │                                 │
                      │  clone → tree-sitter → chunks   │
                      │       ↓                         │
                      │  Reader → Writer ─┬─> Improver  │
                      │                   └─> Verifier  │
                      │       ↓                         │
                      │  Summarizer → documents         │
                      └─────────────────────────────────┘
                                       │
                      ┌────────────────┼────────────────┐
                      ▼                ▼                ▼
                   OpenAI          Anthropic         Gemini
```

Cada agente escolhe seu provedor pela política de roteamento, com cadeia de
fallback. O Writer roda uma vez por chunk e domina o custo, então vai para um
modelo barato; o Verifier roda uma vez por arquivo e precisa julgar fidelidade,
então vai para o modelo mais forte.

## Rodando localmente

Requer Docker (para o Postgres) e Python 3.11+.

```bash
cp .env.example .env
```

Preencha no `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT_SECRET_KEY
```

E ao menos uma chave de provedor (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY` ou
`GEMINI_API_KEY`).

Suba tudo:

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

A API fica em `http://127.0.0.1:8000`, docs interativas em `/docs`.

### Sem Docker

```bash
python -m venv .venv && .venv/Scripts/activate     # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m legacydoc_api      # terminal 1
python -m legacydoc_worker   # terminal 2
```

### Testes

```bash
pytest -q
ruff check .
```

Os testes rodam em SQLite e não gastam nenhum token: os provedores de LLM são
substituídos por dublês.

## Escalar

```bash
docker compose -f infra/docker-compose.yml up -d --scale worker=4
```

`SELECT ... FOR UPDATE SKIP LOCKED` garante que duas réplicas nunca peguem o
mesmo job, sem coordenação entre elas. Dentro de cada worker,
`WORKER_CONCURRENCY` define quantos jobs simultâneos, e `CHUNK_CONCURRENCY`
quantos chunks em paralelo por arquivo.

Se um worker morrer no meio de um job, o *lease* vence e outro worker reivindica
o trabalho — um deploy não perde a requisição do cliente.

## Escolhas que valem explicar

**Sem LangGraph.** O pipeline é linear com fan-out sobre chunks. O grafo
atrapalhava as três coisas que importam aqui: concorrência real
(`asyncio.gather`), roteamento de provedor por agente e contabilidade de custo
por chamada. O orquestrador em `packages/agents/pipeline.py` faz isso em ~350
linhas legíveis.

**A fila mora no Postgres.** Um broker separado (Redis + Celery) resolveria o
mesmo problema com mais uma peça para operar, monitorar e pagar. Com
`SKIP LOCKED` o banco entrega exclusão mútua, durabilidade e prioridade. Se o
volume crescer para centenas de jobs simultâneos, migrar vale a pena — hoje não.

**Chunking por AST, não por linha.** Cortar a cada N linhas parte funções ao
meio, e um Writer instruído a ignorar definições incompletas descarta a metade
em silêncio. Aqui o corte só acontece entre símbolos.

**Complexidade é medida, não perguntada.** Complexidade ciclomática e números de
linha vêm do parser. É determinístico, verificável e não custa token.

**Findings são gravados mesmo em plano que não os mostra.** Assim um upgrade
libera o que já foi analisado, sem reprocessar e sem cobrar de novo pelos tokens.

## Documentação

- [`docs/api-contract.md`](docs/api-contract.md) — guia para clientes, incluindo
  a extensão do VS Code.
- [`docs/openapi.json`](docs/openapi.json) — spec gerada do código, para codegen.
- [`docs/migracao-v1.md`](docs/migracao-v1.md) — o que mudou em relação à v1.

## Antes de abrir para usuários

- [ ] `JWT_SECRET_KEY` forte e único por ambiente.
- [ ] `ALLOWED_ORIGINS` com a URL real do front, sem `*` (a app rejeita `*`).
- [ ] HTTPS no domínio da API; porta 8000 apenas em loopback.
- [ ] **Conferir os preços de OpenAI e Gemini** em
      `packages/providers/legacydoc_providers/catalog.py` — estão marcados
      `verified=False` e alimentam o faturamento.
- [ ] Backup do volume do Postgres: ele guarda usuários, jobs e documentos.
- [ ] Rate limit por IP nas rotas de auth (ainda não implementado).
