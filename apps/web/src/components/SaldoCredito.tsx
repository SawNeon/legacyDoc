import { useEffect, useState } from "react";
import { getUsage, type UsageInfo } from "../services/api";
import { balanceState } from "../services/billingForm";

function reais(valor: number) {
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function data(iso: string) {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

export default function SaldoCredito() {
  const [uso, setUso] = useState<UsageInfo | null>(null);

  useEffect(() => {
    let ativo = true;

    getUsage()
      .then((resposta) => ativo && setUso(resposta))
      .catch(() => ativo && setUso(null));

    return () => {
      ativo = false;
    };
  }, []);

  if (!uso) return null;

  const estado = balanceState(uso);
  const usado = Math.round(uso.percent_used);

  return (
    <div className="saldo" data-estado={estado} role="status" aria-label="Saldo de créditos">
      <div className="saldo-topo">
        <span>Saldo</span>
        <strong className="mono">
          {reais(uso.credits_remaining_brl)}{" "}
          <small>de {reais(uso.credits_total_brl)}</small>
        </strong>
      </div>

      <div
        className="saldo-barra"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={usado}
        aria-label={`${usado}% do saldo usado`}
      >
        <div className="saldo-barra-cheia" style={{ width: `${Math.min(100, usado)}%` }} />
      </div>

      <p className="saldo-rodape">
        {uso.exhausted
          ? `Seus créditos acabaram. O saldo do plano renova em ${data(uso.renews_at)}.`
          : uso.near_limit
            ? `${usado}% do saldo usado. O do plano renova em ${data(uso.renews_at)}.`
            : `${usado}% usado · renova em ${data(uso.renews_at)}`}
        {uso.topups.length > 0 &&
          ` · inclui ${reais(uso.topups.reduce((soma, item) => soma + item.remaining_brl, 0))} de recarga`}
      </p>
    </div>
  );
}
