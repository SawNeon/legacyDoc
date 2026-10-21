import { useEffect, useRef } from "react";

type Props = {
  origem: string | null;
  aberto: boolean;
  excluindo: boolean;
  erro: string | null;
  aoConfirmar: () => void;
  aoCancelar: () => void;
};

export default function ConfirmarExclusao({
  origem,
  aberto,
  excluindo,
  erro,
  aoConfirmar,
  aoCancelar,
}: Props) {
  const dialogo = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const elemento = dialogo.current;
    if (!elemento) return;

    if (aberto && !elemento.open) elemento.showModal();
    if (!aberto && elemento.open) elemento.close();
  }, [aberto]);

  return (
    <dialog
      ref={dialogo}
      className="dialogo"
      aria-labelledby="dialogo-excluir-titulo"
      aria-describedby="dialogo-excluir-texto"
      onCancel={(evento) => {
        evento.preventDefault();
        if (!excluindo) aoCancelar();
      }}
    >
      <h2 id="dialogo-excluir-titulo">Excluir análise?</h2>

      <p id="dialogo-excluir-texto">
        Tem certeza que quer excluir a análise de{" "}
        <strong className="file-path">{origem ?? "origem desconhecida"}</strong>? Os documentos e
        as melhorias dela serão apagados e isso não pode ser desfeito.
      </p>

      {erro && (
        <p className="form-error" role="alert">
          {erro}
        </p>
      )}

      <div className="dialogo-acoes">
        <button
          type="button"
          className="btn btn-secondary"
          autoFocus
          disabled={excluindo}
          onClick={aoCancelar}
        >
          Cancelar
        </button>

        <button type="button" className="btn btn-danger" disabled={excluindo} onClick={aoConfirmar}>
          {excluindo ? "Excluindo..." : "Sim, excluir"}
        </button>
      </div>
    </dialog>
  );
}
