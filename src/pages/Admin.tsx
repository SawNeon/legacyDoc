import AdminPrecos from "../components/AdminPrecos";
import Navbar from "../components/Navbar";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  changeAccountPlan,
  changeAccountStatus,
  getAuthToken,
  grantCredits,
  listAccounts,
  listAudit,
  type AdminAccount,
  type AdminAction,
} from "../services/api";

const PLANOS = ["free", "pro", "team"] as const;

const ROTULO_DE_PLANO: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  team: "Team",
};

const ROTULO_DE_ACAO: Record<string, string> = {
  plan_changed: "Plano alterado",
  account_enabled: "Conta reativada",
  account_disabled: "Conta desativada",
  billing_setting_changed: "Regra de cobrança alterada",
  plan_pricing_changed: "Preço do plano alterado",
  credit_granted: "Crédito adicionado",
};

const MOTIVO_MINIMO = 5;

type Aba = "contas" | "precos";

function formatarReais(valor: number) {
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatarData(iso: string | null) {
  if (!iso) return "—";

  const data = new Date(iso);
  return Number.isNaN(data.valueOf()) ? iso : data.toLocaleString("pt-BR");
}

function consumo(conta: AdminAccount) {
  if (conta.cost_limit_usd <= 0) return 0;

  return Math.min(100, (conta.spent_this_month_usd / conta.cost_limit_usd) * 100);
}

export default function Admin() {
  const navigate = useNavigate();

  const [contas, setContas] = useState<AdminAccount[]>([]);
  const [registros, setRegistros] = useState<AdminAction[]>([]);
  const [busca, setBusca] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const [editando, setEditando] = useState<string | null>(null);
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [aba, setAba] = useState<Aba>("contas");
  const [tipoCredito, setTipoCredito] = useState<"pago" | "cortesia">("pago");
  const [valorCredito, setValorCredito] = useState("");

  const buscar = useCallback(
    (
      termo: string,
      aplicar: (
        contas: AdminAccount[] | null,
        registros: AdminAction[] | null,
        falha: string | null
      ) => void
    ) => {
      if (!getAuthToken()) {
        navigate("/login", { viewTransition: true });
        return;
      }

      Promise.all([listAccounts(termo), listAudit(30)])
        .then(([lista, historico]) => aplicar(lista.items, historico, null))
        .catch((falha: unknown) =>
          aplicar(
            null,
            null,
            falha instanceof Error ? falha.message : "Não foi possível carregar o painel."
          )
        );
    },
    [navigate]
  );

  useEffect(() => {
    let ativo = true;

    buscar("", (lista, historico, falha) => {
      if (!ativo) return;

      if (lista) setContas(lista);
      if (historico) setRegistros(historico);
      setErro(falha);
      setCarregando(false);
    });

    return () => {
      ativo = false;
    };
  }, [buscar]);

  function recarregar(termo = busca) {
    setCarregando(true);

    buscar(termo, (lista, historico, falha) => {
      if (lista) setContas(lista);
      if (historico) setRegistros(historico);
      setErro(falha);
      setCarregando(false);
    });
  }

  function abrirEdicao(conta: AdminAccount) {
    setEditando(editando === conta.id ? null : conta.id);
    setMotivo("");
  }

  async function aplicar(acao: () => Promise<AdminAccount>) {
    setSalvando(true);

    try {
      await acao();
      setEditando(null);
      setMotivo("");
      recarregar();
    } catch (falha) {
      alert(falha instanceof Error ? falha.message : "Não foi possível aplicar a mudança.");
    } finally {
      setSalvando(false);
    }
  }

  const motivoValido = motivo.trim().length >= MOTIVO_MINIMO;
  const valorNumerico = Number(valorCredito.replace(",", "."));
  const creditoValido = Number.isFinite(valorNumerico) && valorNumerico > 0;

  const semAcesso = erro?.includes("nao encontrado") || erro?.includes("não encontrado");

  if (semAcesso) {
    return (
      <>
        <Navbar />

        <main id="conteudo" className="main-screen">
          <section className="hero">
            <span className="badge">Restrito</span>
            <h1>Esta área não está disponível</h1>
            <p className="hero-subtitle">
              Sua conta não tem acesso ao painel de contas.
            </p>
            <button className="btn" onClick={() => navigate("/", { viewTransition: true })}>
              Voltar ao início
            </button>
          </section>
        </main>
      </>
    );
  }

  return (
    <>
      <Navbar />

      <main id="conteudo" className="main-screen">
        <section className="hero admin-hero">
          <span className="badge">Painel</span>

          <h1>Contas</h1>

          <p className="hero-subtitle">
            Quem está usando, quanto já consumiu do teto e em que plano está.
          </p>

          <div className="admin-abas" role="tablist" aria-label="Seções do painel">
            {(["contas", "precos"] as const).map((item) => (
              <button
                key={item}
                type="button"
                role="tab"
                aria-selected={aba === item}
                className="admin-aba"
                onClick={() => setAba(item)}
              >
                {item === "contas" ? "Contas" : "Preços e créditos"}
              </button>
            ))}
          </div>

          {aba === "precos" && <AdminPrecos aoMudar={() => recarregar()} />}

          <form
            hidden={aba !== "contas"}
            className="admin-busca"
            onSubmit={(evento) => {
              evento.preventDefault();
              recarregar();
            }}
          >
            <label htmlFor="busca" className="sr-only">
              Buscar por e-mail
            </label>

            <input
              id="busca"
              type="search"
              placeholder="Buscar por e-mail"
              value={busca}
              onChange={(evento) => setBusca(evento.target.value)}
            />

            <button className="btn" type="submit" disabled={carregando}>
              {carregando ? "Carregando..." : "Buscar"}
            </button>
          </form>

          {erro && <p className="admin-erro">{erro}</p>}

          <div className="admin-lista" hidden={aba !== "contas"}>
            {!carregando && contas.length === 0 && (
              <p className="hero-subtitle">Nenhuma conta encontrada.</p>
            )}

            {contas.map((conta) => {
              const aberto = editando === conta.id;
              const perto = consumo(conta) >= 80;

              return (
                <article
                  className="admin-conta"
                  key={conta.id}
                  data-inativa={conta.is_active ? undefined : "sim"}
                >
                  <div className="admin-conta-topo">
                    <div className="admin-identidade">
                      <strong className="mono">{conta.email}</strong>

                      <div className="admin-marcas">
                        <span className={`admin-plano plano-${conta.plan_tier}`}>
                          {ROTULO_DE_PLANO[conta.plan_tier] ?? conta.plan_tier}
                        </span>

                        {conta.is_admin && <span className="admin-marca">admin</span>}

                        {!conta.is_active && (
                          <span className="admin-marca perigo">desativada</span>
                        )}

                        {conta.locked_until && (
                          <span className="admin-marca alerta">bloqueada por tentativas</span>
                        )}
                      </div>
                    </div>

                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => abrirEdicao(conta)}
                    >
                      {aberto ? "Fechar" : "Gerenciar"}
                    </button>
                  </div>

                  <div className="admin-metricas">
                    <div>
                      <span>Consumo do mês</span>
                      <strong className="mono">
                        US$ {conta.spent_this_month_usd.toFixed(4)} de{" "}
                        {conta.cost_limit_usd.toFixed(2)}
                      </strong>

                      <div
                        className="admin-barra"
                        role="img"
                        aria-label={`${consumo(conta).toFixed(0)}% do teto consumido`}
                      >
                        <div
                          className="admin-barra-cheia"
                          data-alto={perto ? "sim" : undefined}
                          style={{ width: `${Math.max(consumo(conta), 1)}%` }}
                        />
                      </div>
                    </div>

                    <div>
                      <span>Saldo do cliente</span>
                      <strong className="mono">{formatarReais(conta.credits_remaining_brl)}</strong>
                    </div>

                    <div>
                      <span>Análises no mês</span>
                      <strong className="mono">{conta.jobs_this_month}</strong>
                    </div>

                    <div>
                      <span>Documentos no total</span>
                      <strong className="mono">{conta.documents_total}</strong>
                    </div>

                    <div>
                      <span>Última análise</span>
                      <strong>{formatarData(conta.last_job_at)}</strong>
                    </div>
                  </div>

                  {aberto && (
                    <div className="admin-edicao">
                      <label htmlFor={`motivo-${conta.id}`}>
                        Motivo da mudança
                        <span className="admin-dica">
                          Fica registrado com seu e-mail. É o que explica, daqui a três
                          meses, por que esta conta está neste plano.
                        </span>
                      </label>

                      <input
                        id={`motivo-${conta.id}`}
                        type="text"
                        value={motivo}
                        onChange={(evento) => setMotivo(evento.target.value)}
                        placeholder="Ex: liberado para a banca avaliar o nível completo"
                      />

                      <div className="admin-acoes">
                        {PLANOS.filter((plano) => plano !== conta.plan_tier).map((plano) => (
                          <button
                            key={plano}
                            type="button"
                            className="btn"
                            disabled={!motivoValido || salvando}
                            onClick={() =>
                              aplicar(() => changeAccountPlan(conta.id, plano, motivo))
                            }
                          >
                            Mudar para {ROTULO_DE_PLANO[plano]}
                          </button>
                        ))}

                        <button
                          type="button"
                          className="btn btn-secondary"
                          disabled={!motivoValido || salvando}
                          onClick={() =>
                            aplicar(() =>
                              changeAccountStatus(conta.id, !conta.is_active, motivo)
                            )
                          }
                        >
                          {conta.is_active ? "Desativar conta" : "Reativar conta"}
                        </button>
                      </div>

                      <fieldset className="admin-credito">
                        <legend>Adicionar crédito</legend>

                        <div className="admin-acoes">
                          <select
                            aria-label="Tipo de crédito"
                            value={tipoCredito}
                            onChange={(evento) =>
                              setTipoCredito(evento.target.value as "pago" | "cortesia")
                            }
                          >
                            <option value="pago">Recarga paga (valor pago em R$)</option>
                            <option value="cortesia">Cortesia (saldo em R$)</option>
                          </select>

                          <input
                            aria-label="Valor em reais"
                            inputMode="decimal"
                            placeholder="Ex: 60"
                            value={valorCredito}
                            onChange={(evento) => setValorCredito(evento.target.value)}
                          />

                          <button
                            type="button"
                            className="btn"
                            disabled={!motivoValido || !creditoValido || salvando}
                            onClick={() =>
                              aplicar(async () => {
                                const resposta = await grantCredits(
                                  conta.id,
                                  tipoCredito === "pago"
                                    ? { price_brl: valorNumerico }
                                    : { credits_brl: valorNumerico },
                                  motivo
                                );
                                setValorCredito("");
                                return resposta.account;
                              })
                            }
                          >
                            Adicionar
                          </button>
                        </div>

                        <small className="admin-dica">
                          Usa o mesmo motivo escrito acima. A recarga paga vira saldo pela razão
                          configurada em Preços e créditos.
                        </small>
                      </fieldset>

                      {!motivoValido && motivo.length > 0 && (
                        <p className="admin-dica">
                          Escreva pelo menos {MOTIVO_MINIMO} caracteres.
                        </p>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </div>

          <div className="admin-auditoria">
            <h2>Últimas ações</h2>

            {registros.length === 0 ? (
              <p className="hero-subtitle">Nenhuma ação registrada ainda.</p>
            ) : (
              <ol>
                {registros.map((registro) => (
                  <li key={registro.id}>
                    <strong>{ROTULO_DE_ACAO[registro.action] ?? registro.action}</strong>{" "}
                    <span className="mono">{registro.target_email}</span>

                    {registro.value_before && registro.value_after && (
                      <span className="mono admin-transicao">
                        {registro.value_before} → {registro.value_after}
                      </span>
                    )}

                    <span className="admin-dica">
                      {formatarData(registro.created_at)} por{" "}
                      <span className="mono">{registro.actor_email}</span>
                    </span>

                    <p>{registro.reason}</p>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
