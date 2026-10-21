import { zip, type Zippable } from "fflate";

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

const MAX_SOURCE_FILE_BYTES = 512 * 1024;

export const MAX_ENTRIES = 5000;

const IGNORED_DIRECTORIES = new Set([
  "node_modules",
  "vendor",
  "third_party",
  "thirdparty",
  "dist",
  "build",
  "out",
  "target",
  "bin",
  "obj",
  "venv",
  "env",
  "__pycache__",
  "pods",
  "bower_components",
  "coverage",
  "site-packages",
]);

const GENERATED_MARKERS = [".min.js", ".min.css", ".bundle.js", ".generated.", "_pb2.py", ".pb.go"];

export type PreparedUpload = {
  file: File;

  label: string;

  includedFiles: number | null;

  skipped: {
    ignoredFolders: number;
    unsupported: number;
    tooLarge: number;
    generated: number;
  };

  truncated: boolean;
};

export class UploadError extends Error {}

function formatarTamanho(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;

  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function extensaoEmMinusculas(nome: string) {
  const ponto = nome.lastIndexOf(".");
  return ponto <= 0 ? "" : nome.slice(ponto).toLowerCase();
}

function caminhoRelativo(arquivo: File) {
  const completo = arquivo.webkitRelativePath || arquivo.name;
  const partes = completo.split("/");

  return partes.length > 1 ? partes.slice(1).join("/") : completo;
}

function nomeDaPasta(arquivos: File[]) {
  const primeiro = arquivos[0]?.webkitRelativePath ?? "";
  return primeiro.split("/")[0] || "projeto";
}

async function lerBytes(arquivo: File): Promise<Uint8Array> {
  return new Uint8Array(await arquivo.arrayBuffer());
}

function comprimir(entradas: Zippable): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    zip(entradas, { level: 6 }, (erro, dados) => {
      if (erro) {
        reject(new UploadError("Não foi possível compactar os arquivos."));
        return;
      }

      resolve(dados);
    });
  });
}

export async function prepareFromFolder(
  arquivos: File[],
  extensoesSuportadas: Set<string>
): Promise<PreparedUpload> {
  const skipped = { ignoredFolders: 0, unsupported: 0, tooLarge: 0, generated: 0 };
  const escolhidos: { caminho: string; arquivo: File }[] = [];

  for (const arquivo of arquivos) {
    const caminho = caminhoRelativo(arquivo);
    const partes = caminho.split("/");
    const nome = partes[partes.length - 1];

    const pastas = partes.slice(0, -1);
    if (pastas.some((p) => p.startsWith(".") || IGNORED_DIRECTORIES.has(p.toLowerCase()))) {
      skipped.ignoredFolders += 1;
      continue;
    }

    if (!extensoesSuportadas.has(extensaoEmMinusculas(nome))) {
      skipped.unsupported += 1;
      continue;
    }

    if (GENERATED_MARKERS.some((marca) => nome.includes(marca))) {
      skipped.generated += 1;
      continue;
    }

    if (arquivo.size > MAX_SOURCE_FILE_BYTES) {
      skipped.tooLarge += 1;
      continue;
    }

    escolhidos.push({ caminho, arquivo });
  }

  if (escolhidos.length === 0) {
    throw new UploadError(
      "Nenhum arquivo de código suportado foi encontrado nesta pasta. " +
        "Escolha a pasta que contém o código-fonte."
    );
  }

  const truncated = escolhidos.length > MAX_ENTRIES;
  const enviados = truncated ? escolhidos.slice(0, MAX_ENTRIES) : escolhidos;

  const entradas: Zippable = {};

  for (let i = 0; i < enviados.length; i += 100) {
    const lote = enviados.slice(i, i + 100);
    const conteudos = await Promise.all(lote.map((item) => lerBytes(item.arquivo)));

    lote.forEach((item, indice) => {
      entradas[item.caminho] = conteudos[indice];
    });
  }

  const comprimido = await comprimir(entradas);

  if (comprimido.byteLength > MAX_UPLOAD_BYTES) {
    throw new UploadError(
      `O projeto compactado tem ${formatarTamanho(comprimido.byteLength)} e o limite é ` +
        `${formatarTamanho(MAX_UPLOAD_BYTES)}. Escolha uma subpasta com menos código.`
    );
  }

  const nome = nomeDaPasta(arquivos);

  return {
    file: new File([comprimido as unknown as BlobPart], `${nome}.zip`, {
      type: "application/zip",
    }),
    label: nome,
    includedFiles: enviados.length,
    skipped,
    truncated,
  };
}

export async function prepareFromZip(arquivo: File): Promise<PreparedUpload> {
  if (!arquivo.name.toLowerCase().endsWith(".zip")) {
    throw new UploadError("Envie um arquivo .zip.");
  }

  if (arquivo.size === 0) {
    throw new UploadError("O arquivo está vazio.");
  }

  if (arquivo.size > MAX_UPLOAD_BYTES) {
    throw new UploadError(
      `O arquivo tem ${formatarTamanho(arquivo.size)} e o limite é ` +
        `${formatarTamanho(MAX_UPLOAD_BYTES)}.`
    );
  }

  const inicio = new Uint8Array(await arquivo.slice(0, 2).arrayBuffer());

  if (inicio[0] !== 0x50 || inicio[1] !== 0x4b) {
    throw new UploadError("Este arquivo não é um .zip de verdade, mesmo com a extensão.");
  }

  return {
    file: arquivo,
    label: arquivo.name,
    includedFiles: null,
    skipped: { ignoredFolders: 0, unsupported: 0, tooLarge: 0, generated: 0 },
    truncated: false,
  };
}

export { formatarTamanho };
