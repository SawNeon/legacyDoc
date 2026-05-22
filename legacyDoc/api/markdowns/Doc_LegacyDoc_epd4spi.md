# 📄 Documentação de Código: `epd4spi`

> Documentação gerada automaticamente para o módulo **epd4spi**.

## 📑 Índice de Funções

- [init](#-função-init)
- [gpio_set_direction](#-função-gpio_set_direction)
- [gpio_set_pull_mode](#-função-gpio_set_pull_mode)
- [cmdM1](#-função-cmdm1)
- [dataM1](#-função-datam1)
- [cmdS1](#-função-cmds1)
- [dataS1](#-função-datas1)
- [cmdM2](#-função-cmdm2)
- [dataS1](#-função-datas1)
- [dataM2](#-função-datam2)
- [cmdS2](#-função-cmds2)
- [dataM2](#-função-datam2)
- [cmdS2](#-função-cmds2)
- [dataS2](#-função-datas2)
- [cmdM1S1M2S2](#-função-cmdm1s1m2s2)
- [dataM1S1M2S2](#-função-datam1s1m2s2)
- [data](#-função-data)
- [dataM1](#-função-datam1)
- [dataS1](#-função-datas1)
- [dataS2](#-função-datas2)
- [reset](#-função-reset)

---

## 🛠 Função: `init`

> **Resumo:** Inicializa a comunicação SPI com configurações específicas.

### 💻 Assinatura

```cpp
void Epd4Spi::init(uint8_t frequency=4,bool debug=false)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **frequency** |
| `bool` | **debug** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu configuro os pinos do SPI e defino suas direções. Isso garante que a comunicação SPI funcione corretamente, permitindo que os dispositivos se comuniquem de forma eficaz. Além disso, habilito o modo de depuração, se necessário, para facilitar a resolução de problemas.

---

## 🛠 Função: `gpio_set_direction`

> **Resumo:** Configura a direção de um pino GPIO.

### 💻 Assinatura

```cpp
void gpio_set_direction(gpio_num_t gpio_num, gpio_mode_t mode)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `gpio_num_t` | **gpio_num** |
| `gpio_mode_t` | **mode** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Este método é utilizado para definir se um pino GPIO será uma entrada ou saída. Isso é crucial para garantir que os pinos funcionem corretamente em um sistema, permitindo a comunicação adequada entre os componentes eletrônicos. A configuração correta dos pinos é fundamental para o funcionamento do dispositivo.

---

## 🛠 Função: `gpio_set_pull_mode`

> **Resumo:** Configura o modo de pull de um pino GPIO.

### 💻 Assinatura

```cpp
void gpio_set_pull_mode(gpio_num_t gpio_num, gpio_pull_mode_t pull_mode)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `gpio_num_t` | **gpio_num** |
| `gpio_pull_mode_t` | **pull_mode** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu configuro o modo de pull de um pino GPIO, que é essencial para garantir que o pino tenha um estado definido quando não está sendo acionado. Isso ajuda a evitar flutuações indesejadas e garante uma comunicação estável entre os componentes do sistema. A configuração correta é vital para o desempenho do dispositivo.

---

## 🛠 Função: `cmdM1`

> **Resumo:** Envia um comando para o dispositivo M1.

### 💻 Assinatura

```cpp
void Epd4Spi::cmdM1(const uint8_t cmd)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **cmd** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio um comando para o dispositivo M1. Primeiro, verifico se o modo de depuração está ativado e, se sim, imprimo o comando. Em seguida, configuro a transação SPI e transmito o comando. Por fim, restauro os níveis dos pinos de controle.

---

## 🛠 Função: `dataM1`

> **Resumo:** Envia dados para o dispositivo M1.

### 💻 Assinatura

```cpp
void Epd4Spi::dataM1(uint8_t data)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **data** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio dados para o dispositivo M1. Assim como no método anterior, verifico o modo de depuração e imprimo os dados. Depois, configuro a transação SPI e transmito os dados. Finalmente, restauro os níveis dos pinos de controle.

---

## 🛠 Função: `cmdS1`

> **Resumo:** Envia um comando S1 via SPI.

### 💻 Assinatura

```cpp
void Epd4Spi::cmdS1(const uint8_t cmd)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **cmd** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio um comando S1 através da interface SPI. Primeiro, verifico se o modo de depuração está ativado e, em seguida, configuro a transação SPI. Após a transmissão, restauro os níveis de GPIO para finalizar o comando.

---

## 🛠 Função: `dataS1`

> **Resumo:** Envia dados S1 via SPI.

### 💻 Assinatura

```cpp
void Epd4Spi::dataS1(uint8_t data)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **data** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio dados S1 pela interface SPI. Primeiro, verifico se o modo de depuração está ativado e, em seguida, configuro a transação SPI. Após a transmissão, restauro os níveis de GPIO para concluir o envio dos dados.

---

## 🛠 Função: `cmdM2`

> **Resumo:** Envia um comando M2 via SPI.

### 💻 Assinatura

```cpp
void Epd4Spi::cmdM2(const uint8_t cmd)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **cmd** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio um comando M2 através da interface SPI. Primeiro, verifico se o modo de depuração está ativado e, em seguida, configuro a transação SPI. O método finaliza a transmissão do comando, garantindo que a comunicação SPI ocorra corretamente.

---

## 🛠 Função: `dataS1`

> **Resumo:** Envia dados S1 via SPI.

### 💻 Assinatura

```cpp
void Epd4Spi::dataS1(uint8_t data)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **data** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio dados S1 pela interface SPI. Primeiro, verifico se o modo de depuração está ativado e, em seguida, configuro a transação SPI. Após a transmissão, restauro os níveis de GPIO para concluir o envio dos dados.

---

## 🛠 Função: `dataM2`

> **Resumo:** Envia dados via SPI.

### 💻 Assinatura

```cpp
void Epd4Spi::dataM2(uint8_t data)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **data** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio um dado via SPI. Primeiro, verifico se o modo de depuração está ativado e imprimo o dado. Em seguida, configuro os níveis GPIO, preparo a transação SPI e transmito o dado. Por fim, restauro o nível GPIO.

---

## 🛠 Função: `cmdS2`

> **Resumo:** Envia um comando via SPI.

### 💻 Assinatura

```cpp
void Epd4Spi::cmdS2(const uint8_t cmd)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const uint8_t` | **cmd** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio um comando via SPI. Primeiro, verifico se o modo de depuração está ativado e imprimo o comando. Depois, configuro os níveis GPIO, preparo a transação SPI e transmito o comando. Por fim, restauro o nível GPIO.

---

## 🛠 Função: `dataM2`

> **Resumo:** Envia dados via SPI.

### 💻 Assinatura

```cpp
void Epd4Spi::dataM2(uint8_t data)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **data** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio um dado via SPI. Primeiro, verifico se o modo de depuração está ativado e imprimo o dado. Em seguida, configuro os níveis GPIO, preparo a transação SPI e transmito o dado. Por fim, restauro o nível GPIO.

---

## 🛠 Função: `cmdS2`

> **Resumo:** Envia um comando via SPI.

### 💻 Assinatura

```cpp
void Epd4Spi::cmdS2(const uint8_t cmd)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const uint8_t` | **cmd** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio um comando via SPI. Primeiro, verifico se o modo de depuração está ativado e imprimo o comando. Depois, configuro os níveis GPIO, preparo a transação SPI e transmito o comando. Por fim, restauro o nível GPIO.

---

## 🛠 Função: `dataS2`

> **Resumo:** Envia dados para o display S2.

### 💻 Assinatura

```cpp
void Epd4Spi::dataS2(uint8_t data)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **data** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio dados para o display S2. Primeiro, habilito o modo de depuração, se necessário. Em seguida, configuro a transação SPI e transmito os dados. Isso garante que o display receba as informações corretas para funcionar corretamente.

---

## 🛠 Função: `cmdM1S1M2S2`

> **Resumo:** Envia um comando para todos os 4 displays.

### 💻 Assinatura

```cpp
void Epd4Spi::cmdM1S1M2S2(uint8_t cmd)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **cmd** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu envio um comando para todos os quatro displays. Após configurar os pinos de controle, transmito o comando via SPI. Isso assegura que todos os displays respondam ao mesmo comando simultaneamente, facilitando a sincronização.

---

## 🛠 Função: `dataM1S1M2S2`

> **Resumo:** Envia dados para os displays M1, S1, M2 e S2.

### 💻 Assinatura

```cpp
void Epd4Spi::dataM1S1M2S2(uint8_t data)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **data** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio dados para os displays M1, S1, M2 e S2. Embora o modo de depuração esteja comentado, a configuração da transação SPI e a transmissão dos dados são realizadas para garantir que todos os displays recebam as informações necessárias.

---

## 🛠 Função: `data`

> **Resumo:** Envia dados para o SPI.

### 💻 Assinatura

```cpp
void Epd4Spi::data(const uint8_t *data, int len)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const uint8_t *` | **data** |
| `int` | **len** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu envio dados para o SPI chamando a função dataM1. Isso garante que os dados sejam transmitidos corretamente, utilizando a configuração adequada do SPI. O impacto é que a comunicação com o dispositivo SPI se torna eficiente e confiável.

---

## 🛠 Função: `dataM1`

> **Resumo:** Transmite dados via SPI usando polling.

### 💻 Assinatura

```cpp
void Epd4Spi::dataM1(const uint8_t *data, int len)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const uint8_t *` | **data** |
| `int` | **len** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, eu transmito dados via SPI, garantindo que a transação seja feita corretamente. Ao utilizar o modo polling, eu consigo uma transmissão mais rápida, evitando a sobrecarga de interrupções. Isso resulta em uma comunicação mais eficiente com o dispositivo.

---

## 🛠 Função: `dataS1`

> **Resumo:** Transmite dados usando o canal S1.

### 💻 Assinatura

```cpp
void Epd4Spi::dataS1(const uint8_t *data, int len)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const uint8_t *` | **data** |
| `int` | **len** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, verifico se o comprimento é zero. Se não for, configuro o nível do GPIO para iniciar a transmissão, transmito os dados e, em seguida, restauro o nível do GPIO. Isso garante que os dados sejam enviados corretamente pelo canal S1.

---

## 🛠 Função: `dataS2`

> **Resumo:** Transmite dados usando o canal S2.

### 💻 Assinatura

```cpp
void Epd4Spi::dataS2(const uint8_t *data, int len)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const uint8_t *` | **data** |
| `int` | **len** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, verifico se o comprimento é zero. Se não for, configuro o nível do GPIO para iniciar a transmissão, transmito os dados e restauro o nível do GPIO. Isso assegura que os dados sejam enviados corretamente pelo canal S2.

---

## 🛠 Função: `reset`

> **Resumo:** Reseta o dispositivo com um atraso especificado.

### 💻 Assinatura

```cpp
void Epd4Spi::reset(uint8_t millis=20)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `uint8_t` | **millis** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste método, configuro os níveis do GPIO para zero, aguardo um tempo especificado e, em seguida, restauro os níveis do GPIO. Isso garante que o dispositivo seja resetado corretamente.

---

