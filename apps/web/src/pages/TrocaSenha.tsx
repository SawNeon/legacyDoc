import Navbar from "../components/Navbar";
import { Link } from "react-router-dom";
import { useState } from "react";
import type { FormEvent } from "react";
import { requestPasswordReset } from "../services/api";

export default function TrocaSenha() {
  const [email, setEmail] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setErro("");

    if (!email.trim()) {
      setErro("Informe seu e-mail.");
      return;
    }

    try {
      setCarregando(true);
      await requestPasswordReset(email.trim());
      setEnviado(true);
    } catch (err) {
      setErro(
        err instanceof Error
          ? err.message
          : "Nao foi possivel enviar o link. Tente novamente."
      );
    } finally {
      setCarregando(false);
    }
  }

  if (enviado) {
    return (
      <>
        <Navbar />

        <main id="conteudo" className="main-screen">
          <section className="hero">
            <span className="badge">Recuperação de acesso</span>

            <h1>Verifique seu e-mail</h1>

            <p className="hero-subtitle">
              Se houver uma conta com <strong>{email.trim()}</strong>, enviamos um
              link para redefinir a senha. Ele vale por 30 minutos e só pode ser
              usado uma vez.
            </p>

            <p className="hero-subtitle">
              Não recebeu? Confira a caixa de spam ou{" "}
              <button
                type="button"
                className="nav-link-button"
                onClick={() => setEnviado(false)}
              >
                tente outro e-mail
              </button>
              .
            </p>

            <Link to="/login" className="link">
              Voltar para login
            </Link>
          </section>
        </main>
      </>
    );
  }

  return (
    <>
      <Navbar />

      <main id="conteudo" className="main-screen">
        <section className="hero">
          <span className="badge">Recuperação de acesso</span>

          <h1>Esqueceu sua senha?</h1>

          <p className="hero-subtitle">
            Informe seu e-mail e enviaremos um link para você criar uma nova senha.
          </p>

          <form className="form-box" onSubmit={handleSubmit}>
            <input
              type="email"
              placeholder="Seu email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
            />

            {erro && <p className="form-error">{erro}</p>}

            <button disabled={carregando}>
              {carregando ? "Enviando..." : "Enviar link"}
            </button>
          </form>

          <Link to="/login" className="link">
            Voltar para login
          </Link>
        </section>
      </main>
    </>
  );
}
