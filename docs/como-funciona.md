# Como o Legacy Doc funciona, fluxo a fluxo

Mapa para entender o código de ponta a ponta. Cada fluxo mostra **o caminho**, **o
arquivo e a função** onde acontece e **por que foi feito assim**. Não há números de
linha de propósito: eles envelhecem a cada edição, e o nome da função não.

Para o contrato de cada endpoint, veja [`api-contract.md`](api-contract.md). Para a
extensão do VS Code, [`guia-extensao.md`](guia-extensao.md). Para publicar,
[`deploy.md`](deploy.md). Para custos, [`custos.md`](custos.md).

---

## 0. A ideia em uma página

```
 Navegador / VS Code                 VPS
 ┌────────────────┐   HTTPS   ┌──────────┐      ┌──────────────┐      ┌───────────┐
 │ Front (React)  │──────────>│  nginx   │─────>│  API FastAPI │─────>│ Postgres  │
 │ Extensão       │<──────────│ (+CF)    │      │  (só HTTP)   │<─────│  (fila +  │
 └────────────────┘           └──────────┘      └──────────────┘      │  dados)   │
                                                                      └─────┬─────┘
                                                        FOR UPDATE SKIP LOCKED│
                                                                      ┌─────▼─────┐
                                                                      │  Worker   │──> OpenAI
                                                                      │ (2 réplicas)│   Anthropic
                                                                      └───────────┘   Gemini
```

Três decisões explicam quase tudo:

1. **A API só faz HTTP** (validar, autorizar, gravar, enfileirar) e responde em
   milissegundos. Todo trabalho pesado roda no **worker**. Na v1 uma única requisição
   segurava o servidor por minutos.
2. **A fila é o próprio Postgres.** Sem Redis nem broker: menos uma peça para operar
   e a fila herda as transações do banco.
3. **O parser é a fonte da verdade, o modelo de IA não.** Linhas, complexidade e
   existência de cada função vêm do tree-sitter. O que o modelo inventa e o parser
   não confirma é descartado.

### Onde fica cada coisa

| Pasta | Responsabilidade | Depende de |
| :--- | :--- | :--- |
| `apps/api` | Rotas HTTP, autenticação, cotas, rate limit | `core` |
| `apps/worker` | Laço que pega jobs da fila e os executa | `core`, `agents`, `providers`, `parsing` |
| `apps/cli` | Migração, criação de usuário, `set-admin`, smoke test | `core` |
| `packages/core` | Modelos, planos, fila, segurança, zip, clone, configuração | nada interno |
| `packages/parsing` | tree-sitter: símbolos, blocos, índice entre arquivos | `core` |
| `packages/agents` | Pipeline dos agentes, prompts, seleção de contexto | `core`, `parsing`, `providers` |
| `packages/providers` | OpenAI, Anthropic, Gemini atrás da mesma interface, roteador | `core` |
| `packages/exporters` | Markdown, PDF, JSON | `core` |
| `tests` | 255 testes | tudo |

Regra de dependência: **`core` não importa ninguém**, e nenhum módulo de domínio
importa FastAPI (`packages/core/legacydoc_core/errors.py`). Por isso os erros de
domínio são traduzidos para HTTP num lugar só (fluxo 1.3).

### Como subir

| O quê | Comando |
| :--- | :--- |
| Migrar o banco | `python -m legacydoc_cli.db migrate` |
| API | `uvicorn legacydoc_api.main:get_app --factory --port 8001` |
| Worker | `python -m legacydoc_worker` |
| Front | `npm run dev` em `Front/test/LegacyDocFront` |
| Promover admin | `python -m legacydoc_cli.db set-admin <email>` |

**Sem o worker rodando, os jobs ficam eternamente em `queued`.** É a causa mais comum
de "a análise não funciona" em desenvolvimento.

---

## 1. Entrada de uma requisição

### 1.1 Ordem das camadas (`apps/api/legacydoc_api/main.py`)

```
requisição ─> CORS ─> rate limit ─> roteamento ─> dependências (auth/cotas) ─> rota
```

- `create_app` (`main.py`) monta tudo; `lifespan` abre o pool de conexões
  e o fecha ao desligar.
- O rate limit é registrado **antes** do CORS porque o Starlette executa o
  último registrado primeiro. Assim o CORS fica por fora e uma resposta 429 ainda
  leva os cabeçalhos que o navegador exige para mostrá-la.
- `/health` não passa por autenticação nem por rate limit.

### 1.2 Rate limit (`apps/api/legacydoc_api/ratelimit.py`, `packages/core/legacydoc_core/ratelimit.py`)

Janela deslizante **por IP**, em memória do processo. Três faixas (`ratelimit.py`):

| Faixa | Limite | Rotas |
| :--- | :--- | :--- |
| `auth` | 20 / 5 min | login, cadastro, redefinição de senha |
| `jobs` | 30 / 5 min | `POST /v1/jobs` e `/v1/jobs/upload` |
| `read` | 240 / min | todo o resto, incluindo o polling |

Por que 20 em `auth` e não menos: o bloqueio da conta (fluxo 2.1) já barra o palpite
de senha, e apertar mais o IP prejudica turma ou escritório que sai por um único IP.

`_client_address` só confia em `X-Forwarded-For` quando
`TRUST_PROXY_HEADERS=true`, e usa a **última** entrada (a que o proxy anexou). Sem
essa regra qualquer cliente forjaria um IP novo a cada pedido. Atrás da Cloudflare
isso depende do `infra/nginx-cloudflare-realip.conf`, que só aceita
`CF-Connecting-IP` vindo dos IPs da própria Cloudflare.

### 1.3 Erros num formato único (`main.py`)

Toda falha responde `{"error", "message", "details"}`. `LegacyDocError` mapeia para
o `http_status` da própria exceção (`errors.py`): 401, 402, 404, 409, 422, 429, 502.
Erro inesperado vira 500 sem vazar detalhes em produção (`main.py`).

---

## 2. Identidade e credenciais

### 2.1 Cadastro e login (`routers/auth.py`)

**Cadastro**: normaliza o e-mail, valida a força da senha, grava com
**argon2id** (`security.py`), plano `free`. E-mail repetido dá 409.

**Login**, em ordem:

1. E-mail desconhecido → "Credenciais inválidas." Mesma resposta de senha errada,
   para não virar um detector de contas existentes.
2. Conta bloqueada → recusa **antes** de verificar a senha. Se verificasse depois, o
   atacante continuaria testando candidatas.
3. Senha errada → soma tentativa; da 5ª em diante bloqueia com espera crescente:
   15 min, 30, 60… até 24 h (`security.py`). Não bloqueia para sempre, senão
   o atacante negaria o acesso à vítima.
4. **O `commit` vem antes do `raise`** (`auth.py`). A sessão faz rollback
   quando há exceção; sem o commit explícito o contador nunca persistiria e o
   bloqueio jamais dispararia. Já foi um bug real.
5. Sucesso → zera o contador e devolve um JWT de 24 h (`_token_for`, ).

### 2.2 Duas credenciais no mesmo cabeçalho (`deps.py`)

`Authorization: Bearer <x>`. `get_principal` decide pelo prefixo:

| Prefixo | Tipo | Como valida | Uso |
| :--- | :--- | :--- | :--- |
| `ldk_` | Chave de API | Busca pelo prefixo indexado, confirma o SHA-256 em tempo constante | Extensão, CI |
| outro | JWT | Decodifica e assina | Front web |

Chave de API usa SHA-256 e não argon2 (`security.py`): ela tem 256 bits de
entropia, então não há senha humana para forçar, e argon2 somaria ~100 ms a cada
chamada da extensão.

O resultado é um `Principal` (`deps.py`): usuário + plano + se veio por chave.
Conta desativada é recusada aqui, para todas as rotas de uma vez.

### 2.3 Chaves de API (`auth.py`)

`POST /v1/auth/api-keys` gera `ldk_` + 32 bytes aleatórios, **grava só o hash** e
devolve o valor uma única vez. `DELETE` revoga (marca `revoked_at`). A `last_used_at`
é atualizada a cada uso (`deps.py`).

### 2.4 Painel administrativo (`routers/admin.py`, `deps.py`)

`require_admin` **recusa chave de API** e responde **404, não 403**:

- Chave é credencial longa, feita para ficar em máquina de CI e editor. Se abrisse o
  painel, um vazamento de chave entregaria a administração junto.
- 403 confirmaria a quem sonda que existe um painel ali.

Mudar plano ou status exige **motivo obrigatório** e grava um `AdminAction` com o
e-mail de quem agiu e da conta afetada **copiados** (a linha sobrevive mesmo se a
conta for apagada; FK `SET NULL`). É o que responde, meses depois, "por que essa
conta está no Pro?".

O mesmo padrão "404 em vez de 403" vale para dono de recurso: projeto, job e
documento de outra conta respondem 404 (`deps.py`, `jobs.py`).

---

## 3. Planos, profundidade e custo

### 3.1 O plano é um teto (`packages/core/legacydoc_core/plans.py`)

| | Free | Pro | Team |
| :--- | ---: | ---: | ---: |
| Jobs por mês | 20 | 500 | 5.000 |
| Teto de gasto em IA por mês | US$ 0,50 | US$ 25 | US$ 200 |
| Arquivos por job | 3 | 50 | 500 |
| Jobs simultâneos | 1 | 4 | 16 |
| Profundidade máxima | basic | pro | pro |
| Ver melhorias | não | sim | sim |
| Contexto de projeto | não | sim | sim |
| Webhook | não | sim | sim |
| Prioridade na fila | 100 | 50 | 10 (menor vai primeiro) |

Os planos são constantes no código (`_FREE`, `_PRO`, `_TEAM`); o plano
de cada conta é só o texto `plan_tier` na tabela `users`. Mudar de plano é trocar
esse texto, e o **painel admin** faz exatamente isso. Ainda **não há pagamento**.

**O limite é em dólares, não em jobs** (`plans.py`): um arquivo e quinhentos
diferem em ordens de grandeza, e a conta a pagar é em dólar.

### 3.2 Profundidade escolhida por job (`GenerationDepth`, `plans.py`)

| `depth` | Agentes que rodam | Custo medido por arquivo |
| :--- | :--- | ---: |
| `basic` | leitor, escritor, resumo | ~US$ 0,002 |
| `standard` | + melhorias (improver) | ~US$ 0,009 |
| `pro` | + auditoria (verifier) e reescrita | ~US$ 0,023 |

O plano diz até onde a pessoa **pode** ir; o `depth` diz até onde ela **escolheu**
ir. `resolve_depth` **limita em vez de recusar**: pedir `pro` no Free roda
`basic` e a resposta informa o que foi aplicado. Assim um cliente que sempre manda
`pro` funciona em qualquer plano.

O worker **chama `resolve_depth` de novo** (`processor.py`) em vez de confiar no
que foi gravado na criação: o job pode ficar na fila enquanto a conta muda de plano,
e vale o plano do momento da execução. Há teste para isso
(`test_a_downgrade_while_queued_is_honoured`).

### 3.3 Onde os limites são checados (`deps.py`)

Antes de enfileirar, nesta ordem:

1. `enforce_cost_budget`: teto **global** do mês (`GLOBAL_MONTHLY_BUDGET_USD`,
   padrão US$ 50) e teto do **usuário**. O global é a última defesa do cartão: várias
   contas cada uma dentro do seu limite ainda podem somar mais do que se pode pagar.
2. `enforce_job_quota`: cota mensal de jobs e concorrência.

O gasto é somado de `usage_records`, que o worker preenche a cada chamada de IA.
É um **freio, não uma cerca exata**: um job já aceito termina e pode ultrapassar o
teto pelo custo dele.

### 3.4 Melhorias sempre gravadas, exibição por plano (`documents.py`)

O improver roda conforme a **profundidade**; ver o resultado depende do **plano**
(`Feature.IMPROVEMENT_FINDINGS`). São permissões separadas de propósito: o que já
está gravado pode ser revelado por um upgrade sem reprocessar nem gastar token.

`findings_locked = bool(document.findings) and not shows_findings` só é `true` quando
**existem** melhorias gravadas e o plano atual não as mostra. **Uma conta Free nunca
gera melhorias** (a profundidade dela é limitada a `basic`), então para ela o campo é
`false` e a lista vem vazia. O `true` aparece em quem **caiu** de um plano pago: os
documentos gerados quando era Pro continuam lá, ocultos, e voltam com um novo upgrade.
Ver a limitação 13 sobre o que isso significa para a vitrine do plano Pro.

---

## 4. Criar um job (três entradas)

Todas terminam em `enqueue` (`queue.py`) e respondem **202** com o job em `queued`.

### 4.1 Link de repositório: `POST /v1/jobs` (`routers/jobs.py`)

1. `enforce_cost_budget` e `enforce_job_quota`.
2. Projeto informado precisa ser do chamador (`get_owned_project`).
3. Webhook exige plano com `WEBHOOKS`.
4. `resolve_depth`.
5. `validate_repo_url` (`repository.py`): **só HTTPS**, só `github.com`,
   `gitlab.com`, `bitbucket.org`, sem `@` na URL. Isso barra `file://`, `git://`, SSH
   e qualquer host interno: uma URL controlada pelo cliente não pode ler o disco nem
   alcançar a rede interna do servidor.
6. Pedir mais `paths` que o plano permite dá 422.
7. Grava o job com os parâmetros. **Nada de clone aqui.**

### 4.2 Trecho de código: `POST /v1/jobs` com `job_type=document_snippet`

É o caminho da extensão para o arquivo aberto. O `path` só serve para **detectar a
linguagem** (`detect_language`), por isso extensão desconhecida dá 422. Conteúdo até
1 MB (`schemas.py`, `SnippetJobRequest`).

### 4.3 Envio do computador: `POST /v1/jobs/upload` (`jobs.py`)

Multipart com `file`, `project_id`, `output_language`, `depth`.

1. Mesmas checagens de cota e custo.
2. Nome precisa terminar em `.zip`.
3. **Grava em disco lendo em blocos de 1 MB**, contando os bytes. O
   `Content-Length` vem do cliente e não é limite; ao cruzar 50 MB aborta na hora.
4. Vazio → 422. **A assinatura decide, não o `Content-Type`**: `looks_like_zip`
   (`archive.py`) confere os bytes `PK`.
5. Se qualquer passo falha, o arquivo parcial é apagado.
6. O job guarda **só o caminho** do zip. **A extração acontece no worker**, porque
   fazê-la aqui devolveria à API o trabalho pesado que a v2 existe para tirar dela.

O nginx limita o corpo a 55 MB (`infra/nginx-legacydoc.conf`), acima dos 50 MB da
aplicação de propósito: o cliente recebe o 422 legível da API, e não um 413 seco.

---

## 5. A fila e o worker

### 5.1 Pegar um job (`queue.py`, SQL em )

```sql
UPDATE jobs SET status='running', locked_by=..., lease_expires_at=..., attempts=attempts+1
 WHERE id = (SELECT id FROM jobs WHERE status='queued' AND scheduled_at <= now()
             ORDER BY priority ASC, scheduled_at ASC
             FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING id
```

`SKIP LOCKED` faz um worker pular o job que outro já está pegando, então N workers
rodam sem coordenação e sem pegar o mesmo job. Ordena por `priority` (planos pagos
primeiro) e depois por `scheduled_at` (FIFO dentro da faixa). O ramo SQLite existe só para os testes rodarem sem container.

### 5.2 O laço (`apps/worker/legacydoc_worker/runner.py`)

- `run` cria `WORKER_CONCURRENCY` **slots** (padrão 4) mais um **reaper**.
- `_slot`: pega job → executa → repete. Fila vazia: espera
  `WORKER_POLL_INTERVAL_SECONDS` (2 s), mas acorda na hora se pedirem para desligar.
- `_execute` separa os erros em dois tipos, e isso é central:

| Erro | Tratamento |
| :--- | :--- |
| `LegacyDocError` (extensão inválida, repositório inexistente, zip ruim) | **Falha definitiva**, sem nova tentativa: repetir não melhora |
| Qualquer outra exceção (rede, banco, provedor caiu) | **Reenfileira** com espera de 30 s dobrando até 15 min, até 3 tentativas (`queue.py`) |
| Concluiu sem gerar nenhum documento | Falha `no_documents` |

### 5.3 Lease e heartbeat: como um worker que morre não perde o job

Pegar um job dá um **lease** de 900 s (`JOB_LEASE_SECONDS`). A cada arquivo o worker
chama `heartbeat` (`queue.py`), que renova o lease **e** publica progresso.
Se o processo morre, o lease vence; o **reaper** (`runner.py`, a cada 60 s)
reenfileira o job (`queue.py`), ou o marca `failed` se as tentativas acabaram.

`heartbeat` devolve `False` quando o job já não pertence a este worker.
O processador então **para** (`processor.py`): continuar duplicaria documentos
e cobraria token duas vezes.

Desligamento gracioso (`runner.py`): SIGTERM/SIGINT param de pegar jobs e deixam o
atual terminar. Sem isso, um deploy mataria jobs no meio e gastaria token de novo.

### 5.4 Retomada depois de falha

O worker **grava cada arquivo assim que o termina** (`processor.py`), para uma falha
tardia não jogar fora o que já foi pago. Quando o job volta à fila, a nova tentativa
consulta os documentos que o job já tem (`_documented_paths`, `processor.py`) e
**pula esses arquivos**, sem chamar a IA. Antes disso, a segunda tentativa batia na
restrição única `(job_id, path)` e o job terminava como `failed` com metade do
trabalho gravado. Teste: `test_a_retried_job_resumes_instead_of_documenting_again`.

---

## 6. Executar um job (`apps/worker/legacydoc_worker/processor.py`)

`process` monta o roteador de provedores, resolve a profundidade e o pipeline,
e despacha por tipo:

```
process ──┬─ document_snippet ──> 1 arquivo em memória ─────────────┐
          ├─ document_archive ──> extrai o zip ──> varre ───────────┼─> _document_files
          └─ document_repository ─> clona ────────> varre ──────────┘
```

### 6.1 Repositório (`_document_repository`, )

1. `clone` (`repository.py`): `--depth=1 --single-branch --no-tags`, com timeout.
2. `scan`: percorre podando pastas de dependência e ocultas, descartando
   extensões sem gramática, arquivos minificados, arquivos acima de 512 KB, binários e
   vazios; respeita limites de arquivos e bytes.
3. Corta em `plan.max_files_per_job` **mesmo sem `paths`** e avisa quantos ficaram fora.
4. `finally: cleanup_directory` **sempre**: a v1 deixava um clone órfão de 101 MB.

### 6.2 Zip (`_document_archive`, , `safe_extract` em `archive.py`)

Cada entrada passa por, em ordem: link simbólico → caminho perigoso (absoluto, letra
de drive, `..`, byte nulo) → tamanho → **razão de compressão** (> 500x) → extensão
suportada → destino dentro da pasta. Tamanhos são conferidos **byte a byte durante a
escrita**, então uma bomba calibrada para 499x ainda é cortada pelos tetos absolutos.
Filtrar por extensão **durante** a extração impede que um zip cheio de imagens toque
o disco.

Entrada recusada por segurança **não derruba o job**: vira aviso no resultado.
`finally` apaga a pasta extraída **e o zip enviado**: o zip só serve a
este job, e guardá-lo acumularia disco e deixaria código de cliente parado no servidor.

### 6.3 Todos os arquivos (`_document_files`, )

1. Carrega o **contexto do projeto** (glossário, regras), se houver.
2. Monta o **índice de símbolos** de todos os arquivos em thread (`_build_index`,
   ): custa CPU e zero token, e deixa o escritor entender chamadas para outros
   arquivos em vez de chutar.
3. Para cada arquivo: `heartbeat` (progresso 15%→95%) → `pipeline.run` → alimenta o
   índice com os resumos gerados (arquivos seguintes enxergam o que já foi
   documentado) → `_persist` → `commit`.
4. Falha de **um** arquivo (`LegacyDocError`) vira aviso e o job segue.

### 6.4 Custos registrados

`_make_usage_sink` grava um `UsageRecord` por chamada de IA (agente,
provedor, modelo, tokens, US$, latência, sucesso). É a base do teto de gasto, do painel
e de `docs/custos.md`.

---

## 7. O pipeline de agentes (`packages/agents/legacydoc_agents/pipeline.py`)

`DocumentationPipeline.run`, **por arquivo**:

```
parse (tree-sitter) ─> chunks ─> LEITOR ─> ESCRITOR ║ MELHORIAS ─> AUDITOR ⇄ reescrita ─> RESUMO
                                  (todos)  (todos)   (standard+)     (pro)              (todos)
                                                     paralelos por bloco
```

1. **Parse** (`symbols.py`): símbolos, linhas, complexidade ciclomática e classe-mãe
   vêm da árvore sintática. Sem gramática, divide por linhas e avisa.
2. **Blocos** (`chunking.py`): agrupa símbolos até ~6.000 tokens; um símbolo maior
   que o orçamento é fatiado.
3. **Leitor**: diagnóstico rápido do que falta de contexto. Roda em todos os
   níveis e a falha dele não derruba nada (é consultivo).
4. **Escritor + Melhorias** (`_process_chunks`, ): por bloco, em paralelo, com
   semáforo (`CHUNK_CONCURRENCY`, padrão 6). O bloco que falha vira aviso, **não
   afunda o arquivo**.
5. **Ancoragem** (`_enrich`, `_anchor_findings`): **a defesa contra
   alucinação.** O símbolo é aceito só se o parser o viu; linha, complexidade e classe
   vêm do parser. O nome citado pelo modelo é normalizado (`Classe.metodo`).
   Símbolo ou melhoria sobre algo que **não existe no código é descartado** e listado
   nos avisos. Melhoria sobre o arquivo todo é mantida, mas **sem linha**, porque nada
   a confirma. Motivo: uma melhoria que manda o leitor para a linha errada é pior que
   nenhuma, porque ele confia nela e depois desconfia do resto.
6. **Auditor** (`_review_loop`, , só `pro`): compara a documentação com o código.
   O código vai como **prefixo cacheável** (`cacheable_prefix`), pago com desconto a
   partir da 2ª rodada. Reprovou? `_rewrite_rejected` reescreve **só os
   símbolos reprovados**, e não o arquivo inteiro, para não gastar token nem degradar
   o que estava certo. Uma rodada de reescrita (`max_review_rounds=1`); o que
   sobreviver vira aviso.
7. **Resumo** (`_run_summarizer`, ).

### 7.1 Roteamento por agente (`packages/providers/legacydoc_providers/router.py`)

`DEFAULT_ROUTES`: barato no volume, forte na auditoria.

| Agente | 1ª opção | Reserva |
| :--- | :--- | :--- |
| Leitor, Resumo | gpt-4o-mini | gemini-2.0-flash |
| Escritor | gpt-4o-mini | gemini, claude-haiku |
| Melhorias | claude-sonnet-5 | gpt-4o |
| Auditor | claude-opus-5 | gpt-4o |

`resolve_chain` **filtra pelos provedores que têm chave**. Hoje só há
`OPENAI_API_KEY`, então melhorias e auditoria rodam em `gpt-4o`. `complete`
tenta a cadeia em ordem, e cada falha (inclusive rate limit) passa para o próximo;
só quando todos falham levanta `ProviderError` (502).

---

## 8. Ler o resultado

`GET /v1/jobs/{id}` (`jobs.py`) devolve status, `progress_percent`,
`progress_message` (mensagem real, tipo "Documentando src/a.py (3/12)"), `depth` e
`source`. `_source_of` expõe só a origem legível e **não** os parâmetros
inteiros: eles trazem o conteúdo enviado e o caminho do arquivo no disco do servidor.

`GET /v1/documents?job_id=` lista; `GET /v1/documents/{id}` traz símbolos e melhorias
(fluxo 3.4); `/export?format=markdown|pdf|json` gera o artefato **sob demanda**, com
autenticação e `Cache-Control: private, no-store`. Não existe URL pública de arquivo:
na v1 o PDF era acessível por quem adivinhasse o nome.

---

## 9. O front (`Front/test/LegacyDocFront`)

### 9.1 Do clique ao resultado

```
Home ──(link)──> localStorage: repoUrl, repoBranch, repoDepth ──> /loading
     └─(pasta/zip)─> createUploadJob (XHR, progresso) ──> localStorage: pendingJobId ─> /loading

Loading ── runRepositoryJob ou followJob(pendingJobId) ──> polling GET /v1/jobs/{id}
        └─ ao concluir: documentToResult ──> localStorage: legacyDocResult ──> /resultado

Resultado ── lê legacyDocResult; abre cada arquivo com getDocument; exporta
```

- `services/api.ts`: cliente da v2. `followJob` acompanha um job existente;
  `runRepositoryJob` cria e acompanha; `createUploadJob` envia o zip
  por XHR porque `fetch` não informa progresso de **envio**; `documentToResult` converte o formato da API no que as telas usam.
- `services/upload.ts`: prepara a pasta. **Filtra no navegador com as regras do
  servidor** (pastas de dependência, extensões de `GET /v1/meta/languages`, arquivos
  grandes ou gerados) e compacta com `fflate`. Uma pasta de projeto costuma ter
  `node_modules` maior que o código, e mandar isso para o servidor descartar gastaria
  banda e o limite de 50 MB à toa.
- **Por que `pendingJobId`:** o upload já criou o job na Home; a tela de carregamento
  só precisa acompanhá-lo. Sem esse repasse ela criaria um segundo job.

### 9.2 Histórico por conta

`clearLocalSession` (`api.ts`) apaga resultado, histórico e chaves de estado ao
entrar e ao sair. Já houve vazamento de histórico entre contas porque tudo ficava em
`localStorage` sem dono; hoje o histórico vem do servidor (`listJobs`, ),
escopado à conta.

### 9.3 Visual por plano

Azul é o padrão. Roxo aparece **só** no modo `pro` (`data-modo="pro"`), que precisa
**redeclarar os tokens semânticos**: uma variável CSS resolve o `var()` no elemento
onde é declarada, então trocar só a paleta base não muda `--primary` nos filhos.
`Resultado` mostra as melhorias reais e, quando `findings_locked`, o cartão com
cadeado (`Resultado.tsx`, ).

---

## 10. Garantias de segurança (o que protege de quê)

| Ameaça | Defesa | Onde |
| :--- | :--- | :--- |
| Palpite de senha | argon2id + bloqueio crescente + rate limit | `security.py`; `ratelimit.py` |
| Descobrir quais e-mails existem | Mesma resposta para e-mail e senha errados | `auth.py` |
| Ver dado de outra conta | 404 para recurso alheio, filtro por dono em toda consulta | `deps.py`, `jobs.py`, `documents.py` |
| Chave de API vazada abrir o painel | Painel só aceita sessão | `deps.py` |
| Ler o disco ou a rede pelo clone | HTTPS + lista de hosts + sem credencial na URL | `repository.py` |
| Zip slip, bomba, symlink | Validação por entrada, tetos por byte, razão de compressão | `archive.py` |
| Upload maior que o limite | Contagem em blocos, aborto na hora, nginx acima | `jobs.py` |
| Estourar a conta da IA | Teto por usuário + teto global | `deps.py` |
| Inundação de requisições | Limite na app + nginx; IP real atrás da Cloudflare | `ratelimit.py`, `infra/` |
| Documentação inventada | Parser é a verdade; o que ele não vê é descartado | `pipeline.py` |
| Chave de IA no código | Só variável de ambiente, `SecretStr` | `settings.py` |

---

## 11. Limitações conhecidas

Listadas para ninguém descobrir sozinho. Nenhuma impede o uso hoje; todas valem
decisão antes de abrir para o público.

| # | Limitação | Impacto | Sugestão |
| :-: | :--- | :--- | :--- |
| 1 | **Cancelar só funciona em job `queued`.** `cancel_job` (`queue.py`) exige `queued`; o comentário fala em "perceber no heartbeat", mas o heartbeat nunca cancela. | Job em execução não para e gasta até o fim | Checar `cancelled` no `heartbeat` e abortar, ou corrigir o texto |
| 2 | **Nova tentativa de job de upload falha.** O zip é apagado no `finally` do 1º ciclo (`processor.py`), então a 2ª tentativa acusa "arquivo não está mais disponível". | Erro transitório num upload vira falha definitiva com mensagem clara | Apagar o zip só quando o job termina (sucesso ou falha final) |
| 3 | **Cotas checadas antes de enfileirar, sem trava.** Duas requisições simultâneas passam pela contagem. | Pode passar um job da concorrência | Contar dentro da mesma transação com `SELECT ... FOR UPDATE` na linha do usuário |
| 4 | **Rate limit em memória do processo.** Cada réplica da API tem a sua contagem. | Com várias réplicas o limite efetivo multiplica | Hoje há 1 réplica. Com mais, mover para Redis ou para o nginx |
| 5 | **Webhook sem validação de destino** (`runner.py`). | SSRF: um usuário Pro/Team aponta para a rede interna | Aplicar a mesma lista/validação do clone, resolver DNS e bloquear IP privado |
| 6 | **Sem verificação de e-mail e sem SMTP em produção.** | Cadastro com e-mail de terceiro; redefinição de senha não chega | Configurar SMTP e confirmar e-mail antes de liberar jobs |
| 7 | **`/docs` aberto em produção.** | Expõe o mapa da API | Desligar ou proteger fora de desenvolvimento |
| 8 | **Sem tela de chaves de API no front.** | Só se gera a chave por API/extensão | Tela "Chaves" em Configurações |
| 9 | **O leitor roda também no `basic`.** | Uma chamada barata a mais por arquivo, fora da tabela de custo | Documentar ou pular no `basic` |
| 10 | **Sem pagamento.** Plano é troca manual pelo painel. | Não vende sozinho | Gateway + webhook que chama a mesma troca de plano |
| 11 | **Sem reaproveitamento por `content_sha256`.** O hash está gravado, mas não é usado para pular arquivos inalterados entre jobs. | Reanalisar o mesmo arquivo cobra de novo | Reusar o documento do último job com o mesmo hash |
| 12 | **`Idempotency-Key` inexistente.** | Retry de POST com timeout pode duplicar job | Aceitar o cabeçalho e devolver o job já criado |
| 13 | **O Free não vê "N melhorias travadas".** Como o improver não roda no Free, `findings_locked` é `false` e o cartão de cadeado do `Resultado` só aparece para quem caiu de plano. | A vitrine de upgrade do relatório não funciona para o público que mais interessa | Decisão de produto: rodar o improver uma vez por job no Free só para contar (custa ~US$ 0,007 por arquivo) ou mostrar uma amostra fixa. Hoje a vitrine está na Home (seletor com cadeado) |

---

## 12. Onde estão os testes

255 testes em `tests/` (SQLite em memória; `test_queue_postgres.py` roda contra um
Postgres real quando disponível).

| Arquivo | Garante |
| :--- | :--- |
| `test_api.py` | Cadastro, login, bloqueio, isolamento entre contas, cotas |
| `test_admin.py` | Painel: só admin, motivo obrigatório, auditoria, chave de API recusada |
| `test_queue.py`, `test_queue_postgres.py` | Prioridade, lease, retry com espera, reaper, concorrência real |
| `test_worker_integration.py` | Da fila ao documento, sem gastar token (roteador substituído) |
| `test_pipeline.py` | Ancoragem, descarte de símbolo inventado, auditoria e reescrita |
| `test_depth.py` | Profundidade, teto do plano, rebaixamento na fila |
| `test_archive.py` | Zip slip, bomba, symlink, limites |
| `test_repository.py` | URL permitida, varredura, limites |
| `test_ratelimit.py` | Janela deslizante, cabeçalhos, IP por proxy |
| `test_parsing.py`, `test_legacy_languages.py`, `test_symbol_index.py` | 36 linguagens, símbolos, índice |
| `test_providers.py` | Cadeia de reserva, custo, cache |

Rodar tudo: `python -m pytest`. Qualidade: `ruff check apps tests` e `ruff format --check`.
