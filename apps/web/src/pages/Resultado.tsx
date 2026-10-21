import Navbar from "../components/Navbar";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import logo from "../assets/logo.png";
import {
  type FindingItem,
  documentToResult,
  downloadArtifact,
  getDocument,
  type DocumentSummary,
} from "../services/api";
import { useRevelar } from "../hooks/useRevelar";

type FunctionArg = {
  name: string;
  type: string;
};

type FunctionItem = {
  name: string;
  kind?: string;
  return_type?: string;
  args?: FunctionArg[];
  summary?: string;
  description?: string;
  raises?: string[];
};

type DocumentationObject = {
  file?: string;
  summary?: string;
  functions?: FunctionItem[];
};

type ApiResponse = {
  status?: string;
  file?: string;
  summary?: string;
  documentation?: FunctionItem[] | DocumentationObject;
  pdf_url?: string;
  markdown_url?: string;
  documents?: DocumentSummary[];
  depth?: string;
  findings?: FindingItem[];
  findings_locked?: boolean;
};

const ROTULO_DE_SEVERIDADE: Record<string, string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Médio",
  low: "Baixo",
  info: "Info",
};

function classeDeSeveridade(severidade: string) {
  if (severidade === "critical" || severidade === "high") return "high";
  if (severidade === "medium") return "medium";
  return "low";
}

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
      <rect x="5" y="10.5" width="14" height="9.5" rx="2.2" fill="currentColor" />
      <path
        d="M8 10.5V7.5a4 4 0 0 1 8 0v3"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function getRepoName(repoUrl: string | null) {
  if (!repoUrl) return "Repositório não informado";

  const clean = repoUrl.replace(".git", "");
  const parts = clean.split("/").filter(Boolean);

  return parts[parts.length - 1] || "Repositório analisado";
}

function getLanguageByFile(fileName: string) {
  const lower = fileName.toLowerCase();

  if (lower.endsWith(".cpp") || lower.endsWith(".c") || lower.endsWith(".h")) {
    return "C / C++";
  }

  if (lower.endsWith(".py")) return "Python";
  if (lower.endsWith(".ts") || lower.endsWith(".tsx")) return "TypeScript";
  if (lower.endsWith(".js") || lower.endsWith(".jsx")) return "JavaScript";
  if (lower.endsWith(".java")) return "Java";
  if (lower.endsWith(".cs")) return "C#";

  return "Não identificada";
}

function getStackByLanguage(language: string) {
  if (language.includes("C")) {
    return ["C/C++", "Funções", "Headers", "Compilação nativa", "Entrada/Saída"];
  }

  if (language === "Python") {
    return ["Python", "Módulos", "Funções", "Scripts", "Automação"];
  }

  if (language === "TypeScript") {
    return ["TypeScript", "React", "Componentes", "Services", "Vite"];
  }

  if (language === "JavaScript") {
    return ["JavaScript", "Node.js", "Funções", "Módulos", "Frontend"];
  }

  return ["Código-fonte", "Funções", "Estrutura", "Documentação", "Análise"];
}

export default function Resultado() {
  const navigate = useNavigate();

  const raw = localStorage.getItem("legacyDocResult");
  const repoUrl = localStorage.getItem("repoUrl");

  const [result, setResult] = useState<ApiResponse | null>(() =>
    raw ? JSON.parse(raw) : null
  );
  const [loadingFile, setLoadingFile] = useState<string | null>(null);

  const documents = result?.documents ?? [];

  useRevelar([result?.file]);

  async function abrirArquivo(item: DocumentSummary) {
    if (loadingFile || item.path === result?.file) return;

    setLoadingFile(item.path);

    try {
      const detail = await getDocument(item.id);
      const next = documentToResult(detail, documents);

      setResult(next);
      localStorage.setItem("legacyDocResult", JSON.stringify(next));
    } catch (error) {
      alert(error instanceof Error ? error.message : "Não foi possível abrir o arquivo.");
    } finally {
      setLoadingFile(null);
    }
  }

  const functions: FunctionItem[] = Array.isArray(result?.documentation)
    ? result.documentation
    : result?.documentation?.functions ?? [];

  const fileName =
    result?.file ||
    (!Array.isArray(result?.documentation) && result?.documentation?.file) ||
    "Arquivo analisado";

  const firstFunction = functions[0];

  const summary =
    result?.summary ||
    (!Array.isArray(result?.documentation) && result?.documentation?.summary) ||
    firstFunction?.summary ||
    "Documentação gerada automaticamente com base na análise do repositório.";

  const findings = result?.findings ?? [];

  const bloqueadosPeloPlano = Boolean(result?.findings_locked);

  const modoDoRelatorio = result?.depth === "pro" ? "pro" : undefined;

  const repoName = getRepoName(repoUrl);
  const language = getLanguageByFile(fileName);
  const stack = getStackByLanguage(language);

  const totalFunctions = functions.length;

  const totalArgs = functions.reduce(
    (acc, fn) => acc + (fn.args?.length ?? 0),
    0
  );

  const functionsWithArgs = functions.filter(
    (fn) => (fn.args?.length ?? 0) > 0
  ).length;

  const functionsWithRaises = functions.filter(
    (fn) => (fn.raises?.length ?? 0) > 0
  ).length;

  const qualityScore = Math.max(
    65,
    Math.min(96, 88 - functionsWithRaises * 4 + functionsWithArgs * 2)
  );

  async function handleDownloadPdf() {
    if (!result?.pdf_url) {
      alert("PDF ainda não disponível.");
      return;
    }

    try {
      await downloadArtifact(result.pdf_url, "documentacao.pdf");
    } catch (error) {
      alert(error instanceof Error ? error.message : "Falha ao baixar o PDF.");
    }
  }

  async function handleDownloadMD() {
    if (!result?.markdown_url) {
      alert("Markdown não disponível para este item.");
      return;
    }

    try {
      await downloadArtifact(result.markdown_url, "documentacao.md");
    } catch (error) {
      alert(error instanceof Error ? error.message : "Falha ao baixar o Markdown.");
    }
  }

  if (!result) {
    return (
      <>
        <Navbar />

        <main id="conteudo" className="main-screen">
          <section className="hero">
            <span className="badge">Sem resultado</span>

            <h1>Nenhum resultado encontrado</h1>

            <p className="hero-subtitle">
              Faça uma análise antes de acessar esta página.
            </p>

            <button className="btn" onClick={() => navigate("/", { viewTransition: true })}>
              Voltar
            </button>
          </section>
        </main>
      </>
    );
  }

  return (
    <>
      <Navbar />

      <main
        id="conteudo"
        className="result-page"
        data-modo={modoDoRelatorio}
      >
        <section className="report-paper">
          <header className="report-header">
            <div className="report-brand">
            <img src={logo} alt="Legacy Doc" className="report-logo-img" />
            </div>

            <div className="report-generated">
              <span>GERADO AUTOMATICAMENTE</span>
              <strong>{new Date().toLocaleString("pt-BR")}</strong>
            </div>
          </header>

          <section className="report-hero">
            <div className="report-title-block">
              <div className="report-kicker-row">
                <span className="report-kicker">DOCUMENTAÇÃO TÉCNICA</span>

                {result.depth === "pro" && (
                  <span className="pro-badge">Auditado</span>
                )}
              </div>

              <h1>Documentação Técnica Automatizada</h1>

              <p>{summary}</p>

              <div className="report-actions">
                <button className="btn" onClick={handleDownloadPdf}>
                  Baixar PDF
                </button>

                <button className="btn" onClick={handleDownloadMD}>
                  Baixar Markdown
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={() => navigate("/", { viewTransition: true })}
                >
                  Nova análise
                </button>
              </div>
            </div>

            <aside className="repo-info-card">
              <div className="section-heading compact">
                <span>▣</span>
                <h2>Repositório</h2>
              </div>

              <div className="repo-row">
                <span>Projeto</span>
                <strong>{repoName}</strong>
              </div>

              <div className="repo-row">
                <span>URL</span>
                <strong>{repoUrl || "Não informado"}</strong>
              </div>

              <div className="repo-row">
                <span>Arquivo</span>
                <strong className="file-path">{fileName}</strong>
              </div>

              <div className="repo-row">
                <span>Linguagem</span>
                <strong>{language}</strong>
              </div>

              <div className="repo-row">
                <span>Status</span>
                <strong className="success-text">
                  {result.status || "success"}
                </strong>
              </div>
            </aside>
          </section>

          {documents.length > 1 && (
            <>
              <div className="report-divider"></div>

              <section>
                <div className="section-heading">
                  <span>☰</span>
                  <h2>
                    Arquivos analisados ({documents.length})
                  </h2>
                </div>

                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "0.5rem",
                    marginTop: "0.75rem",
                  }}
                >
                  {documents.map((item) => {
                    const atual = item.path === fileName;

                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => abrirArquivo(item)}
                        disabled={loadingFile !== null}
                        title={item.path}
                        style={{
                          padding: "0.5rem 0.8rem",
                          borderRadius: 8,
                          border: atual
                            ? "1px solid #22c55e"
                            : "1px solid rgba(128,128,128,0.35)",
                          background: atual ? "rgba(34,197,94,0.12)" : "transparent",
                          cursor: loadingFile ? "wait" : "pointer",
                          fontSize: "0.85rem",
                          textAlign: "left",
                          opacity: loadingFile && loadingFile !== item.path ? 0.5 : 1,
                        }}
                      >
                        <strong className="file-path">
                          {item.path.split("/").pop()}
                        </strong>
                        <span style={{ opacity: 0.65, marginLeft: 8 }}>
                          {item.symbol_count} símbolos
                          {item.finding_count > 0 && ` · ${item.finding_count} pontos`}
                        </span>
                        {loadingFile === item.path && <span> · abrindo...</span>}
                      </button>
                    );
                  })}
                </div>
              </section>
            </>
          )}

          <div className="report-divider"></div>

          <section className="report-two-columns" data-revelar>
            <div className="stack-card">
              <div className="section-heading">
                <span>▤</span>
                <h2>Stack tecnológica</h2>
              </div>

              <div className="stack-list">
                {stack.map((item, index) => (
                  <div className="stack-item" key={item}>
                    <span className="stack-icon">{index + 1}</span>
                    <strong>{item}</strong>
                  </div>
                ))}
              </div>
            </div>

            <div className="architecture-card">
              <div className="section-heading">
                <span>⌘</span>
                <h2>Visão geral da análise</h2>
              </div>

              <div className="architecture-flow">
                <div className="arch-node">Repositório</div>
                <div className="arch-arrow">→</div>
                <div className="arch-node">Arquivo</div>
                <div className="arch-arrow">→</div>
                <div className="arch-node">Funções</div>
                <div className="arch-arrow">→</div>
                <div className="arch-node">Documentação</div>
              </div>

              <p>
                O Legacy Doc analisa o código-fonte, identifica estruturas
                relevantes e transforma o conteúdo técnico em documentação
                organizada.
              </p>
            </div>
          </section>

          <section className="metrics-row" data-revelar>
            <div className="report-metric">
              <span>ƒx</span>
              <p>Funções detectadas</p>
              <strong>{totalFunctions}</strong>
            </div>

            <div className="report-metric">
              <span>◌</span>
              <p>Argumentos totais</p>
              <strong>{totalArgs}</strong>
            </div>

            <div className="report-metric">
              <span>&lt;/&gt;</span>
              <p>Linguagem</p>
              <strong>{language}</strong>
            </div>

            <div className="report-metric">
              <span>★</span>
              <p>Qualidade estrutural</p>
              <strong>{qualityScore}%</strong>
            </div>
          </section>

          <section className="report-grid-bottom" data-revelar>
            <div className="code-insight-card">
              <div className="section-heading">
                <span>&lt;/&gt;</span>
                <h2>Insights de código</h2>
              </div>

              <div className="code-window">
                <pre>
{`arquivo: ${fileName}
funções: ${totalFunctions}
argumentos: ${totalArgs}
linguagem: ${language}
status: ${result.status || "success"}`}
                </pre>
              </div>

              <div className="info-note">
                A análise identificou estruturas documentáveis e transformou os
                principais elementos técnicos em informação legível.
              </div>
            </div>

            <div className="improvements-card" data-modo={modoDoRelatorio}>
              <div className="section-heading">
                <span>⚠</span>
                <h2>Pontos de melhoria</h2>
              </div>

              {findings.length > 0 ? (
                <div className="improvement-list">
                  {findings.map((ponto) => (
                    <div
                      key={ponto.id}
                      className={`improvement-item ${classeDeSeveridade(ponto.severity)}`}
                    >
                      <strong>{ponto.title}</strong>
                      <p>{ponto.detail}</p>

                      {ponto.suggestion && (
                        <p className="improvement-suggestion">{ponto.suggestion}</p>
                      )}

                      {ponto.symbol_name && (
                        <span className="improvement-local mono">
                          {ponto.symbol_name}
                          {ponto.line_start ? `:${ponto.line_start}` : ""}
                        </span>
                      )}

                      <span>{ROTULO_DE_SEVERIDADE[ponto.severity] ?? ponto.severity}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="melhorias-travadas" data-modo="pro">
                  <span className="depth-lock" aria-hidden="true">
                    <LockIcon />
                  </span>

                  <strong>
                    {bloqueadosPeloPlano
                      ? "Esta análise encontrou pontos de melhoria"
                      : "Este nível não procura pontos de melhoria"}
                  </strong>

                  <p>
                    {bloqueadosPeloPlano
                      ? "Eles já estão gravados e aparecem assim que o plano cobrir. Nada será reprocessado nem cobrado de novo."
                      : "Os níveis Padrão e Completo apontam risco, complexidade e code smell em cada função, com o trecho exato onde está."}
                  </p>

                  <span className="pro-badge">Incluído no Pro</span>
                </div>
              )}
            </div>

            <div className="modules-card">
              <div className="section-heading">
                <span>▦</span>
                <h2>Resumo do projeto</h2>
              </div>

              <div className="project-summary-list">
                <div>
                  <span>Arquivo analisado</span>
                  <strong className="file-path">{fileName}</strong>
                </div>

                <div>
                  <span>Funções</span>
                  <strong>{totalFunctions}</strong>
                </div>

                <div>
                  <span>Com parâmetros</span>
                  <strong>{functionsWithArgs}</strong>
                </div>

                <div>
                  <span>Com raises</span>
                  <strong>{functionsWithRaises}</strong>
                </div>

                <div>
                  <span>Status</span>
                  <strong>{result.status || "success"}</strong>
                </div>
              </div>
            </div>
          </section>

          <section className="documented-functions">
            <div className="section-heading">
              <span>☰</span>
              <h2>Funções documentadas</h2>
            </div>

            {functions.length === 0 ? (
              <p className="empty-text">Nenhuma função encontrada.</p>
            ) : (
              <div className="function-report-list">
                {functions.map((fn, index) => (
                  <article
                    className="function-report-card"
                    data-revelar
                    key={`${fn.name}-${index}`}
                  >
                    <div className="function-report-header">
                      <div>
                        <span>Função</span>
                        <h3>{fn.name || "Função sem nome"}</h3>
                      </div>

                      <strong>{fn.return_type || "Retorno não informado"}</strong>
                    </div>

                    <div className="function-report-content">
                      <div>
                        <small>Tipo</small>
                        <p>{fn.kind || "function"}</p>
                      </div>

                      <div>
                        <small>Resumo</small>
                        <p>{fn.summary || "Sem resumo informado."}</p>
                      </div>

                      <div>
                        <small>Parâmetros</small>
                        <p>
                          {fn.args && fn.args.length > 0
                            ? fn.args
                                .map((arg) => `${arg.name} (${arg.type})`)
                                .join(", ")
                            : "Nenhum"}
                        </p>
                      </div>

                      <div>
                        <small>Descrição</small>
                        <p>{fn.description || "Sem descrição informada."}</p>
                      </div>

                      <div>
                        <small>Raises</small>
                        <p>
                          {fn.raises && fn.raises.length > 0
                            ? fn.raises.join(", ")
                            : "Nenhum"}
                        </p>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="report-observation">
            <strong>Observações</strong>
            <p>
              A documentação foi gerada automaticamente com base na análise do
              repositório e pode servir como apoio técnico, educacional e de
              manutenção.
            </p>
          </section>

          <footer className="report-footer">
            <strong>LEGACY DOC</strong>
            <span>Conhecimento que conecta.</span>
            <p>Página de resultado</p>
          </footer>
        </section>
      </main>
    </>
  );
}
