import Navbar from "../components/Navbar";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register, setAuthToken } from "../services/api";

export default function CriarConta() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");

    if (!name.trim() || !email.trim() || !password) {
      setError("Preencha nome, email e senha.");
      return;
    }

    if (password !== confirmPassword) {
      setError("As senhas nao conferem.");
      return;
    }

    try {
      setLoading(true);
      const response = await register(email.trim(), password);
      setAuthToken(response.access_token);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nao foi possivel criar a conta.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Navbar />

      <main id="conteudo" className="main-screen">
        <section className="hero">
          <span className="badge">Cadastro</span>

          <h1>Criar sua conta</h1>

          <p className="hero-subtitle">
            Comece a usar a plataforma para gerar documentacoes automaticas com
            inteligencia artificial.
          </p>

          <form className="form-box" onSubmit={handleSubmit}>
            <input
              type="text"
              placeholder="Nome completo"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <input
              type="password"
              placeholder="Senha"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <input
              type="password"
              placeholder="Confirmar senha"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />

            {error && <p className="form-error">{error}</p>}

            <button disabled={loading}>
              {loading ? "Criando conta..." : "Criar conta"}
            </button>
          </form>

          <Link to="/login" className="link">
            Ja tem uma conta? Entrar
          </Link>
        </section>
      </main>
    </>
  );
}
