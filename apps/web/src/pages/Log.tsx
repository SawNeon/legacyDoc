import ConfirmarExclusao from "../components/ConfirmarExclusao";
import Navbar from "../components/Navbar";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  deleteJobRecord,
  documentToResult,
  downloadArtifact,
  exportPath,
  getAuthToken,
  getDocument,
  listDocuments,
  listJobs,
  type Job,
} from "../services/api";

const ROTULO_DE_STATUS: Record<string, string> = {
  queued: "Na fila",
  running: "Processando",
  succeeded: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
};

const STATUS_FINAIS = ["succeeded", "failed", "cancelled"];

const ROTULO_DE_NIVEL: Record<string, string> = {
  basic: "Básico",
  standard: "Padrão",
  pro: "Completo",
};

function classeDeStatus(status: string) {
  if (status === "succeeded") return "status success";
  if (status === "failed" || status === "cancelled") return "status error";
  return "status pending";
}

function formatarData(iso: string) {
  const data = new Date(iso);
  return Number.isNaN(data.valueOf()) ? iso : data.toLocaleString("pt-BR");
}

export default function Log() {
  const navigate = useNavigate();

  const [jobs, setJobs] = useState<Job[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [abrindo, setAbrindo] = useState<string | null>(null);
  const [paraExcluir, setParaExcluir] = useState<Job | null>(null);
  const [excluindo, setExcluindo] = useState<string | null>(null);
  const [erroExclusao, setErroExclusao] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    if (!aviso) return;

    const temporizador = setTimeout(() => setAviso(null), 4000);

    return () => clearTimeout(temporizador);
  }, [aviso]);

  const buscar = useCallback(
    (aplicar: (lista: Job[] | null, erro: string | null) => void) => {
      if (!getAuthToken()) {
        navigate("/login", { viewTransition: true });
        return;
      }

      listJobs()
        .then((lista) => aplicar(lista.items, null))
        .catch((erro: unknown) =>
          aplicar(
            null,
            erro instanceof Error ? erro.message : "Não foi possível carregar o histórico."
          )
        );
    },
    [navigate]
  );

  useEffect(() => {
    let ativo = true;

    buscar((lista, falha) => {
      if (!ativo) return;

      if (lista) setJobs(lista);
      setErro(falha);
      setCarregando(false);
    });

    return () => {
      ativo = false;
    };
  }, [buscar]);

  function atualizar() {
    setCarregando(true);

    buscar((lista, falha) => {
      if (lista) setJobs(lista);
      setErro(falha);
      setCarregando(false);
    });
  }

  async function abrirResultado(job: Job) {
    if (abrindo) return;

    setAbrindo(job.id);

    try {
      const documentos = await listDocuments(job.id);

      if (documentos.length === 0) {
        alert("Esta análise não gerou nenhum documento.");
        return;
      }

      const detalhe = await getDocument(documentos[0].id);

      localStorage.setItem(
        "legacyDocResult",
        JSON.stringify(documentToResult(detalhe, documentos))
      );

      localStorage.setItem("repoUrl", job.source ?? "");

      navigate("/resultado", { viewTransition: true });
    } catch (error) {
      alert(error instanceof Error ? error.message : "Não foi possível abrir o resultado.");
    } finally {
      setAbrindo(null);
    }
  }

  function pedirExclusao(job: Job) {
    setErroExclusao(null);
    setParaExcluir(job);
  }

  function fecharConfirmacao() {
    setParaExcluir(null);
    setErroExclusao(null);
  }

  async function confirmarExclusao() {
    const alvo = paraExcluir;
    if (!alvo) return;

    setExcluindo(alvo.id);
    setErroExclusao(null);

    try {
      await deleteJobRecord(alvo.id);
      setAviso("Análise excluída.");
    } catch (error) {
      const mensagem =
        error instanceof Error ? error.message : "Não foi possível excluir a análise.";

      if (!/n[aã]o encontrado/i.test(mensagem)) {
        setErroExclusao(mensagem);
        return;
      }

      setAviso("Esta análise já tinha sido excluída.");
    } finally {
      setExcluindo(null);
    }

    setJobs((atuais) => atuais.filter((item) => item.id !== alvo.id));
    fecharConfirmacao();
    atualizar();
  }

  async function baixar(job: Job, formato: "pdf" | "markdown") {
    try {
      const documentos = await listDocuments(job.id);

      if (documentos.length === 0) {
        alert("Esta análise não gerou nenhum documento.");
        return;
      }

      await downloadArtifact(
        exportPath(documentos[0].id, formato),
        formato === "pdf" ? "documentacao.pdf" : "documentacao.md"
      );
    } catch (error) {
      alert(error instanceof Error ? error.message : "Falha ao baixar o arquivo.");
    }
  }

  return (
    <>
      <Navbar />

      <main id="conteudo" className="main-screen">
        <section className="hero">
          <span className="badge">Histórico</span>

          <h1>Histórico de documentações</h1>

          <p className="hero-subtitle">
            Todas as análises desta conta, em qualquer navegador.
          </p>

          <button className="btn btn-secondary" onClick={atualizar} disabled={carregando}>
            {carregando ? "Carregando..." : "Atualizar"}
          </button>

          <p className="log-aviso" role="status" aria-live="polite">
            {aviso}
          </p>

          <div className="log-list">
            {erro && (
              <div className="log-item empty-history">
                <div className="log-left">
                  <strong>Não foi possível carregar</strong>
                  <p>{erro}</p>
                </div>
              </div>
            )}

            {!erro && !carregando && jobs.length === 0 && (
              <div className="log-item empty-history">
                <div className="log-left">
                  <strong>Nenhuma análise ainda</strong>
                  <span className="status pending">Sem registros</span>
                </div>
              </div>
            )}

            {jobs.map((job) => (
              <article className="log-item" key={job.id}>
                <div className="log-left">
                  <strong className="file-path">
                    {job.source ?? "Análise sem origem registrada"}
                  </strong>

                  <span className={classeDeStatus(job.status)}>
                    {ROTULO_DE_STATUS[job.status] ?? job.status}
                  </span>

                  <small>{formatarData(job.created_at)}</small>
                  <small>
                    Nível: {ROTULO_DE_NIVEL[job.depth] ?? job.depth} ·{" "}
                    {job.document_count} arquivo(s)
                  </small>

                  {job.error_message && <p>{job.error_message}</p>}
                </div>

                <div className="log-actions">
                  <button
                    className="btn btn-secondary"
                    disabled={job.document_count === 0 || abrindo === job.id}
                    onClick={() => abrirResultado(job)}
                  >
                    {abrindo === job.id ? "Abrindo..." : "Resultado"}
                  </button>

                  <button
                    className="btn"
                    disabled={job.document_count === 0}
                    onClick={() => baixar(job, "pdf")}
                  >
                    PDF
                  </button>

                  <button
                    className="btn"
                    disabled={job.document_count === 0}
                    onClick={() => baixar(job, "markdown")}
                  >
                    Markdown
                  </button>

                  {STATUS_FINAIS.includes(job.status) && (
                    <button
                      className="btn btn-secondary"
                      aria-label={`Excluir a análise de ${job.source ?? "origem desconhecida"}`}
                      disabled={excluindo === job.id}
                      onClick={() => pedirExclusao(job)}
                    >
                      Excluir
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>

      <ConfirmarExclusao
        origem={paraExcluir?.source ?? null}
        aberto={paraExcluir !== null}
        excluindo={excluindo !== null}
        erro={erroExclusao}
        aoConfirmar={confirmarExclusao}
        aoCancelar={fecharConfirmacao}
      />
    </>
  );
}
