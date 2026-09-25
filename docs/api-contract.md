# Contrato da API — guia para a extensão do VS Code

Documento de referência para quem está construindo o cliente. O `docs/openapi.json`
é gerado a partir do código e serve para codegen (`openapi-typescript`, por exemplo);
este arquivo explica **como usar** o que está lá.

Para o passo a passo de construir a extensão (login dentro do editor, envio de pasta do
projeto e acompanhamento do job), veja [`guia-extensao.md`](guia-extensao.md).

| Ambiente | Base URL |
| :--- | :--- |
| Produção | `https://api.legacydoc.com.br` |
| Local | `http://127.0.0.1:8001` |

A documentação interativa, gerada do código, fica em `/docs` na mesma base URL.

---

## 1. Autenticação: use chave de API, não JWT

A API aceita duas credenciais no mesmo header:

```
Authorization: Bearer <credencial>
```

| Credencial | Formato | Validade | Para quê |
| :--- | :--- | :--- | :--- |
| JWT de sessão | `eyJhbGci...` | 24h (configurável) | Front web |
| Chave de API | `ldk_...` | Não expira; revogável | **Extensão VS Code**, CI |

**A extensão deve usar chave de API.** Um JWT obrigaria o desenvolvedor a refazer
login dentro do editor todo dia.

Fluxo de onboarding sugerido na extensão:

1. O usuário gera a chave (`POST /v1/auth/api-keys`). **O front web ainda não tem tela
   para isso**, então por enquanto a chave se gera assim, com o e-mail e a senha da
   conta (o comando devolve o valor uma única vez, depois só o hash existe):

   ```bash
   TOKEN=$(curl -s -X POST https://api.legacydoc.com.br/v1/auth/login      -H "Content-Type: application/json"      -d '{"email":"voce@exemplo.com","password":"sua-senha"}' | jq -r .access_token)

   curl -s -X POST https://api.legacydoc.com.br/v1/auth/api-keys      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"      -d '{"name":"vscode"}'
   ```
2. A extensão pede a chave e guarda em `context.secrets` (o SecretStorage do VS Code,
   nunca em `settings.json`, que vai para o controle de versão do usuário).
3. Valida com `GET /v1/auth/me` — devolve o plano e o consumo do mês.

```http
GET /v1/auth/me
Authorization: Bearer ldk_xxx

200 OK
{
  "id": "…", "email": "dev@exemplo.com", "display_name": null,
  "plan": {
    "tier": "pro", "display_name": "Pro",
    "monthly_job_quota": 500, "max_files_per_job": 50, "max_concurrent_jobs": 4,
    "features": ["documentation", "improvement_findings", "project_context", …],
    "max_depth": "pro",
    "available_depths": ["basic", "standard", "pro"]
  },
  "jobs_used_this_month": 37
}
```

Use `plan.features` para decidir o que mostrar na UI. Não hardcode os planos: eles
mudam sem mudar a versão da rota. `GET /v1/meta/plans` lista todos.

---

## 2. O fluxo principal é assíncrono

`POST /v1/jobs` responde **202** em milissegundos. O processamento roda num worker
separado. **Não existe endpoint síncrono** que devolve a documentação pronta —
documentar um arquivo leva de segundos a minutos.

```
POST /v1/jobs ──202──> { id, status: "queued" }
      │
      └──> polling GET /v1/jobs/{id} até status terminal
                │
                └──> GET /v1/documents?job_id={id}
```

### Criar o job (caminho da extensão)

```http
POST /v1/jobs
Authorization: Bearer ldk_xxx
Content-Type: application/json

{
  "job_type": "document_snippet",
  "path": "src/services/auth.ts",
  "content": "<conteúdo do arquivo>",
  "project_id": null,
  "output_language": "pt-BR",
  "depth": "standard"
}
```

`path` serve para **detectar a linguagem** — mande o caminho real, não `arquivo.txt`.
Extensão não suportada devolve 422; consulte `GET /v1/meta/languages` no startup em
vez de embutir a lista no cliente.

Resposta `202`:

```json
{
  "id": "3f2b…", "job_type": "document_snippet", "status": "queued",
  "progress_percent": 0, "progress_message": null, "attempts": 0,
  "created_at": "2026-09-08T14:22:01Z", "document_count": 0,
  "depth": "standard", "source": "src/services/auth.ts"
}
```


### Profundidade da análise

`depth` diz quantos agentes rodam, e é o que controla o custo de cada job. Cada nível
soma um agente ao anterior:

| `depth` | O que roda | Custo medido por arquivo |
| :--- | :--- | ---: |
| `basic` | documentação e resumo | US$ 0,002 |
| `standard` | soma os pontos de melhoria | US$ 0,009 |
| `pro` | soma a auditoria contra o código | US$ 0,023 |

Omitir o campo usa o teto do plano. **Pedir acima do teto não dá erro**: o pedido é
reduzido ao que o plano permite, e o `depth` na resposta diz o que foi de fato
aplicado. Um cliente que sempre manda `pro` funciona em qualquer plano.

Monte o seletor da extensão a partir de `plan.available_depths` em `/v1/auth/me`, sem
fixar a lista no código. O mesmo campo `depth` vem em cada documento, para a UI
rotular o que foi gerado com o quê.

### Enviar um `.zip` (terceira entrada)

Para quem não tem o código no GitHub — o caso comum de sistema legado. É
`multipart/form-data`, não JSON:

```http
POST /v1/jobs/upload
Authorization: Bearer ldk_xxx
Content-Type: multipart/form-data

file=@projeto.zip
project_id=<uuid ou vazio>
output_language=pt-BR
depth=standard
```

Responde `202` com o mesmo `JobResponse` das outras entradas — daí em diante o
fluxo de polling é idêntico.

Limites e recusas:

| Situação | Resposta |
| :--- | :--- |
| Nome não termina em `.zip` | 422 |
| Bytes não são de um zip (assinatura `PK`) | 422 — o `Content-Type` que o cliente declara é ignorado |
| Maior que `MAX_UPLOAD_BYTES` (padrão 50 MB) | 422, cortado durante o streaming |
| Arquivo vazio | 422 |

O `.zip` é extraído **no worker**, com proteção contra zip slip, zip bomb,
symlink e excesso de entradas. Entrada recusada por segurança não falha o job:
vira aviso no resultado, para o usuário saber que parte do envio dele foi
descartada.

Arquivos com extensão não suportada são filtrados **durante** a extração — um
zip cheio de imagens não chega a tocar o disco.

### Acompanhar

```http
GET /v1/jobs/3f2b…
```

`status` percorre: `queued` → `running` → `succeeded` | `failed` | `cancelled`.

Use `progress_percent` e `progress_message` na barra de status do VS Code — o
worker publica mensagens reais (`"Documentando src/auth.ts (3/12)"`).

**Cadência de polling recomendada:** 1s nos primeiros 10s, depois 3s. Pare em
status terminal. Não faça polling abaixo de 1s.

Alternativa para quem não quer polling: `webhook_url` no corpo do job (requer
plano Pro). O worker faz `POST` com `{job_id, status, documents}` ao terminar.

### Buscar o resultado

```http
GET /v1/documents?job_id=3f2b…
```

Devolve a lista resumida. Para o conteúdo completo de um documento:

```http
GET /v1/documents/{document_id}
```

```json
{
  "id": "…", "path": "src/services/auth.ts", "language": "typescript",
  "summary": "Camada de autenticação…",
  "symbols": [
    {
      "name": "validateToken", "kind": "function",
      "signature": "async function validateToken(token: string): Promise<User | null>",
      "language": "typescript", "line_start": 42, "line_end": 68,
      "summary": "Valida um JWT e devolve o usuário.",
      "description": "Situação… Ação… Impacto…",
      "parameters": [{"name": "token", "type": "string", "description": "…", "optional": false, "default": null}],
      "return_type": "Promise<User | null>", "return_description": "…",
      "raises": [], "side_effects": ["Consulta o banco de usuários"],
      "complexity_estimate": 7, "parent": null
    }
  ],
  "findings": [
    {
      "id": "…", "category": "security", "severity": "high",
      "title": "Token não é verificado contra revogação",
      "detail": "…", "suggestion": "…",
      "symbol_name": "validateToken", "line_start": 51, "line_end": 53,
      "confidence": 0.8
    }
  ],
  "findings_locked": false
}
```

`line_start` / `line_end` e `complexity_estimate` vêm do **parser** (tree-sitter),
não do LLM — são confiáveis para posicionar CodeLens e diagnostics. Os campos de
texto vêm do modelo.

---

## 3. Planos: melhorias e `findings_locked`

Os pontos de melhoria são gerados conforme a **profundidade** do job (`standard` ou
`pro`) e gravados; só retornam em plano que os libera. Numa conta que caiu de um
plano pago, os documentos antigos vêm assim:

```json
{ "findings": [], "findings_locked": true }
```

`findings_locked: true` significa "existem melhorias gravadas, mas seu plano atual
não as exibe". Quando o usuário faz upgrade, elas aparecem **sem reprocessar** e sem
custo novo de token.

**Atenção:** uma conta Free não gera melhorias (a profundidade dela é limitada a
`basic`), então para ela `findings_locked` vem `false` e `findings` vazio. O `true`
só aparece em quem caiu de um plano pago. Para oferecer upgrade a quem está no Free,
use `plan.available_depths` do `/v1/auth/me`, e não este campo.

| Recurso | Free | Pro | Team |
| :--- | :---: | :---: | :---: |
| Documentação | ✅ | ✅ | ✅ |
| Pontos de melhoria | ❌ | ✅ | ✅ |
| Contexto de projeto | ❌ | ✅ | ✅ |
| Auditoria (Verifier) | ❌ | ✅ | ✅ |
| Webhooks | ❌ | ✅ | ✅ |
| Roteamento de modelo | ❌ | ❌ | ✅ |
| Prioridade na fila | ❌ | ❌ | ✅ |
| Jobs/mês | 20 | 500 | 5.000 |
| Arquivos por job | 3 | 50 | 500 |
| Jobs simultâneos | 1 | 4 | 16 |

---

## 4. Exportar artefatos

```http
GET /v1/documents/{id}/export?format=markdown
GET /v1/documents/{id}/export?format=pdf
GET /v1/documents/{id}/export?format=json
```

Devolve os bytes com `Content-Disposition: attachment`. **Requer autenticação** —
não existe URL pública de arquivo. (Na v1 havia: `/pdfs/Doc_LegacyDoc_main.pdf`
era acessível por qualquer pessoa que adivinhasse o nome.)

Formatos disponíveis: `GET /v1/meta/export-formats`.

---

## 5. API de contexto — o que melhora a resposta

É aqui que a documentação deixa de ser genérica. O cliente registra o que o LLM
não tem como saber lendo o código:

```http
POST /v1/projects/{project_id}/context
{
  "kind": "domain_rule",
  "title": "SKU vs. EAN",
  "content": "SKU é o código interno; EAN é o código de barras global. Nunca são intercambiáveis.",
  "path_globs": ["src/catalog/**"],
  "tags": ["catalogo"],
  "weight": 300
}
```

- `kind`: `glossary`, `architecture`, `convention`, `domain_rule`, `dependency`, `freeform`.
- `path_globs`: se preenchido, o item **só** entra no prompt de arquivos que casam.
  Vazio = candidato a qualquer arquivo, selecionado por relevância lexical.
- `weight`: desempate quando o orçamento de contexto estoura. Maior vence.

O orquestrador seleciona automaticamente os itens relevantes por arquivo — mandar
tudo encareceria e diluiria o prompt.

Para a extensão, o caminho natural é ler um `.legacydoc/context/*.md` do repositório
do usuário e sincronizar com esta API.

---

## 6. Erros

Todos os erros têm o mesmo formato:

```json
{ "error": "quota_exceeded", "message": "Texto legível para o usuário.", "details": {} }
```

| HTTP | `error` | Como tratar na extensão |
| :--- | :--- | :--- |
| 401 | `authentication_error` | Chave inválida/revogada → pedir nova chave |
| 402 | `quota_exceeded` | Cota ou recurso de plano → oferecer upgrade, mostrar `message` |
| 404 | `not_found` | Recurso inexistente **ou de outro usuário** |
| 409 | `conflict` | Ex.: cancelar job que já terminou |
| 422 | `validation_error` | Extensão não suportada, URL inválida, corpo malformado |
| 429 | `rate_limited` | Backoff exponencial |
| 502 | `provider_error` | Todos os provedores de LLM falharam; o job já retentou |

Sempre mostre `message` ao usuário — é escrito para ser lido. Nunca mostre
`details`, que é diagnóstico.

`402` merece tratamento especial: é a diferença entre "deu erro" e "seu plano não
cobre isso". São duas UIs diferentes.

---

## 7. Detalhes que economizam tempo

- **Limite de concorrência**: no Free é 1 job simultâneo. Se a extensão disparar um
  job por arquivo aberto, o segundo leva 402. Enfileire do lado do cliente ou use
  `document_repository` com vários `paths` num job só.
- **Conteúdo do snippet**: limite de 1 MB. Arquivo maior deve ser recortado pela
  extensão, ou usar o job de repositório.
- **`project_id` é opcional** mas necessário para o contexto de projeto ser aplicado.
- **Cancelamento** só funciona enquanto `status == "queued"`. Job em execução não é
  interrompido — o worker só percebe no próximo heartbeat.
- **Idempotência**: `POST /v1/jobs` **não** é idempotente hoje. Se a extensão retentar
  um POST que deu timeout, pode criar job duplicado. Se isso incomodar, peça que a
  gente adicione `Idempotency-Key` — é uma mudança pequena.
- **CORS**: já configurado, mas a extensão do VS Code roda em Node, não em browser,
  então isso não te afeta.

---

## 8. Esqueleto do cliente

```ts
class LegacyDocClient {
  constructor(private baseUrl: string, private apiKey: string) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({ message: response.statusText }));
      throw new LegacyDocError(response.status, body.error, body.message);
    }

    return response.json() as Promise<T>;
  }

  documentFile(path: string, content: string, projectId?: string) {
    return this.request<Job>("/v1/jobs", {
      method: "POST",
      body: JSON.stringify({
        job_type: "document_snippet",
        path,
        content,
        project_id: projectId ?? null,
      }),
    });
  }

  getJob(id: string) {
    return this.request<Job>(`/v1/jobs/${id}`);
  }

  async waitForJob(id: string, onProgress: (job: Job) => void, signal: AbortSignal) {
    const started = Date.now();

    while (!signal.aborted) {
      const job = await this.getJob(id);
      onProgress(job);

      if (["succeeded", "failed", "cancelled"].includes(job.status)) return job;

      const elapsed = Date.now() - started;
      await new Promise(resolve => setTimeout(resolve, elapsed < 10_000 ? 1_000 : 3_000));
    }

    throw new Error("cancelado");
  }

  listDocuments(jobId: string) {
    return this.request<DocumentSummary[]>(`/v1/documents?job_id=${jobId}`);
  }

  getDocument(id: string) {
    return this.request<Document>(`/v1/documents/${id}`);
  }
}
```

Para os tipos, rode:

```bash
npx openapi-typescript docs/openapi.json -o src/api-types.ts
```

---

## 9. O que ainda não existe

Sinalizado para não haver surpresa a meio caminho:

- **Sem streaming.** O progresso vem por polling, não por SSE/WebSocket.
- **Sem retomada de upload.** Um `.zip` de 50 MB que cair no meio recomeça do zero.
- **Sem endpoint de diff.** Documentar só o que mudou desde o último commit ainda
  não existe; `content_sha256` está gravado em cada documento, então dá para
  construir, mas a rota não está pronta.
- **Sem `Idempotency-Key`** (ver seção 7).

---

## 10. Limites de requisição e o que o cliente deve fazer

A API limita por IP, em três faixas. Ao estourar, responde `429` com o cabeçalho
`Retry-After` (segundos) e o mesmo envelope de erro das outras falhas:

| Faixa | Limite | Rotas |
| :--- | :--- | :--- |
| Leitura | 240 por minuto | tudo que não está abaixo, inclusive o polling de job |
| Criação de job | 30 por 5 minutos | `POST /v1/jobs` e `/v1/jobs/upload` |
| Credencial | 20 por 5 minutos | login, cadastro e redefinição de senha |

Respostas de sucesso trazem `X-RateLimit-Limit` e `X-RateLimit-Remaining`. O polling
a cada 2 a 3 segundos cabe folgado na faixa de leitura; **obedeça o `Retry-After`** em
vez de insistir, porque insistir só prolonga o bloqueio.

## 11. CORS não se aplica à extensão

O CORS restringe **navegadores**. Uma extensão roda no processo Node do VS Code e não
envia `Origin`, então nada aqui a afeta. Se um dia ela abrir um *webview* que chame a
API diretamente do JavaScript da página, aí a origem do webview precisa estar em
`ALLOWED_ORIGINS`. O caminho recomendado é o webview pedir à extensão, e a extensão
chamar a API.

## 12. Erros que a extensão deve tratar

| Status | Significa | O que fazer |
| :---: | :--- | :--- |
| 401 | Chave ausente, inválida ou revogada | Pedir a chave de novo |
| 402 | Cota mensal, teto de gasto ou recurso fora do plano | Mostrar `message`, que já diz o que faltou |
| 404 | Recurso não existe **ou não é seu** | Tratar igual: a API não distingue de propósito |
| 422 | Corpo inválido ou linguagem não suportada | Mostrar `message` |
| 429 | Limite de requisições | Esperar `Retry-After` |
