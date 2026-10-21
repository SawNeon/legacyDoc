import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import {
  formatarTamanho,
  prepareFromFolder,
  prepareFromZip,
  UploadError,
  type PreparedUpload,
} from "../services/upload";

type Props = {
  extensions: Set<string> | null;

  planMaxFiles?: number;

  disabled?: boolean;

  onChange: (prepared: PreparedUpload | null) => void;
};

export default function UploadPicker({ extensions, planMaxFiles, disabled, onChange }: Props) {
  const campoPasta = useRef<HTMLInputElement>(null);
  const campoZip = useRef<HTMLInputElement>(null);

  const [preparando, setPreparando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [pronto, setPronto] = useState<PreparedUpload | null>(null);
  const [arrastando, setArrastando] = useState(false);

  function definir(material: PreparedUpload | null) {
    setPronto(material);
    onChange(material);
  }

  async function processar(tarefa: () => Promise<PreparedUpload>) {
    setErro(null);
    setPreparando(true);
    definir(null);

    try {
      definir(await tarefa());
    } catch (falha) {
      setErro(
        falha instanceof UploadError
          ? falha.message
          : "Não foi possível preparar os arquivos. Tente novamente."
      );
    } finally {
      setPreparando(false);
    }
  }

  function aoEscolherPasta(evento: ChangeEvent<HTMLInputElement>) {
    const arquivos = Array.from(evento.target.files ?? []);
    evento.target.value = "";

    if (arquivos.length === 0 || !extensions) return;

    processar(() => prepareFromFolder(arquivos, extensions));
  }

  function aoEscolherZip(evento: ChangeEvent<HTMLInputElement>) {
    const arquivo = evento.target.files?.[0];
    evento.target.value = "";

    if (arquivo) processar(() => prepareFromZip(arquivo));
  }

  function aoSoltar(evento: DragEvent<HTMLDivElement>) {
    evento.preventDefault();
    setArrastando(false);

    if (disabled || preparando) return;

    const arquivo = evento.dataTransfer.files[0];
    if (!arquivo) return;

    if (!arquivo.name.toLowerCase().endsWith(".zip")) {
      setErro("Solte um arquivo .zip. Para enviar uma pasta, use o botão “Escolher pasta”.");
      return;
    }

    processar(() => prepareFromZip(arquivo));
  }

  const bloqueado = disabled || preparando;

  if (pronto) {
    const { skipped } = pronto;
    const omitidos = skipped.ignoredFolders + skipped.unsupported + skipped.tooLarge + skipped.generated;
    const passaDoPlano =
      planMaxFiles !== undefined &&
      pronto.includedFiles !== null &&
      pronto.includedFiles > planMaxFiles;

    return (
      <div className="upload-resumo" role="status">
        <div className="upload-resumo-topo">
          <strong className="file-path">{pronto.label}</strong>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => definir(null)}
            disabled={disabled}
          >
            Trocar
          </button>
        </div>

        <p>
          {pronto.includedFiles !== null
            ? `${pronto.includedFiles} arquivos de código`
            : "Arquivo .zip"}{" "}
          · {formatarTamanho(pronto.file.size)}
          {pronto.includedFiles !== null && " compactado"}
        </p>

        {omitidos > 0 && (
          <p className="upload-nota">
            Deixamos de fora {omitidos} {omitidos === 1 ? "arquivo" : "arquivos"} que não
            {omitidos === 1 ? " entra" : " entram"} na análise
            {skipped.ignoredFolders > 0 &&
              `, ${skipped.ignoredFolders} em pastas de dependência ou ocultas`}
            {skipped.unsupported > 0 && `, ${skipped.unsupported} de outros formatos`}
            {skipped.tooLarge > 0 && `, ${skipped.tooLarge} grandes demais`}
            {skipped.generated > 0 &&
              `, ${skipped.generated} ${skipped.generated === 1 ? "gerado" : "gerados"} automaticamente`}.
          </p>
        )}

        {passaDoPlano && (
          <p className="upload-nota upload-aviso">
            Seu plano documenta até {planMaxFiles} arquivos por análise. Os demais serão
            ignorados.
          </p>
        )}

        {pronto.truncated && (
          <p className="upload-nota upload-aviso">
            O projeto tem mais arquivos que o limite de um envio. Enviamos os primeiros;
            para o resto, escolha uma subpasta.
          </p>
        )}
      </div>
    );
  }

  return (
    <div
      className="upload-picker"
      data-arrastando={arrastando ? "sim" : undefined}
      onDragOver={(evento) => {
        evento.preventDefault();
        if (!bloqueado) setArrastando(true);
      }}
      onDragLeave={() => setArrastando(false)}
      onDrop={aoSoltar}
    >
      <p className="upload-titulo">
        {preparando ? "Preparando os arquivos..." : "Envie o código que está no seu computador"}
      </p>

      <p className="upload-dica">
        Escolha a pasta do projeto ou arraste um .zip. Pastas como node_modules e .git são
        deixadas de fora automaticamente.
      </p>

      <div className="upload-acoes">
        <button
          type="button"
          className="btn"
          disabled={bloqueado || !extensions}
          onClick={() => campoPasta.current?.click()}
        >
          Escolher pasta
        </button>

        <button
          type="button"
          className="btn btn-secondary"
          disabled={bloqueado}
          onClick={() => campoZip.current?.click()}
        >
          Escolher .zip
        </button>
      </div>

      <input
        ref={campoPasta}
        type="file"
        hidden
        multiple
        onChange={aoEscolherPasta}
        {...({ webkitdirectory: "" } as Record<string, string>)}
      />

      <input ref={campoZip} type="file" hidden accept=".zip,application/zip" onChange={aoEscolherZip} />

      {erro && (
        <p className="upload-erro" role="alert">
          {erro}
        </p>
      )}
    </div>
  );
}
