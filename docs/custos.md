# Custo por rodada

Medição de 2026-09-11. Refaça quando mudar prompt, chunking ou roteamento.

## Como foi medido

O roteador de provedores foi substituído por um que registra as strings exatas
de sistema e usuário que o pipeline monta, e responde com os schemas reais.
Nenhuma chamada saiu para a OpenAI.

Isso significa que **a entrada não é estimativa**: é o payload que teria sido
enviado, contado com a mesma razão de caracteres por token que o código usa
(`CHARS_PER_TOKEN = 3.6`).

A **saída é modelada**, porque só o modelo sabe o tamanho da própria resposta.
Foi construída a partir do schema de resposta real, com comprimentos de campo
tirados da documentação de exemplo em `apps/cli/legacydoc_cli/seed.py`. É a
parte com incerteza; o smoke contra a API real substitui esse número por um
medido.

Repositório usado: `SawNeon/legacyDoc`, 76 arquivos, 482 KB de código Python.

## Resultado, roteamento atual

| nível | chamadas | entrada | saída | total | por arquivo |
|:--|--:|--:|--:|--:|--:|
| basic | 229 | 292.405 | 231.368 | US$ 0,18 | US$ 0,0024 |
| standard | 306 | 438.349 | 244.304 | US$ 0,68 | US$ 0,0089 |
| pro | 382 | 795.963 | 250.308 | US$ 1,63 | US$ 0,0215 |

O verificador sozinho é 59% do custo do nível `pro`. Ele reenvia o arquivo
inteiro junto da documentação, e é o único agente que roda em modelo caro
gastando entrada alta.

## O que cada plano gasta por job

| plano | arquivos/job | nível | custo do job | jobs até o teto | cota do plano |
|:--|--:|:--|--:|--:|--:|
| Free | 3 | basic | US$ 0,007 | 69 | 20 |
| Pro | 50 | basic | US$ 0,12 | 207 | 500 |
| Pro | 50 | standard | US$ 0,45 | 56 | 500 |
| Pro | 50 | pro | US$ 1,07 | 23 | 500 |
| Team | 500 | basic | US$ 1,20 | 166 | 5.000 |
| Team | 500 | standard | US$ 4,45 | 44 | 5.000 |
| Team | 500 | pro | US$ 10,73 | 18 | 5.000 |

**No Free a cota de jobs é o que limita.** Nos planos pagos é o teto em dólar,
e por larga margem. Um assinante Pro que usa sempre o nível mais profundo em
jobs cheios para no vigésimo terceiro job, não no quingentésimo.

Isso é uma incoerência da tabela de preços, não do código: anunciar 500 jobs
por mês quando o dinheiro acaba em 23 gera reclamação legítima. Ou o teto em
dólar sobe, ou a cota anunciada desce, ou a comunicação diz que a cota vale
para jobs pequenos.

## O roteamento está desatualizado

`gpt-4o-mini` e `gpt-4o` são modelos de 2024 e continuam na rota padrão por
inércia. Preços conferidos na tabela oficial em 2026-09-11 e batem com o
catálogo, mas a família nova custa uma fração para o mesmo trabalho.

Aplicando os mesmos tokens medidos a outras rotas:

| rota | basic | standard | pro |
|:--|--:|--:|--:|
| hoje: 4o-mini + 4o | US$ 0,18 | US$ 0,68 | US$ 1,63 |
| só troca os caros por gpt-5-mini | US$ 0,18 | US$ 0,25 | US$ 0,35 |
| gpt-5-nano + gpt-5-mini | US$ 0,11 | US$ 0,17 | US$ 0,27 |
| gpt-5-nano + gpt-5.6-luna | US$ 0,11 | US$ 0,15 | US$ 0,23 |

Trocar só os dois agentes caros já corta 79% do nível `pro` e não encosta no
escritor, que é o agente que define a qualidade do texto. É a mudança de menor
risco e maior retorno.

**Não troque só olhando preço.** Antes de mexer no roteamento é preciso:

1. Confirmar que o modelo suporta saída estruturada por JSON schema. O pipeline
   inteiro depende disso; a página de preços não informa.
2. Rodar o smoke no mesmo arquivo com a rota velha e a nova, e comparar a
   documentação gerada. Um escritor mais barato que alucina mais custa caro.
3. Atualizar `catalog.py` com os preços e a data da consulta.

## Como refazer a medição

O script de medição não está versionado de propósito: ele instrumenta o
pipeline e sai de sincronia a cada mudança de prompt. O caminho versionado é o
smoke contra a API real, que dá o número medido de verdade:

```bash
python -m legacydoc_cli.smoke --plan pro --depth pro
```

Ele imprime tokens de entrada e saída por chamada e o custo total.
