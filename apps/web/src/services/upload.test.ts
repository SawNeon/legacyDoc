import { unzipSync, strFromU8 } from "fflate";
import { describe, expect, it } from "vitest";
import {
  formatarTamanho,
  MAX_ENTRIES,
  MAX_UPLOAD_BYTES,
  prepareFromFolder,
  prepareFromZip,
  UploadError,
} from "./upload";

const EXTENSOES = new Set([".py", ".ts", ".java"]);

function arquivoDaPasta(caminho: string, conteudo = "x = 1\n", tamanho?: number) {
  const arquivo = new File([tamanho ? "a".repeat(tamanho) : conteudo], caminho.split("/").pop()!);

  Object.defineProperty(arquivo, "webkitRelativePath", { value: caminho });

  return arquivo;
}

async function lerZip(arquivo: File) {
  return unzipSync(new Uint8Array(await arquivo.arrayBuffer()));
}

describe("prepareFromFolder", () => {
  it("envia o caminho sem o nome da pasta escolhida", async () => {
    const resultado = await prepareFromFolder(
      [arquivoDaPasta("meu-projeto/src/app.py", "def f(): pass")],
      EXTENSOES
    );

    const conteudo = await lerZip(resultado.file);

    expect(Object.keys(conteudo)).toEqual(["src/app.py"]);
    expect(strFromU8(conteudo["src/app.py"])).toBe("def f(): pass");
    expect(resultado.label).toBe("meu-projeto");
    expect(resultado.file.name).toBe("meu-projeto.zip");
    expect(resultado.includedFiles).toBe(1);
  });

  it("deixa de fora pastas de dependencia e ocultas, em qualquer nivel", async () => {
    const resultado = await prepareFromFolder(
      [
        arquivoDaPasta("p/src/app.py"),
        arquivoDaPasta("p/node_modules/lib/index.ts"),
        arquivoDaPasta("p/web/node_modules/x/y.ts"),
        arquivoDaPasta("p/.git/hooks/pre.py"),
        arquivoDaPasta("p/.venv/lib/site.py"),
        arquivoDaPasta("p/dist/bundle.ts"),
        arquivoDaPasta("p/Build/out.ts"),
      ],
      EXTENSOES
    );

    expect(Object.keys(await lerZip(resultado.file))).toEqual(["src/app.py"]);
    expect(resultado.skipped.ignoredFolders).toBe(6);
  });

  it("ignora extensoes que o servidor nao documenta", async () => {
    const resultado = await prepareFromFolder(
      [arquivoDaPasta("p/a.py"), arquivoDaPasta("p/logo.png"), arquivoDaPasta("p/README.md")],
      EXTENSOES
    );

    expect(resultado.includedFiles).toBe(1);
    expect(resultado.skipped.unsupported).toBe(2);
  });

  it("reconhece a extensao sem diferenciar maiusculas", async () => {
    const resultado = await prepareFromFolder([arquivoDaPasta("p/Main.JAVA")], EXTENSOES);

    expect(resultado.includedFiles).toBe(1);
  });

  it("descarta arquivos gerados e minificados", async () => {
    const resultado = await prepareFromFolder(
      [
        arquivoDaPasta("p/a.ts"),
        arquivoDaPasta("p/b.generated.ts"),
        arquivoDaPasta("p/c_pb2.py"),
      ],
      EXTENSOES
    );

    expect(resultado.includedFiles).toBe(1);
    expect(resultado.skipped.generated).toBe(2);
  });

  it("descarta arquivo acima de 512 KB e mantem o de exatamente 512 KB", async () => {
    const resultado = await prepareFromFolder(
      [
        arquivoDaPasta("p/ok.py", "", 512 * 1024),
        arquivoDaPasta("p/grande.py", "", 512 * 1024 + 1),
      ],
      EXTENSOES
    );

    expect(resultado.includedFiles).toBe(1);
    expect(resultado.skipped.tooLarge).toBe(1);
  });

  it("recusa a pasta sem nenhum codigo suportado, com mensagem para a pessoa", async () => {
    await expect(
      prepareFromFolder([arquivoDaPasta("p/foto.png"), arquivoDaPasta("p/.git/a.py")], EXTENSOES)
    ).rejects.toThrow(/Nenhum arquivo de código suportado/);
  });

  it("recusa uma lista vazia", async () => {
    await expect(prepareFromFolder([], EXTENSOES)).rejects.toBeInstanceOf(UploadError);
  });

  it("corta no limite de entradas e avisa que truncou", async () => {
    const arquivos = Array.from({ length: MAX_ENTRIES + 3 }, (_, i) =>
      arquivoDaPasta(`p/src/m${i}.py`, `v = ${i}\n`)
    );

    const resultado = await prepareFromFolder(arquivos, EXTENSOES);

    expect(resultado.truncated).toBe(true);
    expect(resultado.includedFiles).toBe(MAX_ENTRIES);
  });

  it("nao marca truncado quando cabe no limite", async () => {
    const resultado = await prepareFromFolder([arquivoDaPasta("p/a.py")], EXTENSOES);

    expect(resultado.truncated).toBe(false);
  });

  it("preserva o conteudo em UTF-8", async () => {
    const resultado = await prepareFromFolder(
      [arquivoDaPasta("p/acao.py", "# validação de ação\n")],
      EXTENSOES
    );

    expect(strFromU8((await lerZip(resultado.file))["acao.py"])).toBe("# validação de ação\n");
  });

  it("gera um zip que o servidor reconhece pela assinatura PK", async () => {
    const resultado = await prepareFromFolder([arquivoDaPasta("p/a.py")], EXTENSOES);
    const inicio = new Uint8Array(await resultado.file.slice(0, 2).arrayBuffer());

    expect([inicio[0], inicio[1]]).toEqual([0x50, 0x4b]);
    expect(resultado.file.type).toBe("application/zip");
  });
});

describe("prepareFromZip", () => {
  const zipValido = () => new File([new Uint8Array([0x50, 0x4b, 3, 4, 0, 0])], "projeto.zip");

  it("aceita um zip de verdade", async () => {
    const resultado = await prepareFromZip(zipValido());

    expect(resultado.label).toBe("projeto.zip");
    expect(resultado.includedFiles).toBeNull();
  });

  it("aceita a extensao em maiusculas", async () => {
    const arquivo = new File([new Uint8Array([0x50, 0x4b, 3, 4])], "PROJETO.ZIP");

    await expect(prepareFromZip(arquivo)).resolves.toBeDefined();
  });

  it.each([
    ["projeto.rar", "Envie um arquivo .zip."],
    ["projeto.tar.gz", "Envie um arquivo .zip."],
  ])("recusa %s", async (nome, mensagem) => {
    await expect(prepareFromZip(new File(["PK"], nome))).rejects.toThrow(mensagem);
  });

  it("recusa arquivo vazio", async () => {
    await expect(prepareFromZip(new File([], "vazio.zip"))).rejects.toThrow("O arquivo está vazio.");
  });

  it("recusa texto com extensao .zip pela assinatura", async () => {
    await expect(
      prepareFromZip(new File(["isto nao e um zip"], "falso.zip"))
    ).rejects.toThrow(/não é um \.zip de verdade/);
  });

  it("recusa acima do limite antes de ler o conteudo", async () => {
    const grande = zipValido();

    Object.defineProperty(grande, "size", { value: MAX_UPLOAD_BYTES + 1 });

    await expect(prepareFromZip(grande)).rejects.toThrow(/o limite é 50\.0 MB/);
  });
});

describe("formatarTamanho", () => {
  it.each([
    [1, "1 KB"],
    [1024, "1 KB"],
    [1536, "2 KB"],
    [1024 * 1024, "1.0 MB"],
    [50 * 1024 * 1024, "50.0 MB"],
  ])("%i bytes viram %s", (bytes, esperado) => {
    expect(formatarTamanho(bytes)).toBe(esperado);
  });
});
