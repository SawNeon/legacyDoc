import type { BillingPlan, BillingSettings, UsageInfo } from "./api";

export type SettingKey = keyof BillingSettings;
export type PlanKey = "price_brl" | "credits_brl" | "cost_ratio";

export type FieldSpec<K extends string> = {
  key: K;
  label: string;
  unit: string;
  hint: string;
  scale?: number;
  list?: boolean;
  step: string;
};

export const SETTING_FIELDS: FieldSpec<SettingKey>[] = [
  {
    key: "fx_rate_brl_per_usd",
    label: "Câmbio de cálculo",
    unit: "R$ por US$",
    hint: "Converte o teto de custo (em dólar) para reais. Use um valor acima do câmbio real, como folga.",
    step: "0.01",
  },
  {
    key: "fees_tax_percent",
    label: "Taxas e imposto",
    unit: "% do preço",
    hint: "Parte do preço que some em taxa de pagamento e imposto antes de sobrar para você.",
    step: "0.1",
  },
  {
    key: "topup_credit_ratio",
    label: "Saldo por real pago na recarga",
    unit: "R$ de saldo por R$ 1",
    hint: "Abaixo do que a assinatura entrega, para a assinatura compensar mais.",
    step: "0.01",
  },
  {
    key: "topup_cost_ratio",
    label: "Parte do saldo da recarga que é custo real",
    unit: "% do saldo",
    hint: "Define o teto de custo real de cada recarga.",
    scale: 100,
    step: "1",
  },
  {
    key: "topup_validity_months",
    label: "Validade da recarga",
    unit: "meses",
    hint: "A assinatura zera todo mês; a recarga vale por este prazo.",
    step: "1",
  },
  {
    key: "topup_pack_prices_brl",
    label: "Pacotes de recarga",
    unit: "R$, separados por vírgula",
    hint: "Valores que o cliente pode comprar.",
    list: true,
    step: "any",
  },
  {
    key: "near_limit_percent",
    label: "Aviso de limite",
    unit: "% do saldo usado",
    hint: "A partir daqui o site e a extensão avisam que o saldo está acabando.",
    step: "1",
  },
  {
    key: "min_margin_alert_percent",
    label: "Alerta de margem mínima",
    unit: "% do preço",
    hint: "Um plano com margem no pior caso abaixo disto é marcado em alerta.",
    step: "1",
  },
  {
    key: "typical_usage_percent",
    label: "Uso típico do teto",
    unit: "% do teto",
    hint: "Só para estimar a margem típica: quanto do teto o cliente costuma gastar.",
    step: "1",
  },
];

export const PLAN_FIELDS: FieldSpec<PlanKey>[] = [
  { key: "price_brl", label: "Preço", unit: "R$ por mês", hint: "", step: "0.01" },
  {
    key: "credits_brl",
    label: "Saldo mostrado",
    unit: "R$",
    hint: "O que o cliente vê. Não é o custo real.",
    step: "0.01",
  },
  {
    key: "cost_ratio",
    label: "Parte do saldo que é custo real",
    unit: "% do saldo",
    hint: "Define o teto de custo em dólar.",
    scale: 100,
    step: "1",
  },
];

function trimNumber(value: number) {
  return String(Math.round(value * 10_000) / 10_000);
}

export function toInput(value: number | number[], spec: { scale?: number; list?: boolean }) {
  if (Array.isArray(value)) return value.map(trimNumber).join(", ");

  return trimNumber(value * (spec.scale ?? 1));
}

export function fromInput(
  text: string,
  spec: { scale?: number; list?: boolean }
): number | number[] | null {
  if (spec.list) {
    const parts = text
      .split(/[,;\s]+/)
      .map((part) => part.trim().replace(",", "."))
      .filter(Boolean);
    const numbers = parts.map(Number);

    return numbers.length > 0 && numbers.every(Number.isFinite) ? numbers : null;
  }

  const number = Number(text.trim().replace(",", "."));

  if (text.trim() === "" || !Number.isFinite(number)) return null;

  return number / (spec.scale ?? 1);
}

export function equalValues(a: number | number[], b: number | number[]) {
  if (Array.isArray(a) || Array.isArray(b)) {
    const left = (Array.isArray(a) ? a : [a]).map((n) => Math.round(n * 100) / 100);
    const right = (Array.isArray(b) ? b : [b]).map((n) => Math.round(n * 100) / 100);

    return left.length === right.length && left.every((n, i) => n === right[i]);
  }

  return Math.abs(a - b) < 1e-9;
}

export function changedFields<K extends string, V extends Record<K, number | number[]>>(
  specs: FieldSpec<K>[],
  current: V,
  inputs: Record<K, string>
): { changes: Partial<V>; invalid: K[] } {
  const changes: Record<string, number | number[]> = {};
  const invalid: K[] = [];

  for (const spec of specs) {
    const parsed = fromInput(inputs[spec.key] ?? "", spec);

    if (parsed === null) {
      invalid.push(spec.key);
      continue;
    }

    if (!equalValues(parsed, current[spec.key])) changes[spec.key] = parsed;
  }

  return { changes: changes as Partial<V>, invalid };
}

export function planValues(plan: BillingPlan): Record<PlanKey, number> {
  return {
    price_brl: plan.price_brl,
    credits_brl: plan.credits_brl,
    cost_ratio: plan.cost_ratio,
  };
}

export function formatBrl(value: number) {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function formatPercent(value: number | null) {
  return value === null ? "—" : `${value.toFixed(1).replace(".", ",")}%`;
}

export function balanceState(usage: Pick<UsageInfo, "exhausted" | "near_limit">) {
  if (usage.exhausted) return "esgotado";
  if (usage.near_limit) return "alerta";

  return "normal";
}
