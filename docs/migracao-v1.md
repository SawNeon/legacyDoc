# Migração da v1

O código da v1 continua em `legacyDoc/` e `Front/`, intocado. Este documento
registra o que foi migrado, o que foi corrigido e o que ainda falta.

## O que veio da v1

Três coisas estavam certas e foram preservadas:

| v1 | v2 | Mudança |
| :--- | :--- | :--- |
| `ExporterFactory` + ABC `DocumentExporter` | `packages/exporters/base.py` | Entrada virou modelo tipado; saída virou bytes em vez de arquivo em disco, para servir HTTP, webhook e extensão com o mesmo código. |
| `validate_repo_url` | `packages/core/repository.py` | Mantida a regra (só HTTPS, só hosts conhecidos). Somados GitLab/Bitbucket e bloqueio de credencial embutida na URL. |
| Auth com argon2 + e-mail normalizado | `packages/core/security.py` | Mantida. Somadas chaves de API para a extensão e política de senha um pouco mais forte. |

## Defeitos corrigidos

### Bloqueio do event loop
`POST /api/generate` era `async def` e chamava `process_single_file`, que é
síncrono e leva minutos (clone + N chamadas de LLM). Uma requisição congelava o
servidor inteiro, inclusive o login de outros usuários.

**Agora:** a API só enfileira e devolve 202. O trabalho roda em processos worker.

### Artefatos públicos
`/pdfs`, `/markdowns` e `/data` eram `StaticFiles` sem autenticação, com nomes
determinísticos (`Doc_LegacyDoc_main.pdf`). Qualquer pessoa baixava a
documentação de qualquer cliente adivinhando o nome.

**Agora:** não existe `StaticFiles`. `GET /v1/documents/{id}/export` gera o
artefato sob demanda, autenticado e no escopo do dono.

### Ausência de isolamento entre usuários
Não havia `user_id` no armazenamento. `/api/dashboard/stats` devolvia os módulos
de **todos** os usuários para qualquer um logado, e `sanitize_filename` usava só
o basename — dois `main.cpp` de repositórios diferentes se sobrescreviam.

**Agora:** `user_id` em todas as tabelas de conteúdo, filtro em toda consulta,
e caminho completo no nome do arquivo. Coberto por
`test_api.py::test_project_is_scoped_to_owner` e vizinhos.

### Segredo JWT padrão
`os.getenv("JWT_SECRET_KEY", "legacydoc-dev-secret-do-not-use-in-production")`,
e o `.env` real não definia a variável — tokens eram assinados com uma string
pública do repositório.

**Agora:** `Settings` exige a variável, com mínimo de 32 caracteres. A aplicação
não sobe sem ela.

### O Verifier que nunca fazia nada
`MAX_REVIEW_ATTEMPTS=1` e o Writer já saía com `attempts=1`, então
`decide_next_step` avaliava `1 < 1` → sempre `END`. O Verifier rodava no `gpt-4o`
(o modelo mais caro do pipeline), sobre o arquivo inteiro mais o JSON completo,
e o resultado era descartado sem nunca reescrever nada.

**Agora:** o loop funciona e reescreve **apenas os símbolos reprovados**.
Coberto por `test_pipeline.py::test_rejected_symbols_are_actually_rewritten`.

### Chunking que perdia funções
Corte a cada 150 linhas fixas partia funções ao meio; o Writer, instruído a
ignorar definições incompletas, descartava a metade em silêncio.

**Agora:** chunking por AST (tree-sitter). Coberto por
`test_parsing.py::test_symbols_are_never_split_across_chunks`.

### PDF lia campos inexistentes
`func["returns"]` e `doc_data["constants"]` nunca existiram no schema (que
define `return_type` / `return_description`). O tipo de retorno jamais aparecia
no PDF. Também não havia tratamento de texto fora de latin-1 nem quebra de
identificadores longos.

**Agora:** campos corretos, `wrapmode="CHAR"` e degradação em vez de exceção
para caracteres não codificáveis.

### Clone órfão
Sem teto de arquivos ou de bytes; um clone deixou 101 MB em
`api/tmp_repo_7f3bbe06/`.

**Agora:** `MAX_REPO_FILES`, `MAX_REPO_BYTES`, `CLONE_TIMEOUT_SECONDS` e limpeza
em `finally`.

### Conexões SQLite vazando
`with sqlite3.connect(...)` faz commit/rollback mas **não fecha**. Cada request
de auth deixava um descritor aberto.

**Agora:** `session_scope()` com `finally: await session.close()`.

### Erros indistinguíveis
Toda falha virava `detail: "Error processing."`. O cliente não conseguia separar
cota estourada de repositório inválido ou provedor fora do ar.

**Agora:** hierarquia de erros de domínio com código estável, traduzida para
HTTP num handler único. Ver seção 6 do contrato da API.

### Um arquivo aleatório por repositório
O front mandava `file_path: "TESTE"` fixo, e o backend documentava o primeiro
arquivo C/C++ que `os.walk` encontrasse. A home prometia "analise repositórios".

**Agora:** o cliente escolhe os arquivos (`paths`), com teto por plano.

## Dependências removidas

`langgraph`, `langchain-openai`, `neo4j`, `qdrant-client` e `tree-sitter-cpp`.

- `neo4j` e `qdrant-client` estavam no `requirements.txt` mas **nunca foram
  importados** no código.
- `tree-sitter-cpp` foi substituído por `tree-sitter-language-pack`, que traz
  mais de cem gramáticas num pacote só.
- LangGraph/LangChain saíram junto com a reescrita do orquestrador (motivo no
  README).

## O que ainda falta

- **Front web.** O `Front/` da v1 fala com a API antiga. Precisa ser reescrito
  para o fluxo assíncrono. Nada nele foi migrado.
- **Teste de concorrência real da fila.** A suite roda em SQLite, que não tem
  `FOR UPDATE SKIP LOCKED`. A garantia sob concorrência depende do Postgres e
  precisa de um teste de integração com container.
- **Preços de OpenAI e Gemini** em `catalog.py`, marcados `verified=False`.
- **Rate limit por IP** nas rotas de auth.
- **Reset de senha.** A tela `TrocaSenha.tsx` da v1 mostrava "instruções
  enviadas" sem chamar backend nenhum; não existe endpoint. Não foi
  reimplementado.

## O que fazer com o código antigo

Sugestão, quando você estiver confortável:

```bash
mkdir legacy
git mv legacyDoc legacy/backend-v1
git mv Front legacy/frontend-v1
```

Note que `legacyDoc/legacyDoc/tmp_repo` está commitado como *gitlink* (modo
160000) sem `.gitmodules` — um submódulo fantasma de um clone temporário. Vale
remover:

```bash
git rm --cached legacyDoc/tmp_repo
```

E a `OPENAI_API_KEY` real que está em `legacyDoc/legacyDoc/.env`: o arquivo não
está versionado, mas a chave circulou em disco de desenvolvimento. Rotacione
antes de subir para produção.
