# Guia da extensão do VS Code — login e consumo da API

Passo a passo para construir a extensão do Legacy Doc do zero até "seleciono um
arquivo ou abro uma pasta e recebo a documentação". Complementa o
[`api-contract.md`](api-contract.md), que é a referência campo a campo; aqui está a
**ordem** em que as coisas acontecem e o código que liga uma à outra.

| | |
| :--- | :--- |
| API de produção | `https://api.legacydoc.com.br` |
| API local | `http://127.0.0.1:8001` |
| Documentação interativa | `<base>/docs` |
| Tipos TypeScript | `npx openapi-typescript docs/openapi.json -o src/api-types.ts` |

---

## Visão geral

```
        EXTENSÃO                                         API
 ┌──────────────────────┐
 │ 1. Login no editor   │── POST /v1/auth/login ───────> e-mail + senha
 │    (e-mail e senha)  │<─ access_token (JWT, 24h) ────
 │                      │── POST /v1/auth/api-keys ────> troca o JWT por uma chave
 │                      │<─ ldk_... (aparece UMA vez) ──
 │ 2. Guarda a chave    │   SecretStorage; senha e JWT são descartados
 ├──────────────────────┤
 │ 3. Toda chamada      │── Authorization: Bearer ldk_...
 ├──────────────────────┤
 │ 4a. Arquivo aberto   │── POST /v1/jobs (document_snippet) ─────────┐
 │ 4b. Pasta do projeto │── POST /v1/jobs/upload (.zip) ──────────────┤ 202 + id
 │ 4c. Link do GitHub   │── POST /v1/jobs (document_repository) ──────┘
 ├──────────────────────┤
 │ 5. Barra de progresso│── GET /v1/jobs/{id}  (polling) ─> queued → running → succeeded
 │ 6. Resultado         │── GET /v1/documents?job_id=  e  /v1/documents/{id}
 └──────────────────────┘
```

Regra que atravessa tudo: **a extensão nunca guarda a senha e nunca usa o JWT depois
do login.** O JWT existe só por alguns segundos, para trocar por uma chave de API.

---

## Passo 1 — Entender por que chave de API e não JWT

| | JWT (front web) | Chave de API (extensão) |
| :--- | :--- | :--- |
| Formato | `eyJhbGci...` | `ldk_...` |
| Validade | 24 horas | Não expira |
| Revogável | Não (expira sozinho) | Sim, por chave |
| Painel administrativo | Acessa | **Não acessa** (a API responde 404) |

Com JWT o desenvolvedor teria de refazer o login dentro do editor todo dia. A chave
não expira e pode ser revogada individualmente se o notebook for perdido. O painel
de contas rejeita chave de API de propósito: uma chave vazada no editor não pode
gerenciar contas de ninguém.

---

## Passo 2 — Testar a API na mão antes de escrever código

Faça isso primeiro. Se funcionar no terminal, qualquer problema depois é da
extensão, não da API.

```bash
API=https://api.legacydoc.com.br

# 1) login -> JWT
TOKEN=$(curl -s -X POST $API/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"voce@exemplo.com","password":"sua-senha"}' | jq -r .access_token)

# 2) troca o JWT por uma chave de API (o valor só aparece agora)
curl -s -X POST $API/v1/auth/api-keys \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"teste-terminal"}'
# -> { "id": "...", "api_key": "ldk_...", "prefix": "ldk_abcd", ... }

# 3) usa a chave
curl -s $API/v1/auth/me -H "Authorization: Bearer ldk_..."
```

O `/v1/auth/me` devolve o plano, o consumo do mês e `plan.available_depths`, que é o
que a extensão usa para montar o seletor de profundidade.

---

## Passo 3 — Login dentro da extensão

O usuário nunca sai do editor e nunca copia uma chave. Isso não exige nenhuma
mudança na API: são os dois endpoints do passo 2, encadeados.

### 3.1 Fluxo

1. Comando **"Legacy Doc: Entrar"** (`legacydoc.signIn`).
2. `showInputBox` pede o e-mail e depois a senha (`password: true`).
3. `POST /v1/auth/login` → JWT.
4. `POST /v1/auth/api-keys` com o JWT, nome `VS Code — <nome da máquina>`.
5. Grava a chave **e o `id` dela** no `SecretStorage`. Descarta senha e JWT.
6. `GET /v1/auth/me` confirma e mostra "Conectado como fulano (Pro)" na barra de status.

Cadastro: o botão **"Criar conta"** abre `https://app.legacydoc.com.br/criar-conta` no
navegador (`vscode.env.openExternal`). Cadastrar dentro do editor duplicaria a
validação de senha para pouco ganho. Depois do cadastro, o usuário volta e faz o
passo acima.

### 3.2 Código

```ts
import * as vscode from "vscode";
import * as os from "node:os";

const KEY = "legacydoc.apiKey";
const KEY_ID = "legacydoc.apiKeyId";

export class Auth {
  constructor(
    private readonly secrets: vscode.SecretStorage,
    private readonly baseUrl: string,
  ) {}

  async apiKey(): Promise<string | undefined> {
    return this.secrets.get(KEY);
  }

  async signIn(): Promise<void> {
    const email = await vscode.window.showInputBox({
      prompt: "E-mail da sua conta Legacy Doc",
      ignoreFocusOut: true,
    });
    if (!email) return;

    const password = await vscode.window.showInputBox({
      prompt: "Senha",
      password: true,
      ignoreFocusOut: true, // não perde o que foi digitado se o foco sair
    });
    if (!password) return;

    const login = await this.post<{ access_token: string }>("/v1/auth/login", { email, password });

    const created = await this.post<{ id: string; api_key: string }>(
      "/v1/auth/api-keys",
      { name: `VS Code — ${os.hostname()}` },
      login.access_token,
    );

    await this.secrets.store(KEY, created.api_key);
    await this.secrets.store(KEY_ID, created.id);
  }

  async signOut(): Promise<void> {
    const key = await this.secrets.get(KEY);
    const id = await this.secrets.get(KEY_ID);

    // Revoga no servidor: apagar só localmente deixaria uma chave viva sem dono.
    if (key && id) {
      await fetch(`${this.baseUrl}/v1/auth/api-keys/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${key}` },
      }).catch(() => undefined); // sem rede: ainda assim limpa o local
    }

    await this.secrets.delete(KEY);
    await this.secrets.delete(KEY_ID);
  }

  private async post<T>(path: string, body: unknown, bearer?: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const erro = await response.json().catch(() => ({ message: response.statusText }));
      throw new LegacyDocError(response.status, erro.error, erro.message);
    }

    return response.json() as Promise<T>;
  }
}
```

No `activate`, passe `context.secrets`. **Nunca** grave a chave em `settings.json` nem
em `globalState`: o primeiro costuma ir para o controle de versão do usuário, e o
segundo não é criptografado. O `SecretStorage` usa o cofre do sistema (Keychain,
Credential Manager, libsecret).

### 3.3 O que pode dar errado no login

| Resposta | Causa | Mensagem na extensão |
| :--- | :--- | :--- |
| 401 `authentication_error` | E-mail ou senha errados | Mostre o `message` da API |
| 401 depois de várias tentativas | Conta bloqueada por tentativas (lockout) | Mostre o `message` (diz que a conta está bloqueada por um tempo e sugere redefinir a senha) |
| 429 `rate_limited` | Mais de 20 tentativas de credencial em 5 min no mesmo IP | Espere o `Retry-After` |
| 401 em qualquer chamada depois | Chave revogada ou apagada | Apague o `SecretStorage` e abra o fluxo de login |

O último caso é importante: **qualquer 401 depois do login significa "entre de novo"**,
não "erro genérico". Trate isso num único lugar (o método `request`, passo 4).

### 3.4 Evolução futura (não fazer agora)

Login pelo navegador (a extensão abre a página, o usuário autentica lá e volta pelo
`vscode://legacydoc.legacydoc/callback`). É melhor quando houver login social ou
autenticação em dois fatores, porque a senha nem passa pela extensão. Exige um
endpoint novo na API, então fica para depois do MVP.

---

## Passo 4 — Cliente HTTP

Uma classe só, com um `request` que trata os erros em um lugar:

```ts
export class LegacyDocError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

export class LegacyDocClient {
  constructor(private readonly baseUrl: string, private readonly auth: Auth) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const key = await this.auth.apiKey();
    if (!key) throw new LegacyDocError(401, "authentication_error", "Entre na sua conta.");

    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${key}`);

    // Não fixe Content-Type em multipart: o fetch precisa gerar o boundary.
    if (typeof init.body === "string") headers.set("Content-Type", "application/json");

    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers });

    if (response.ok) {
      return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
    }

    const erro = await response.json().catch(() => ({ error: "unknown", message: response.statusText }));

    if (response.status === 401) await this.auth.signOut();

    throw new LegacyDocError(response.status, erro.error, erro.message);
  }

  me() { return this.request<Me>("/v1/auth/me"); }
  languages() { return this.request<Language[]>("/v1/meta/languages"); }
  getJob(id: string) { return this.request<Job>(`/v1/jobs/${id}`); }
  listDocuments(jobId: string) { return this.request<DocumentSummary[]>(`/v1/documents?job_id=${jobId}`); }
  getDocument(id: string) { return this.request<DocumentFull>(`/v1/documents/${id}`); }

  documentSnippet(path: string, content: string, depth?: string, projectId?: string) {
    return this.request<Job>("/v1/jobs", {
      method: "POST",
      body: JSON.stringify({
        job_type: "document_snippet",
        path,
        content,
        depth: depth ?? null,
        project_id: projectId ?? null,
        output_language: "pt-BR",
      }),
    });
  }

  documentRepository(repoUrl: string, branch?: string, depth?: string) {
    return this.request<Job>("/v1/jobs", {
      method: "POST",
      body: JSON.stringify({
        job_type: "document_repository",
        repo_url: repoUrl,
        branch: branch ?? null,
        paths: [],
        depth: depth ?? null,
        output_language: "pt-BR",
      }),
    });
  }

  uploadArchive(zip: Uint8Array, name: string, depth?: string, projectId?: string) {
    const form = new FormData();
    form.append("file", new Blob([zip], { type: "application/zip" }), name);
    form.append("output_language", "pt-BR");
    if (depth) form.append("depth", depth);
    if (projectId) form.append("project_id", projectId);

    return this.request<Job>("/v1/jobs/upload", { method: "POST", body: form });
  }
}
```

`fetch`, `FormData` e `Blob` são globais no Node 18+, que é o que o VS Code 1.82 em
diante traz. Se a extensão precisar suportar versão mais antiga, use `undici`.

---

## Passo 5 — Enviar o que está na máquina (o novo recurso)

Antes só era possível documentar um **link do GitHub**. Agora há três entradas, e a
extensão deve oferecer as três num único comando **"Legacy Doc: Documentar…"**:

| Entrada | Quando | Endpoint | Precisa de zip |
| :--- | :--- | :--- | :---: |
| **Arquivo aberto / seleção** | O caso mais comum no editor | `POST /v1/jobs` (`document_snippet`) | Não |
| **Pasta do projeto** | Projeto local, sem GitHub, ou com mudanças não commitadas | `POST /v1/jobs/upload` | Sim |
| **Link de repositório** | Repositório público | `POST /v1/jobs` (`document_repository`) | Não |

### 5.1 Arquivo aberto (não precisa de zip)

Aqui a IDE tem uma vantagem sobre o site: `document.getText()` devolve o conteúdo
**do buffer**, inclusive o que ainda não foi salvo.

```ts
const editor = vscode.window.activeTextEditor;
if (!editor) return;

const relativo = vscode.workspace.asRelativePath(editor.document.uri, false);
const job = await client.documentSnippet(relativo, editor.document.getText(), depth);
```

- Mande o **caminho real** em `path`, porque é ele que detecta a linguagem. `arquivo.txt`
  devolve 422.
- Limite de 1 MB por arquivo. Acima disso, recorte ou use a pasta.
- No plano Free só há 1 job simultâneo: um segundo dispara 402. Enfileire no cliente.

### 5.2 Pasta do projeto (zip)

O servidor aceita `.zip` de até **50 MB**, com no máximo **5.000 arquivos**, e ignora
arquivos de código maiores que **512 KB**. Como o envio é caro em banda e tempo, a
extensão deve **filtrar antes de zipar**, com as mesmas regras do servidor. Mandar
`node_modules` pela rede para o servidor descartar gasta o limite de 50 MB à toa.

Regras (as mesmas do site; a implementação de referência é o
`src/services/upload.ts` do front):

1. **Extensões**: só as de `GET /v1/meta/languages`. Busque no startup e cacheie; não
   embuta a lista, porque uma linguagem nova no servidor deve valer sem atualizar a
   extensão.
2. **Pastas ignoradas** (qualquer nível): `node_modules`, `vendor`, `third_party`,
   `dist`, `build`, `out`, `target`, `bin`, `obj`, `venv`, `env`, `__pycache__`,
   `pods`, `bower_components`, `coverage`, `site-packages`, e toda pasta que comece
   com `.` (`.git`, `.venv`, `.idea`).
3. **Gerados**: nome contendo `.min.js`, `.min.css`, `.bundle.js`, `.generated.`,
   `_pb2.py`, `.pb.go`.
4. **Tamanho**: descarte arquivo acima de 512 KB.
5. **Caminhos no zip**: relativos à raiz do workspace, com `/` (nunca `\`), sem a
   pasta do projeto no começo. É assim que o caminho aparece no resultado.

No VS Code, `findFiles` já ignora o que o usuário excluiu; combine com a lista acima:

```ts
import { zip } from "fflate"; // npm i fflate

const PASTAS_IGNORADAS =
  "**/{node_modules,vendor,third_party,thirdparty,dist,build,out,target,bin,obj,venv,env,__pycache__,Pods,bower_components,coverage,site-packages,.*}/**";

const GERADOS = [".min.js", ".min.css", ".bundle.js", ".generated.", "_pb2.py", ".pb.go"];
const MAX_ARQUIVO = 512 * 1024;
const MAX_ENTRADAS = 5000;
const MAX_ZIP = 50 * 1024 * 1024;

async function empacotarWorkspace(extensoes: Set<string>, progress: vscode.Progress<{ message: string }>) {
  const raiz = vscode.workspace.workspaceFolders?.[0];
  if (!raiz) throw new Error("Abra uma pasta no VS Code primeiro.");

  const encontrados = await vscode.workspace.findFiles(
    new vscode.RelativePattern(raiz, "**/*"),
    PASTAS_IGNORADAS,
    MAX_ENTRADAS + 1,
  );

  const entradas: Record<string, Uint8Array> = {};
  let descartados = 0;

  for (const uri of encontrados) {
    const caminho = vscode.workspace.asRelativePath(uri, false).replace(/\\/g, "/");
    const nome = caminho.split("/").pop() ?? "";
    const ponto = nome.lastIndexOf(".");
    const extensao = ponto > 0 ? nome.slice(ponto).toLowerCase() : "";

    if (!extensoes.has(extensao) || GERADOS.some((g) => nome.includes(g))) { descartados++; continue; }

    const bytes = await vscode.workspace.fs.readFile(uri);
    if (bytes.byteLength > MAX_ARQUIVO) { descartados++; continue; }

    entradas[caminho] = bytes;
    if (Object.keys(entradas).length >= MAX_ENTRADAS) break;
  }

  if (Object.keys(entradas).length === 0) {
    throw new Error("Nenhum arquivo de código suportado foi encontrado nesta pasta.");
  }

  progress.report({ message: "Compactando…" });

  const compactado = await new Promise<Uint8Array>((resolve, reject) =>
    zip(entradas, { level: 6 }, (erro, dados) => (erro ? reject(erro) : resolve(dados))),
  );

  if (compactado.byteLength > MAX_ZIP) {
    throw new Error("O projeto compactado passa de 50 MB. Abra uma subpasta com menos código.");
  }

  return { zip: compactado, nome: `${raiz.name}.zip`, arquivos: Object.keys(entradas).length, descartados };
}
```

Uso, com barra de progresso nativa:

```ts
await vscode.window.withProgress(
  { location: vscode.ProgressLocation.Notification, title: "Legacy Doc", cancellable: true },
  async (progress, cancelamento) => {
    progress.report({ message: "Preparando os arquivos…" });
    const pacote = await empacotarWorkspace(await languages(), progress);

    progress.report({ message: `Enviando ${pacote.arquivos} arquivos…` });
    const job = await client.uploadArchive(pacote.zip, pacote.nome, depth);

    await acompanhar(job.id, progress, cancelamento);
  },
);
```

Nome do zip = nome da pasta: é o que a tela de resultado mostra como origem da análise.

**Aviso de plano antes de enviar.** Free documenta 3 arquivos por job, Pro 50, Team 500.
Se o projeto tem mais que `plan.max_files_per_job` (vem no `/me`), avise: "Seu plano
documenta até 3 arquivos; os demais serão ignorados." O envio não falha, mas o usuário
não deve descobrir isso só no resultado.

**Se quiser o conteúdo não salvo no zip**, troque `fs.readFile` por
`workspace.textDocuments.find(d => d.uri.toString() === uri.toString())?.getText()`
quando o documento estiver `isDirty`. Vale para uma segunda versão.

### 5.3 Link de repositório

Igual ao do site: `documentRepository(url, branch, depth)`. A API só aceita URL HTTPS
de `github.com`, `gitlab.com` e `bitbucket.org`, sem credencial embutida, e clona
sem autenticação: repositório privado não funciona por aqui. Para ele, use a pasta
do projeto (5.2). `branch` é opcional; omitido, vale a branch padrão.

### 5.4 O que a API devolve ao receber o zip

`202` com o mesmo `Job` das outras entradas, então **o acompanhamento é idêntico**.
O zip é extraído no worker, com proteção contra zip slip, zip bomb, symlink e excesso
de entradas. Entrada recusada por segurança não falha o job; vira aviso no resultado.

| Recusa | Status |
| :--- | :---: |
| Nome não termina em `.zip` | 422 |
| Bytes não são de um zip (assinatura `PK`); o `Content-Type` declarado é ignorado | 422 |
| Maior que 50 MB | 422 |
| Arquivo vazio | 422 |
| Cota, teto de gasto ou plano insuficiente | 402 |

---

## Passo 6 — Acompanhar o job

```ts
async function acompanhar(id: string, progress: vscode.Progress<{ message: string }>, cancelamento: vscode.CancellationToken) {
  const inicio = Date.now();

  while (!cancelamento.isCancellationRequested) {
    const job = await client.getJob(id);
    progress.report({ message: job.progress_message ?? job.status });

    if (["succeeded", "failed", "cancelled"].includes(job.status)) return job;

    // 1 s nos primeiros 10 s, depois 3 s. Nunca abaixo de 1 s.
    await new Promise((r) => setTimeout(r, Date.now() - inicio < 10_000 ? 1_000 : 3_000));
  }
}
```

`status`: `queued` → `running` → `succeeded` | `failed` | `cancelled`. O
`progress_message` é real (`"Documentando src/auth.ts (3/12)"`), então mostre-o.
Cancelar com `DELETE /v1/jobs/{id}` só funciona enquanto o status é `queued`.

Em `429`, espere o `Retry-After` (segundos) em vez de insistir.

---

## Passo 7 — Mostrar o resultado

```ts
const resumos = await client.listDocuments(job.id);
const doc = await client.getDocument(resumos[0].id);
```

O que a extensão pode fazer com cada campo:

| Campo | Uso no VS Code |
| :--- | :--- |
| `symbols[].line_start/line_end` | **CodeLens** acima de cada função com o resumo. Vêm do parser, não do modelo: são confiáveis para posicionar |
| `symbols[].description`, `parameters`, `raises` | Hover ao passar o mouse na função |
| `findings[]` (categoria, severidade, linha) | **Diagnostics** (sublinhado e painel Problemas). Também ancorados no parser |
| `findings_locked: true` | Plano sem melhorias: mostre "N melhorias identificadas; disponíveis no plano Pro" com botão de upgrade |
| `summary` | Cabeçalho do painel |

Exportar: `GET /v1/documents/{id}/export?format=markdown|pdf|json` devolve os bytes, e
**exige autenticação** (não há URL pública). Use `workspace.fs.writeFile` para salvar.

---

## Passo 8 — Erros

Todos vêm no mesmo formato: `{ "error", "message", "details" }`. **Mostre `message`**,
que é escrito para ser lido. **Nunca mostre `details`**, que é diagnóstico.

| HTTP | `error` | Na extensão |
| :---: | :--- | :--- |
| 401 | `authentication_error` | Chave inválida ou revogada → abrir o login |
| 402 | `quota_exceeded` | Cota, teto ou recurso fora do plano → mostrar `message` e oferecer upgrade. **É outra UI que "deu erro"** |
| 404 | `not_found` | Não existe ou é de outro usuário |
| 409 | `conflict` | Cancelar job que já terminou |
| 422 | `validation_error` | Extensão não suportada, zip inválido, corpo malformado |
| 429 | `rate_limited` | Esperar o `Retry-After` |
| 502 | `provider_error` | Os provedores de IA falharam; o job já tentou de novo |

## Limites que valem para a extensão

| | Limite |
| :--- | :--- |
| Snippet (`document_snippet`) | 1 MB |
| Zip enviado | 50 MB, 5.000 entradas |
| Arquivo de código dentro do zip | 512 KB (maiores são ignorados) |
| Arquivos documentados por job | Free 3 · Pro 50 · Team 500 |
| Jobs simultâneos | Free 1 · Pro 4 · Team 16 |
| Criar job | 30 a cada 5 min por IP |
| Leitura (polling) | 240 por minuto por IP |
| Login/cadastro | 20 a cada 5 min por IP |

`depth` pedido acima do que o plano permite **não dá erro**: é reduzido ao teto do
plano, e o `depth` da resposta diz o que foi aplicado. Monte o seletor da UI com
`plan.available_depths` do `/me`.

---

## Ordem sugerida de implementação

1. Passo 2 (curl) funcionando com a conta do próprio time.
2. `Auth` + `LegacyDocClient` + comando **Entrar**/**Sair**, e a barra de status
   mostrando "Conectado como … (plano)" via `/me`.
3. **Arquivo aberto** (5.1) + `acompanhar` + mostrar o resumo. É o menor caminho até
   ver documentação aparecendo no editor.
4. **CodeLens/Diagnostics** com `line_start` e `findings`.
5. **Pasta do projeto** (5.2), com o aviso de limite do plano.
6. Link de repositório e exportação.

## O que ainda não existe na API

- Tela para gerenciar chaves de API no site (por enquanto, revogar é pela extensão ou
  por `DELETE /v1/auth/api-keys/{id}`).
- Login pelo navegador (`vscode://` callback).
- Streaming de progresso (é polling).
- Retomada de upload interrompido: um zip de 50 MB que cair recomeça.
- `Idempotency-Key`: repetir um `POST` que deu timeout pode criar um job duplicado.
- Documentar só o que mudou desde o último commit.
