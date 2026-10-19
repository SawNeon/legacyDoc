import { useCallback, useEffect, useState } from "react";
import {
  getBilling,
  updateBillingSettings,
  updatePlanPricing,
  type BillingOverview,
} from "../services/api";
import {
  changedFields,
  equalValues,
  formatBrl,
  formatPercent,
  PLAN_FIELDS,
  planValues,
  SETTING_FIELDS,
  toInput,
  type FieldSpec,
  type PlanKey,
  type SettingKey,
} from "../services/billingForm";

const ROTULO_DE_PLANO: Record<string, string> = { free: "Free", pro: "Pro", team: "Team" };

const MOTIVO_MINIMO = 5;

type CampoProps<K extends string> = {
  spec: FieldSpec<K>;
  valor: string;
  atual: number | number[];
  recomendado: number | number[];
  aoMudar: (texto: string) => void;
  desabilitado: boolean;
};

function Campo<K extends string>({
  spec,
  valor,
  atual,
  recomendado,
  aoMudar,
  desabilitado,
}: CampoProps<K>) {
  const id = `preco-${spec.key}`;
  const textoRecomendado = toInput(recomendado, spec);
  const fora = !equalValues(atual, recomendado);

  return (
    <div className="preco-campo">
      <label htmlFor={id}>
        {spec.label}
        {fora && <span className="preco-fora">diferente do recomendado</span>}
      </label>

      <div className="preco-entrada">
        <input
          id={id}
          type="text"
          inputMode="decimal"
          value={valor}
          disabled={desabilitado}
          onChange={(evento) => aoMudar(evento.target.value)}
        />
        <span className="preco-unidade">{spec.unit}</span>
      </div>

      <div className="preco-recomendado">
        <span>
          Recomendado: <strong className="mono">{textoRecomendado}</strong>
        </span>

        {valor !== textoRecomendado && (
          <button
            type="button"
            className="preco-usar"
            disabled={desabilitado}
            onClick={() => aoMudar(textoRecomendado)}
          >
            Usar recomendado
          </button>
        )}
      </div>

      {spec.hint && <small className="admin-dica">{spec.hint}</small>}
    </div>
  );
}

export default function AdminPrecos({ aoMudar }: { aoMudar?: () => void }) {
  const [dados, setDados] = useState<BillingOverview | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [regras, setRegras] = useState<Record<SettingKey, string> | null>(null);
  const [planos, setPlanos] = useState<Record<string, Record<PlanKey, string>>>({});
  const [motivoRegras, setMotivoRegras] = useState("");
  const [motivoPlano, setMotivoPlano] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState<string | null>(null);

  const aplicar = useCallback((resposta: BillingOverview) => {
    setDados(resposta);
    setRegras(
      Object.fromEntries(
        SETTING_FIELDS.map((spec) => [spec.key, toInput(resposta.settings[spec.key], spec)])
      ) as Record<SettingKey, string>
    );
    setPlanos(
      Object.fromEntries(
        resposta.plans.map((plano) => [
          plano.tier,
          Object.fromEntries(
            PLAN_FIELDS.map((spec) => [spec.key, toInput(planValues(plano)[spec.key], spec)])
          ),
        ])
      ) as Record<string, Record<PlanKey, string>>
    );
  }, []);

  useEffect(() => {
    let ativo = true;

    getBilling()
      .then((resposta) => ativo && aplicar(resposta))
      .catch((falha: unknown) =>
        ativo &&
        setErro(falha instanceof Error ? falha.message : "Não foi possível carregar os preços.")
      );

    return () => {
      ativo = false;
    };
  }, [aplicar]);

  if (erro) return <p className="admin-erro">{erro}</p>;
  if (!dados || !regras) return <p className="hero-subtitle">Carregando preços...</p>;

  const mudancasRegras = changedFields(SETTING_FIELDS, dados.settings, regras);

  async function salvarRegras() {
    if (!dados) return;

    setSalvando("regras");

    try {
      aplicar(await updateBillingSettings(mudancasRegras.changes, motivoRegras.trim()));
      setMotivoRegras("");
      aoMudar?.();
    } catch (falha) {
      alert(falha instanceof Error ? falha.message : "Não foi possível salvar.");
    } finally {
      setSalvando(null);
    }
  }

  async function salvarPlano(tier: string) {
    const plano = dados?.plans.find((item) => item.tier === tier);

    if (!plano) return;

    const { changes } = changedFields(PLAN_FIELDS, planValues(plano), planos[tier]);

    setSalvando(tier);

    try {
      aplicar(await updatePlanPricing(tier, changes, (motivoPlano[tier] ?? "").trim()));
      setMotivoPlano((atuais) => ({ ...atuais, [tier]: "" }));
      aoMudar?.();
    } catch (falha) {
      alert(falha instanceof Error ? falha.message : "Não foi possível salvar.");
    } finally {
      setSalvando(null);
    }
  }

  const regrasMudaram = Object.keys(mudancasRegras.changes).length > 0;
  const regrasValidas = mudancasRegras.invalid.length === 0;
  const regrasProntas =
    regrasMudaram && regrasValidas && motivoRegras.trim().length >= MOTIVO_MINIMO;

  return (
    <section className="admin-precos" aria-labelledby="titulo-precos">
      <h2 id="titulo-precos">Preços e créditos</h2>

      <p className="hero-subtitle">
        Tudo que define quanto cada plano custa e quanto o cliente pode gastar. Ao lado de cada
        valor está o recomendado. Cada mudança fica registrada com o seu motivo.
      </p>

      <p className="preco-global">
        Gasto global do mês: <strong className="mono">US$ {dados.global_spend_usd.toFixed(2)}</strong>{" "}
        de <strong className="mono">US$ {dados.global_budget_usd.toFixed(2)}</strong> de orçamento.
      </p>

      <h3>Planos</h3>

      <div className="preco-planos">
        {dados.plans.map((plano) => {
          const textos = planos[plano.tier];
          const { changes, invalid } = changedFields(PLAN_FIELDS, planValues(plano), textos);
          const motivo = motivoPlano[plano.tier] ?? "";
          const pronto =
            Object.keys(changes).length > 0 &&
            invalid.length === 0 &&
            motivo.trim().length >= MOTIVO_MINIMO;

          return (
            <article
              className="preco-plano"
              key={plano.tier}
              data-alerta={plano.margin_alert ? "sim" : undefined}
            >
              <header>
                <h4>{ROTULO_DE_PLANO[plano.tier] ?? plano.tier}</h4>
                {plano.margin_alert && <span className="admin-marca perigo">margem baixa</span>}
              </header>

              {PLAN_FIELDS.map((spec) => (
                <Campo
                  key={spec.key}
                  spec={spec}
                  valor={textos[spec.key]}
                  atual={planValues(plano)[spec.key]}
                  recomendado={plano.recommended[spec.key]}
                  desabilitado={salvando !== null}
                  aoMudar={(texto) =>
                    setPlanos((atuais) => ({
                      ...atuais,
                      [plano.tier]: { ...atuais[plano.tier], [spec.key]: texto },
                    }))
                  }
                />
              ))}

              <dl className="preco-derivados">
                <div>
                  <dt>Teto de custo real</dt>
                  <dd className="mono">US$ {plano.ceiling_usd.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>Lucro no pior caso</dt>
                  <dd className="mono">{formatPercent(plano.worst_case_margin_percent)}</dd>
                </div>
                <div>
                  <dt>Lucro no uso típico</dt>
                  <dd className="mono">{formatPercent(plano.typical_margin_percent)}</dd>
                </div>
                <div>
                  <dt>Preço de lista</dt>
                  <dd className="mono">{formatBrl(plano.price_brl)}</dd>
                </div>
              </dl>

              <label htmlFor={`motivo-plano-${plano.tier}`} className="preco-motivo">
                Motivo da mudança
              </label>
              <input
                id={`motivo-plano-${plano.tier}`}
                type="text"
                value={motivo}
                placeholder="Ex: ajuste depois de medir o custo real"
                onChange={(evento) =>
                  setMotivoPlano((atuais) => ({ ...atuais, [plano.tier]: evento.target.value }))
                }
              />

              <button
                type="button"
                className="btn"
                disabled={!pronto || salvando !== null}
                onClick={() => salvarPlano(plano.tier)}
              >
                {salvando === plano.tier ? "Salvando..." : "Salvar plano"}
              </button>
            </article>
          );
        })}
      </div>

      <h3>Regras gerais</h3>

      <div className="preco-regras">
        {SETTING_FIELDS.map((spec) => (
          <Campo
            key={spec.key}
            spec={spec}
            valor={regras[spec.key]}
            atual={dados.settings[spec.key]}
            recomendado={dados.recommended_settings[spec.key]}
            desabilitado={salvando !== null}
            aoMudar={(texto) => setRegras((atuais) => ({ ...atuais!, [spec.key]: texto }))}
          />
        ))}
      </div>

      {!regrasValidas && (
        <p className="admin-dica">Há valores inválidos. Use só números.</p>
      )}

      <div className="preco-salvar">
        <label htmlFor="motivo-regras">Motivo da mudança</label>
        <input
          id="motivo-regras"
          type="text"
          value={motivoRegras}
          placeholder="Ex: o dólar subiu, reajustando o câmbio de cálculo"
          onChange={(evento) => setMotivoRegras(evento.target.value)}
        />

        <button
          type="button"
          className="btn"
          disabled={!regrasProntas || salvando !== null}
          onClick={salvarRegras}
        >
          {salvando === "regras" ? "Salvando..." : "Salvar regras gerais"}
        </button>
      </div>
    </section>
  );
}
