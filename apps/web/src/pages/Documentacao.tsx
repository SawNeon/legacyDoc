import Navbar from "../components/Navbar";
import "../styles/style.css";

export default function Documentacao() {
  return (
    <>
      <Navbar />

      <main id="conteudo" className="main-screen">
        <section className="hero">

          <h1>Gerando documentação...</h1>

          <p>
            Estamos analisando o repositório e estruturando a documentação.
          </p>

          <div className="loader"></div>

          <div className="steps-loading">
            <p>📥 Clonando repositório</p>
            <p>📂 Analisando arquivos</p>
            <p>📦 Identificando tecnologias</p>
            <p>🧠 Gerando documentação</p>
          </div>

        </section>
      </main>
    </>
  );
}