import Navbar from "../components/Navbar";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { followJob, runRepositoryJob, type Job } from "../services/api";

export default function Loading() {
  const navigate = useNavigate();
  const hasStarted = useRef(false);

  const [percent, setPercent] = useState(0);
  const [message, setMessage] = useState("Enfileirando o repositório...");

  useEffect(() => {
    async function gerarAnalise() {
      if (hasStarted.current) return;
      hasStarted.current = true;

      const repoUrl = localStorage.getItem("repoUrl");
      const branch = localStorage.getItem("repoBranch");
      const depth = localStorage.getItem("repoDepth");

      const pendingJobId = localStorage.getItem("pendingJobId");
      localStorage.removeItem("pendingJobId");

      if (!repoUrl) {
        alert("Nenhum repositório informado.");
        navigate("/", { viewTransition: true });
        return;
      }

      function acompanhar(job: Job) {
        setPercent(job.progress_percent);
        setMessage(job.progress_message || "Processando...");
      }

      try {
        const data = pendingJobId
          ? await followJob(pendingJobId, acompanhar)
          : await runRepositoryJob({ repoUrl, branch, depth }, acompanhar);

        localStorage.setItem("legacyDocResult", JSON.stringify(data));

        navigate("/resultado", { viewTransition: true });
      } catch (error) {
        console.error("Erro ao gerar documentacao:", error);
        alert(error instanceof Error ? error.message : "Erro ao gerar documentação.");
        navigate("/", { viewTransition: true });
      }
    }

    gerarAnalise();
  }, [navigate]);

  return (
    <>
      <Navbar />

      <main id="conteudo" className="main-screen">
        <section className="hero">
          <span className="badge">Processando</span>

          <h1>Gerando documentação...</h1>

          <p className="hero-subtitle">{message}</p>

          <div
            style={{
              width: "min(420px, 80vw)",
              height: 8,
              borderRadius: 999,
              background: "rgba(255,255,255,0.15)",
              overflow: "hidden",
              margin: "1.5rem auto 0.75rem",
            }}
          >
            <div
              style={{
                width: `${Math.max(percent, 3)}%`,
                height: "100%",
                background: "#22c55e",
                transition: "width 400ms ease",
              }}
            />
          </div>

          <p className="hero-subtitle" style={{ opacity: 0.7 }}>
            {percent}%
          </p>

          <div className="loader"></div>
        </section>
      </main>
    </>
  );
}
