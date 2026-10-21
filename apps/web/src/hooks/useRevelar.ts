import { useEffect } from "react";

const PRAZO_DE_SEGURANCA_MS = 1200;

export function useRevelar(dependencias: unknown[] = []) {
  useEffect(() => {
    const alvos = Array.from(
      document.querySelectorAll<HTMLElement>("[data-revelar]")
    );

    if (alvos.length === 0) return;

    const revelar = (elemento: Element) => {
      elemento.classList.add("revelado");
      elemento.classList.remove("por-revelar");
    };

    const revelarTudo = () => alvos.forEach(revelar);

    const querMenosMovimento = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    if (querMenosMovimento || typeof IntersectionObserver === "undefined") {
      revelarTudo();
      return;
    }

    let observadorRespondeu = false;

    const observador = new IntersectionObserver(
      (entradas) => {
        observadorRespondeu = true;

        for (const entrada of entradas) {
          if (!entrada.isIntersecting) continue;

          revelar(entrada.target);

          observador.unobserve(entrada.target);
        }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.03 }
    );

    for (const alvo of alvos) {
      const caixa = alvo.getBoundingClientRect();
      const jaVisivel = caixa.top < window.innerHeight && caixa.bottom > 0;

      if (jaVisivel) {
        revelar(alvo);
        continue;
      }

      alvo.classList.add("por-revelar");
      observador.observe(alvo);
    }

    const prazo = window.setTimeout(() => {
      if (!observadorRespondeu) revelarTudo();
    }, PRAZO_DE_SEGURANCA_MS);

    return () => {
      window.clearTimeout(prazo);
      observador.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencias);
}
