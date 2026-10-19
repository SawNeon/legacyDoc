import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearAuthToken,
  clearLocalSession,
  deleteJobRecord,
  documentToResult,
  followJob,
  getAuthToken,
  getJob,
  listJobs,
  setAuthToken,
  type DocumentDetail,
  type DocumentSummary,
  type Job,
} from "./api";

class MemoriaLocal {
  private dados = new Map<string, string>();

  getItem(chave: string) {
    return this.dados.get(chave) ?? null;
  }

  setItem(chave: string, valor: string) {
    this.dados.set(chave, valor);
  }

  removeItem(chave: string) {
    this.dados.delete(chave);
  }
}

function resposta(status: number, corpo?: unknown, tipo = "application/json") {
  return new Response(corpo === undefined ? null : JSON.stringify(corpo), {
    status,
    headers: { "content-type": tipo },
  });
}

function job(parcial: Partial<Job> = {}): Job {
  return {
    id: "j1",
    job_type: "document_repository",
    status: "queued",
    progress_percent: 0,
    progress_message: null,
    attempts: 0,
    created_at: "2026-01-01T00:00:00Z",
    document_count: 0,
    depth: "basic",
    source: null,
    ...parcial,
  } as Job;
}

let fetchSimulado: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.stubGlobal("localStorage", new MemoriaLocal());
  vi.stubGlobal("window", { dispatchEvent: vi.fn() });
  vi.stubGlobal("Event", class {});
  fetchSimulado = vi.fn();
  vi.stubGlobal("fetch", fetchSimulado);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("deleteJobRecord", () => {
  it("chama DELETE em /record com o token e resolve no 204 de corpo vazio", async () => {
    setAuthToken("tok");
    fetchSimulado.mockResolvedValue(
      new Response(null, { status: 204, headers: { "content-type": "application/json" } })
    );

    await expect(deleteJobRecord("abc")).resolves.toBeUndefined();

    const [url, opcoes] = fetchSimulado.mock.calls[0];
    expect(url).toMatch(/\/v1\/jobs\/abc\/record$/);
    expect(opcoes.method).toBe("DELETE");
    expect(opcoes.headers.Authorization).toBe("Bearer tok");
  });

  it("mostra a mensagem da API quando o job ja esta em andamento (409)", async () => {
    fetchSimulado.mockResolvedValue(
      resposta(409, { error: "conflict", message: "A analise ainda esta em andamento." })
    );

    await expect(deleteJobRecord("abc")).rejects.toThrow("A analise ainda esta em andamento.");
  });

  it("trata 404 como erro com a mensagem da API", async () => {
    fetchSimulado.mockResolvedValue(resposta(404, { message: "Job nao encontrado." }));

    await expect(deleteJobRecord("abc")).rejects.toThrow("Job nao encontrado.");
  });

  it("encerra a sessao local ao receber 401", async () => {
    setAuthToken("tok");
    fetchSimulado.mockResolvedValue(resposta(401, { message: "Credencial ausente." }));

    await expect(deleteJobRecord("abc")).rejects.toThrow("Credencial ausente.");
    expect(getAuthToken()).toBeNull();
  });

  it("propaga a falha de rede sem engolir", async () => {
    fetchSimulado.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(deleteJobRecord("abc")).rejects.toThrow("Failed to fetch");
  });
});

describe("sessao e historico por conta", () => {
  it("trocar de token apaga o resultado e o historico da conta anterior", () => {
    setAuthToken("a");
    localStorage.setItem("legacyDocResult", "{}");
    localStorage.setItem("legacyDocHistory", "[]");
    localStorage.setItem("pendingJobId", "j");

    setAuthToken("b");

    expect(localStorage.getItem("legacyDocResult")).toBeNull();
    expect(localStorage.getItem("legacyDocHistory")).toBeNull();
    expect(localStorage.getItem("pendingJobId")).toBeNull();
    expect(getAuthToken()).toBe("b");
  });

  it("sair apaga o token e o estado local", () => {
    setAuthToken("a");
    localStorage.setItem("repoUrl", "https://github.com/x/y");

    clearAuthToken();

    expect(getAuthToken()).toBeNull();
    expect(localStorage.getItem("repoUrl")).toBeNull();
  });

  it("clearLocalSession nao apaga o token", () => {
    localStorage.setItem("legacyDocToken", "t");
    localStorage.setItem("repoDepth", "pro");

    clearLocalSession();

    expect(localStorage.getItem("legacyDocToken")).toBe("t");
    expect(localStorage.getItem("repoDepth")).toBeNull();
  });
});

describe("leitura da API", () => {
  it("getJob envia o token e devolve o job", async () => {
    setAuthToken("tok");
    fetchSimulado.mockResolvedValue(resposta(200, job({ status: "running" })));

    const resultado = await getJob("j1");

    expect(resultado.status).toBe("running");
    expect(fetchSimulado.mock.calls[0][1].headers.Authorization).toBe("Bearer tok");
  });

  it("listJobs respeita o limite pedido", async () => {
    fetchSimulado.mockResolvedValue(resposta(200, { items: [], total: 0 }));

    await listJobs(10);

    expect(fetchSimulado.mock.calls[0][0]).toMatch(/\/v1\/jobs\?limit=10$/);
  });

  it("usa a mensagem de texto puro quando a API nao devolve JSON", async () => {
    fetchSimulado.mockResolvedValue(
      new Response("Bad gateway", { status: 502, headers: { "content-type": "text/plain" } })
    );

    await expect(getJob("j1")).rejects.toThrow("Bad gateway");
  });

  it("cai numa mensagem generica quando o erro nao traz texto", async () => {
    fetchSimulado.mockResolvedValue(resposta(500, {}));

    await expect(getJob("j1")).rejects.toThrow("Erro na API");
  });
});

describe("followJob", () => {
  const resumo = {
    id: "d1",
    job_id: "j1",
    path: "a.py",
    language: "python",
    summary: "Resumo",
    symbol_count: 1,
    finding_count: 0,
    depth: "basic",
    created_at: "2026-01-01T00:00:00Z",
  } as DocumentSummary;

  const detalhe = {
    id: "d1",
    job_id: "j1",
    path: "a.py",
    language: "python",
    summary: "Resumo",
    symbols: [
      {
        name: "metodo",
        parent: "Classe",
        kind: "method",
        signature: "def metodo(self, x)",
        language: "python",
        line_start: 1,
        line_end: 2,
        summary: "s",
        description: "d",
        parameters: [
          { name: "x", type: null, description: "", optional: false, default: null },
        ],
        return_type: null,
        raises: [],
        side_effects: [],
      },
    ],
    findings: [],
    findings_locked: true,
    depth: "standard",
    created_at: "2026-01-01T00:00:00Z",
  } as unknown as DocumentDetail;

  it("acompanha ate concluir e monta o resultado", async () => {
    vi.useFakeTimers();

    fetchSimulado
      .mockResolvedValueOnce(resposta(200, job({ status: "running", progress_percent: 40 })))
      .mockResolvedValueOnce(resposta(200, job({ status: "succeeded", document_count: 1 })))
      .mockResolvedValueOnce(resposta(200, [resumo]))
      .mockResolvedValueOnce(resposta(200, detalhe));

    const progresso: number[] = [];
    const promessa = followJob("j1", (j) => progresso.push(j.progress_percent));

    await vi.runAllTimersAsync();
    const resultado = await promessa;

    expect(progresso).toEqual([40, 0]);
    expect(resultado.file).toBe("a.py");
    expect(resultado.findings_locked).toBe(true);
    expect(resultado.depth).toBe("standard");
    expect(resultado.documentation![0].name).toBe("Classe.metodo");
    expect(resultado.documentation![0].args).toEqual([{ name: "x", type: "?" }]);
  });

  it("usa a mensagem do servidor quando o job falha", async () => {
    fetchSimulado.mockResolvedValue(
      resposta(200, job({ status: "failed", error_message: "Repositorio inexistente." }))
    );

    await expect(followJob("j1")).rejects.toThrow("Repositorio inexistente.");
  });

  it("explica quando o job termina sem nenhum documento", async () => {
    fetchSimulado
      .mockResolvedValueOnce(resposta(200, job({ status: "succeeded" })))
      .mockResolvedValueOnce(resposta(200, []));

    await expect(followJob("j1")).rejects.toThrow(/Nenhum arquivo suportado/);
  });

  it("desiste depois do tempo maximo de espera", async () => {
    vi.useFakeTimers();
    fetchSimulado.mockImplementation(async () => resposta(200, job({ status: "running" })));

    const promessa = followJob("j1");
    const falha = expect(promessa).rejects.toThrow(/passou do tempo previsto/);

    await vi.advanceTimersByTimeAsync(16 * 60 * 1000);
    await falha;
  });
});

describe("documentToResult", () => {
  it("mantem o nome simples quando o simbolo nao tem classe-mae", () => {
    const detalhe = {
      path: "a.py",
      summary: null,
      symbols: [
        {
          name: "f",
          parent: null,
          kind: "function",
          signature: "def f()",
          parameters: [],
          return_type: "int",
          raises: [],
          summary: "",
          description: "",
        },
      ],
      findings: [],
      findings_locked: false,
      depth: "basic",
    } as unknown as DocumentDetail;

    const resultado = documentToResult(detalhe, []);

    expect(resultado.documentation![0].name).toBe("f");
    expect(resultado.documentation![0].return_type).toBe("int");
    expect(resultado.summary).toBeUndefined();
  });
});
