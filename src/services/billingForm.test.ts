import { describe, expect, it } from "vitest";
import type { BillingSettings } from "./api";
import {
  balanceState,
  changedFields,
  equalValues,
  formatBrl,
  formatPercent,
  fromInput,
  PLAN_FIELDS,
  SETTING_FIELDS,
  toInput,
} from "./billingForm";

const RECOMMENDED: BillingSettings = {
  fx_rate_brl_per_usd: 6,
  fees_tax_percent: 10,
  topup_credit_ratio: 1,
  topup_cost_ratio: 0.55,
  topup_validity_months: 12,
  topup_pack_prices_brl: [30, 60, 100],
  near_limit_percent: 80,
  min_margin_alert_percent: 15,
  typical_usage_percent: 60,
};

function inputsOf(settings: BillingSettings) {
  return Object.fromEntries(
    SETTING_FIELDS.map((spec) => [spec.key, toInput(settings[spec.key], spec)])
  ) as Record<keyof BillingSettings, string>;
}

describe("toInput / fromInput", () => {
  it("mostra uma razao como porcentagem", () => {
    expect(toInput(0.55, { scale: 100 })).toBe("55");
  });

  it("devolve a porcentagem digitada como razao", () => {
    expect(fromInput("55", { scale: 100 })).toBeCloseTo(0.55);
  });

  it("aceita virgula decimal", () => {
    expect(fromInput("5,5", {})).toBe(5.5);
  });

  it("evita ruido de ponto flutuante na tela", () => {
    expect(toInput(0.1 + 0.2, {})).toBe("0.3");
    expect(toInput(0.57, { scale: 100 })).toBe("57");
  });

  it.each(["", "   ", "abc", "1,2,3x"])("recusa %j", (text) => {
    expect(fromInput(text, {})).toBeNull();
  });

  it("le uma lista de pacotes separada por virgula, ponto e virgula ou espaco", () => {
    expect(fromInput("30, 60; 100 150", { list: true })).toEqual([30, 60, 100, 150]);
  });

  it("recusa lista vazia ou com lixo", () => {
    expect(fromInput("", { list: true })).toBeNull();
    expect(fromInput("30, x", { list: true })).toBeNull();
  });

  it("mostra a lista como texto", () => {
    expect(toInput([30, 60, 100], { list: true })).toBe("30, 60, 100");
  });

  it("ida e volta preserva todos os campos de regras", () => {
    for (const spec of SETTING_FIELDS) {
      const text = toInput(RECOMMENDED[spec.key], spec);
      const back = fromInput(text, spec);

      expect(equalValues(back as number | number[], RECOMMENDED[spec.key])).toBe(true);
    }
  });
});

describe("equalValues", () => {
  it("compara numeros com tolerancia minima", () => {
    expect(equalValues(0.55, 0.55 + 1e-12)).toBe(true);
    expect(equalValues(0.55, 0.56)).toBe(false);
  });

  it("compara listas ignorando centavos de ruido", () => {
    expect(equalValues([30, 60], [30.001, 60])).toBe(true);
    expect(equalValues([30, 60], [30, 60, 100])).toBe(false);
  });
});

describe("changedFields", () => {
  it("nao propoe nada quando nada mudou", () => {
    const { changes, invalid } = changedFields(SETTING_FIELDS, RECOMMENDED, inputsOf(RECOMMENDED));

    expect(changes).toEqual({});
    expect(invalid).toEqual([]);
  });

  it("propoe so o campo alterado", () => {
    const inputs = { ...inputsOf(RECOMMENDED), fx_rate_brl_per_usd: "5,5" };

    expect(changedFields(SETTING_FIELDS, RECOMMENDED, inputs).changes).toEqual({
      fx_rate_brl_per_usd: 5.5,
    });
  });

  it("converte a porcentagem de volta para razao", () => {
    const inputs = { ...inputsOf(RECOMMENDED), topup_cost_ratio: "60" };

    expect(
      changedFields(SETTING_FIELDS, RECOMMENDED, inputs).changes.topup_cost_ratio
    ).toBeCloseTo(0.6);
  });

  it("aponta os campos invalidos em vez de enviar lixo", () => {
    const inputs = { ...inputsOf(RECOMMENDED), fees_tax_percent: "dez" };

    expect(changedFields(SETTING_FIELDS, RECOMMENDED, inputs).invalid).toEqual([
      "fees_tax_percent",
    ]);
  });

  it("funciona para os campos de plano", () => {
    const current = { price_brl: 100, credits_brl: 120, cost_ratio: 0.55 };
    const inputs = { price_brl: "150", credits_brl: "120", cost_ratio: "55" };

    expect(changedFields(PLAN_FIELDS, current, inputs).changes).toEqual({ price_brl: 150 });
  });

  it("detecta uma lista de pacotes alterada", () => {
    const inputs = { ...inputsOf(RECOMMENDED), topup_pack_prices_brl: "30, 60, 100, 200" };

    expect(changedFields(SETTING_FIELDS, RECOMMENDED, inputs).changes).toEqual({
      topup_pack_prices_brl: [30, 60, 100, 200],
    });
  });
});

describe("formatacao", () => {
  it("formata reais no padrao brasileiro", () => {
    expect(formatBrl(1234.5).replace(/\s/g, " ")).toBe("R$ 1.234,50");
  });

  it("formata porcentagem com virgula e trata ausencia", () => {
    expect(formatPercent(24)).toBe("24,0%");
    expect(formatPercent(null)).toBe("—");
  });
});

describe("balanceState", () => {
  it.each([
    [{ exhausted: false, near_limit: false }, "normal"],
    [{ exhausted: false, near_limit: true }, "alerta"],
    [{ exhausted: true, near_limit: true }, "esgotado"],
    [{ exhausted: true, near_limit: false }, "esgotado"],
  ])("%j vira %s", (usage, expected) => {
    expect(balanceState(usage)).toBe(expected);
  });
});
