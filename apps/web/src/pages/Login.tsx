import Navbar from "../components/Navbar";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login, setAuthToken } from "../services/api";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");

    if (!email.trim() || !password) {
      setError("Informe email e senha.");
      return;
    }

    try {
      setLoading(true);
      const response = await login(email.trim(), password);
      setAuthToken(response.access_token);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nao foi possivel entrar.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Navbar />

      <main id="conteudo" className="main-screen">
        <section className="hero">
          <h1>Entrar</h1>
          <p className="hero-subtitle">Acesse sua conta para continuar</p>

          <form className="form-box" onSubmit={handleSubmit}>
            <input
              type="email"
              placeholder="Seu email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <input
              type="password"
              placeholder="Sua senha"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />

            {error && <p className="form-error">{error}</p>}

            <button disabled={loading}>{loading ? "Entrando..." : "Entrar"}</button>
          </form>

          <Link to="/criar-conta" className="link">
            Criar conta
          </Link>

          <Link to="/troca-senha" className="link">
            Esqueci minha senha
          </Link>
        </section>
      </main>
    </>
  );
}
