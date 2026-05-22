# 📄 Documentação de Código: `dosbox`

> Documentação gerada automaticamente para o módulo **dosbox**.

## 📑 Índice de Funções

- [DOSBOX_GetTicksDone](#-função-dosbox_getticksdone)
- [DOSBOX_SetTicksDone](#-função-dosbox_setticksdone)
- [DOSBOX_SetTicksScheduled](#-função-dosbox_setticksscheduled)
- [normal_loop](#-função-normal_loop)
- [increase_ticks](#-função-increase_ticks)
- [GetTicks](#-função-getticks)
- [GetTicksUs](#-função-getticksus)
- [TIMER_AddTick](#-função-timer_addtick)
- [GetTicksDiff](#-função-getticksdiff)
- [CPU_CycleAutoAdjust](#-função-cpu_cycleautoadjust)
- [CPU_CycleMax](#-função-cpu_cyclemax)
- [CPU_CyclePercUsed](#-função-cpu_cyclepercused)
- [CPU_IODelayRemoved](#-função-cpu_iodelayremoved)
- [E_Exit](#-função-e_exit)
- [LOG](#-função-log)
- [MAPPER_AddHandler](#-função-mapper_addhandler)
- [GFX_RequestExit](#-função-gfx_requestexit)
- [MSG_LoadMessages](#-função-msg_loadmessages)
- [GFX_GetPresentationMode](#-função-gfx_getpresentationmode)
- [GFX_MaybePresentFrame](#-função-gfx_maybepresentframe)
- [GFX_PollAndHandleEvents](#-função-gfx_pollandhandleevents)
- [ticks.locked](#-função-ticks.locked)
- [ticks.remain](#-função-ticks.remain)
- [ticks.last](#-função-ticks.last)
- [ticks.added](#-função-ticks.added)
- [ticks.done](#-função-ticks.done)
- [ticks.scheduled](#-função-ticks.scheduled)
- [MicrosInMillisecond](#-função-microsinmillisecond)
- [auto_cpu_cycles_min](#-função-auto_cpu_cycles_min)
- [DOSBOX_GetVersion](#-função-dosbox_getversion)
- [DOSBOX_GetDetailedVersion](#-função-dosbox_getdetailedversion)
- [DOSBOX_SetLoop](#-função-dosbox_setloop)
- [DOSBOX_SetNormalLoop](#-função-dosbox_setnormalloop)
- [DOSBOX_RunMachine](#-função-dosbox_runmachine)
- [DOSBOX_RequestShutdown](#-função-dosbox_requestshutdown)
- [DOSBOX_IsShutdownRequested](#-função-dosbox_isshutdownrequested)
- [DOSBOX_UnlockSpeed](#-função-dosbox_unlockspeed)
- [remove_waitpid](#-função-remove_waitpid)
- [DOSBOX_Restart](#-função-dosbox_restart)
- [DOSBOX_Restart](#-função-dosbox_restart)
- [remove_waitpid](#-função-remove_waitpid)
- [GFX_RequestExit](#-função-gfx_requestexit)
- [CreateProcess](#-função-createprocess)
- [LOG_ERR](#-função-log_err)
- [dosbox_realinit](#-função-dosbox_realinit)
- [DOSBOX_Init](#-função-dosbox_init)
- [DOSBOX_Destroy](#-função-dosbox_destroy)
- [notify_dosbox_setting_updated](#-função-notify_dosbox_setting_updated)
- [add_dosbox_config_section](#-função-add_dosbox_config_section)
- [DOSBOX_InitModuleConfigsAndMessages](#-função-dosbox_initmoduleconfigsandmessages)
- [DOSBOX_InitModules](#-função-dosbox_initmodules)
- [DOSBOX_InitModules](#-função-dosbox_initmodules)
- [DOSBOX_Init](#-função-dosbox_init)
- [PROGRAMS_AddMessages](#-função-programs_addmessages)
- [LOG_StartUp](#-função-log_startup)
- [LOG_Init](#-função-log_init)
- [COMPOSITE_Init](#-função-composite_init)
- [CPU_Init](#-função-cpu_init)
- [FPU_Init](#-função-fpu_init)
- [DMA_Init](#-função-dma_init)
- [VGA_Init](#-função-vga_init)
- [KEYBOARD_Init](#-função-keyboard_init)
- [PCI_Init](#-função-pci_init)
- [VOODOO_Init](#-função-voodoo_init)
- [CAPTURE_Init](#-função-capture_init)
- [MIXER_Init](#-função-mixer_init)
- [MIDI_Init](#-função-midi_init)
- [DEBUG_Init](#-função-debug_init)
- [SBLASTER_Init](#-função-sblaster_init)
- [GUS_Init](#-função-gus_init)
- [IMFC_Init](#-função-imfc_init)
- [INNOVATION_Init](#-função-innovation_init)
- [SPEAKER_Init](#-função-speaker_init)
- [REELMAGIC_Init](#-função-reelmagic_init)
- [DOSBOX_DestroyModules](#-função-dosbox_destroymodules)

---

## 🛠 Função: `DOSBOX_GetTicksDone`

> **Resumo:** Retorna o número de ticks concluídos.

### 💻 Assinatura

```cpp
int64_t DOSBOX_GetTicksDone()
```

### 📤 Retorno

- **Tipo:** `int64_t`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função é utilizada para obter o número total de ticks que foram concluídos. Ao chamá-la, eu consigo acessar a variável 'done' dentro da estrutura 'ticks', o que é útil para monitorar o progresso do tempo no emulador.

---

## 🛠 Função: `DOSBOX_SetTicksDone`

> **Resumo:** Define o número de ticks concluídos.

### 💻 Assinatura

```cpp
void DOSBOX_SetTicksDone(const int64_t ticks_done)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `int64_t` | **ticks_done** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função permite que eu defina o número de ticks que foram concluídos. Ao passar um valor para 'ticks_done', eu atualizo a variável 'done' na estrutura 'ticks', ajudando a gerenciar o tempo no emulador.

---

## 🛠 Função: `DOSBOX_SetTicksScheduled`

> **Resumo:** Define os ticks agendados.

### 💻 Assinatura

```cpp
void DOSBOX_SetTicksScheduled(const int64_t ticks_scheduled)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `int64_t` | **ticks_scheduled** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu defino o número de ticks agendados. Isso é importante para garantir que o sistema mantenha o controle do tempo de execução, permitindo uma gestão eficiente dos ciclos de processamento.

---

## 🛠 Função: `normal_loop`

> **Resumo:** Executa um loop normal para processamento.

### 💻 Assinatura

```cpp
static Bitu normal_loop()
```

### 📤 Retorno

- **Tipo:** `Bitu`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu executo um loop contínuo que processa eventos e chamadas de função. Isso é crucial para a operação do sistema, pois garante que as tarefas sejam executadas em tempo real, mantendo a fluidez do emulador.

---

## 🛠 Função: `increase_ticks`

> **Resumo:** Aumenta os ticks para o emulador.

### 💻 Assinatura

```cpp
static void increase_ticks()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu aumento os ticks do emulador. Ao verificar se os ticks estão bloqueados, eu ajusto o valor de ticks.remain e reinicio algumas variáveis. Isso garante que o emulador funcione corretamente durante a execução, mantendo a contagem de ticks precisa.

---

## 🛠 Função: `GetTicks`

> **Resumo:** Retorna o número atual de ticks.

### 💻 Assinatura

```cpp
auto GetTicks()
```

### 📤 Retorno

- **Tipo:** `auto`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função me fornece o número atual de ticks, que é essencial para o controle do tempo no emulador. Usando esse valor, eu posso ajustar a lógica de emulação e garantir que os ciclos de CPU sejam gerenciados corretamente, impactando a performance do emulador.

---

## 🛠 Função: `GetTicksUs`

> **Resumo:** Retorna o número atual de ticks em microsegundos.

### 💻 Assinatura

```cpp
auto GetTicksUs()
```

### 📤 Retorno

- **Tipo:** `auto`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu obtenho o número de ticks em microsegundos, o que é crucial para cálculos de tempo mais precisos. Isso me permite fazer ajustes finos na emulação, garantindo que a experiência do usuário seja suave e responsiva, especialmente em modos de velocidade variável.

---

## 🛠 Função: `TIMER_AddTick`

> **Resumo:** Adiciona um tick ao temporizador.

### 💻 Assinatura

```cpp
void TIMER_AddTick()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função é responsável por adicionar um tick ao temporizador do emulador. Ao chamar essa função, eu consigo manter a contagem de tempo atualizada, o que é vital para a sincronização das operações do emulador e para garantir que os eventos ocorram no momento certo.

---

## 🛠 Função: `GetTicksDiff`

> **Resumo:** Calcula a diferença entre dois ticks.

### 💻 Assinatura

```cpp
auto GetTicksDiff(auto start, auto end)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `auto` | **start** |
| `auto` | **end** |

### 📤 Retorno

- **Tipo:** `auto`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu calculo a diferença entre dois valores de ticks. Isso é importante para medir o tempo decorrido entre eventos no emulador, permitindo que eu faça ajustes necessários para a sincronização e a performance geral do sistema.

---

## 🛠 Função: `CPU_CycleAutoAdjust`

> **Resumo:** Ajusta automaticamente os ciclos da CPU.

### 💻 Assinatura

```cpp
void CPU_CycleAutoAdjust()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função ajusta automaticamente os ciclos da CPU com base nas condições atuais do emulador. Isso garante que a emulação funcione de maneira eficiente e responsiva, adaptando-se às necessidades do sistema e melhorando a experiência do usuário.

---

## 🛠 Função: `CPU_CycleMax`

> **Resumo:** Define o número máximo de ciclos da CPU.

### 💻 Assinatura

```cpp
void CPU_CycleMax()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu defino o número máximo de ciclos que a CPU pode executar. Isso é fundamental para evitar sobrecarga no sistema e garantir que o emulador funcione dentro de limites seguros, proporcionando uma experiência de emulação estável e controlada.

---

## 🛠 Função: `CPU_CyclePercUsed`

> **Resumo:** Retorna a porcentagem de ciclos da CPU utilizados.

### 💻 Assinatura

```cpp
float CPU_CyclePercUsed()
```

### 📤 Retorno

- **Tipo:** `float`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função me fornece a porcentagem de ciclos da CPU que estão sendo utilizados. Isso é crucial para monitorar a performance do emulador e fazer ajustes conforme necessário, garantindo que o sistema opere de maneira eficiente e responsiva.

---

## 🛠 Função: `CPU_IODelayRemoved`

> **Resumo:** Remove o atraso de I/O da CPU.

### 💻 Assinatura

```cpp
void CPU_IODelayRemoved()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu removo o atraso de I/O da CPU, o que é importante para melhorar a performance do emulador. Isso ajuda a garantir que as operações de entrada e saída sejam processadas de forma mais rápida e eficiente, resultando em uma experiência de usuário mais fluida.

---

## 🛠 Função: `E_Exit`

> **Resumo:** Finaliza a execução do emulador.

### 💻 Assinatura

```cpp
void E_Exit()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função encerra a execução do emulador de forma controlada. Ao chamar essa função, eu asseguro que todos os recursos sejam liberados corretamente, evitando vazamentos de memória e garantindo que o sistema esteja em um estado limpo após a finalização.

---

## 🛠 Função: `LOG`

> **Resumo:** Registra uma mensagem no log.

### 💻 Assinatura

```cpp
void LOG(const char* message)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const char*` | **message** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu registro uma mensagem no log do emulador. Isso é essencial para monitorar eventos e erros durante a execução, permitindo que eu faça diagnósticos e melhore a qualidade do emulador com base nas informações coletadas.

---

## 🛠 Função: `MAPPER_AddHandler`

> **Resumo:** Adiciona um manipulador ao mapeador.

### 💻 Assinatura

```cpp
void MAPPER_AddHandler()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função adiciona um manipulador ao mapeador do emulador. Isso é importante para garantir que os eventos sejam tratados corretamente, permitindo uma interação adequada entre o hardware virtualizado e o software emulado, melhorando a funcionalidade geral do sistema.

---

## 🛠 Função: `GFX_RequestExit`

> **Resumo:** Solicita a saída do sistema gráfico.

### 💻 Assinatura

```cpp
void GFX_RequestExit()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu solicito a saída do sistema gráfico do emulador. Isso é fundamental para garantir que todos os recursos gráficos sejam liberados corretamente ao encerrar o emulador, evitando problemas de desempenho e garantindo uma finalização limpa.

---

## 🛠 Função: `MSG_LoadMessages`

> **Resumo:** Carrega mensagens para o emulador.

### 💻 Assinatura

```cpp
void MSG_LoadMessages()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função carrega mensagens necessárias para o emulador. Isso é essencial para garantir que o sistema tenha todas as informações necessárias para operar corretamente, melhorando a experiência do usuário e a funcionalidade do emulador.

---

## 🛠 Função: `GFX_GetPresentationMode`

> **Resumo:** Retorna o modo de apresentação atual.

### 💻 Assinatura

```cpp
PresentationMode GFX_GetPresentationMode()
```

### 📤 Retorno

- **Tipo:** `PresentationMode`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu obtenho o modo de apresentação atual do sistema gráfico. Isso é importante para determinar como os frames devem ser apresentados, garantindo que a emulação funcione de maneira eficiente e que a experiência do usuário seja otimizada.

---

## 🛠 Função: `GFX_MaybePresentFrame`

> **Resumo:** Apresenta um frame, se necessário.

### 💻 Assinatura

```cpp
void GFX_MaybePresentFrame()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função apresenta um frame do emulador, se necessário. Isso é crucial para garantir que a saída visual do emulador seja atualizada corretamente, proporcionando uma experiência de usuário suave e responsiva durante a emulação.

---

## 🛠 Função: `GFX_PollAndHandleEvents`

> **Resumo:** Verifica e trata eventos do sistema gráfico.

### 💻 Assinatura

```cpp
bool GFX_PollAndHandleEvents()
```

### 📤 Retorno

- **Tipo:** `bool`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu verifico e trato eventos do sistema gráfico. Isso é fundamental para garantir que a interação do usuário com o emulador seja fluida e responsiva, permitindo que eu reaja a entradas e eventos em tempo real.

---

## 🛠 Função: `ticks.locked`

> **Resumo:** Indica se os ticks estão bloqueados.

### 💻 Assinatura

```cpp
bool ticks.locked
```

### 📤 Retorno

- **Tipo:** `bool`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta variável indica se os ticks do emulador estão bloqueados. Isso é importante para controlar o fluxo de emulação e garantir que o sistema funcione corretamente, especialmente em modos de velocidade variável.

---

## 🛠 Função: `ticks.remain`

> **Resumo:** Número de ticks restantes.

### 💻 Assinatura

```cpp
int ticks.remain
```

### 📤 Retorno

- **Tipo:** `int`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta variável armazena o número de ticks restantes para a emulação. Isso é crucial para gerenciar o tempo e a performance do emulador, garantindo que os ciclos de CPU sejam executados de forma adequada e eficiente.

---

## 🛠 Função: `ticks.last`

> **Resumo:** Último valor de ticks.

### 💻 Assinatura

```cpp
auto ticks.last
```

### 📤 Retorno

- **Tipo:** `auto`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta variável armazena o último valor de ticks registrado. Isso é importante para calcular diferenças de tempo e garantir que a emulação funcione de maneira precisa e sincronizada, melhorando a experiência do usuário.

---

## 🛠 Função: `ticks.added`

> **Resumo:** Número de ticks adicionados.

### 💻 Assinatura

```cpp
int ticks.added
```

### 📤 Retorno

- **Tipo:** `int`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta variável armazena o número de ticks que foram adicionados. Isso é fundamental para o controle do tempo no emulador, permitindo que eu ajuste a lógica de emulação conforme necessário e mantenha a performance ideal.

---

## 🛠 Função: `ticks.done`

> **Resumo:** Número de ticks concluídos.

### 💻 Assinatura

```cpp
int ticks.done
```

### 📤 Retorno

- **Tipo:** `int`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta variável armazena o número de ticks que foram concluídos. Isso é importante para monitorar o progresso da emulação e garantir que todas as operações sejam executadas dentro dos limites de tempo estabelecidos, melhorando a eficiência do sistema.

---

## 🛠 Função: `ticks.scheduled`

> **Resumo:** Número de ticks agendados.

### 💻 Assinatura

```cpp
int ticks.scheduled
```

### 📤 Retorno

- **Tipo:** `int`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta variável armazena o número de ticks que foram agendados. Isso é crucial para gerenciar o tempo de execução do emulador e garantir que as operações sejam realizadas de forma oportuna, impactando a performance geral do sistema.

---

## 🛠 Função: `MicrosInMillisecond`

> **Resumo:** Número de microssegundos em um milissegundo.

### 💻 Assinatura

```cpp
int MicrosInMillisecond
```

### 📤 Retorno

- **Tipo:** `int`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta variável define o número de microssegundos em um milissegundo. Isso é importante para conversões de tempo e cálculos precisos dentro do emulador, garantindo que a lógica de tempo funcione corretamente e que a emulação seja precisa.

---

## 🛠 Função: `auto_cpu_cycles_min`

> **Resumo:** Número mínimo de ciclos de CPU.

### 💻 Assinatura

```cpp
constexpr auto auto_cpu_cycles_min
```

### 📤 Retorno

- **Tipo:** `auto`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta variável define o número mínimo de ciclos de CPU que devem ser utilizados. Isso é fundamental para garantir que o emulador opere de maneira eficiente e responsiva, evitando subutilização dos recursos disponíveis.

---

## 🛠 Função: `DOSBOX_GetVersion`

> **Resumo:** Retorna a versão do DOSBox.

### 💻 Assinatura

```cpp
const char* DOSBOX_GetVersion() noexcept
```

### 📤 Retorno

- **Tipo:** `const char*`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função é utilizada para obter a versão atual do DOSBox. Ao chamá-la, eu retorno uma string que representa a versão, permitindo que os usuários saibam qual versão do emulador estão utilizando. Isso é importante para garantir que todos estejam cientes das atualizações e melhorias.

---

## 🛠 Função: `DOSBOX_GetDetailedVersion`

> **Resumo:** Retorna a versão detalhada do DOSBox.

### 💻 Assinatura

```cpp
const char* DOSBOX_GetDetailedVersion() noexcept
```

### 📤 Retorno

- **Tipo:** `const char*`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu defino a função que retorna a versão detalhada do DOSBox. Ao chamar essa função, você obtém uma string que inclui a versão e o hash do Git, permitindo que você saiba exatamente qual versão do software está em uso.

---

## 🛠 Função: `DOSBOX_SetLoop`

> **Resumo:** Define o manipulador de loop para DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_SetLoop(LoopHandler* handler)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `LoopHandler*` | **handler** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu implemento a função que define um novo manipulador de loop para o DOSBox. Isso permite que você altere a lógica de execução do loop principal, impactando como o emulador processa suas operações.

---

## 🛠 Função: `DOSBOX_SetNormalLoop`

> **Resumo:** Define o loop normal para DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_SetNormalLoop()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu restauro o loop normal do DOSBox. Isso é útil para retornar ao comportamento padrão do emulador, garantindo que ele funcione como esperado após modificações.

---

## 🛠 Função: `DOSBOX_RunMachine`

> **Resumo:** Executa a máquina DOSBox até que um desligamento seja solicitado.

### 💻 Assinatura

```cpp
void DOSBOX_RunMachine()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu implemento a função que executa a máquina DOSBox. Enquanto o loop principal não solicitar um desligamento, a máquina continua a rodar, permitindo que o emulador funcione continuamente até que uma condição de parada seja atendida.

---

## 🛠 Função: `DOSBOX_RequestShutdown`

> **Resumo:** Solicita o desligamento da máquina DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_RequestShutdown()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu marco a máquina DOSBox para desligamento. Isso é importante para interromper a execução de forma controlada, permitindo que o sistema finalize suas operações de maneira segura.

---

## 🛠 Função: `DOSBOX_IsShutdownRequested`

> **Resumo:** Verifica se um desligamento foi solicitado.

### 💻 Assinatura

```cpp
bool DOSBOX_IsShutdownRequested()
```

### 📤 Retorno

- **Tipo:** `bool`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu implemento a função que verifica se um desligamento da máquina foi solicitado. Isso é útil para determinar se o emulador deve continuar executando ou se deve encerrar suas operações.

---

## 🛠 Função: `DOSBOX_UnlockSpeed`

> **Resumo:** Desbloqueia a velocidade do emulador se a tecla for pressionada.

### 💻 Assinatura

```cpp
static void DOSBOX_UnlockSpeed(bool pressed)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `bool` | **pressed** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu gerencio o desbloqueio da velocidade do emulador quando a tecla correspondente é pressionada. Isso permite que o emulador acelere suas operações, impactando a experiência do usuário durante a execução.

---

## 🛠 Função: `remove_waitpid`

> **Resumo:** Remove parâmetros de espera do vetor.

### 💻 Assinatura

```cpp
static void remove_waitpid(std::vector<std::string>& parameters)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `std::vector<std::string>&` | **parameters** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu removo os parâmetros '-waitpid' ou '--waitpid' de um vetor de strings. Ao fazer isso, garanto que o vetor não contenha esses parâmetros indesejados, melhorando a clareza e a funcionalidade do código. Isso é útil para evitar comportamentos inesperados durante a execução.

---

## 🛠 Função: `DOSBOX_Restart`

> **Resumo:** Reinicia o DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_Restart()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Esta função reinicia o DOSBox, permitindo que o emulador comece novamente. Isso é importante para garantir que as configurações e o estado do emulador sejam redefinidos, proporcionando uma experiência limpa e sem erros para o usuário. É uma parte essencial do ciclo de vida do emulador.

---

## 🛠 Função: `DOSBOX_Restart`

> **Resumo:** Reinicia o DOSBox com os parâmetros fornecidos.

### 💻 Assinatura

```cpp
void DOSBOX_Restart(std::vector<std::string>& parameters)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `std::vector<std::string>&` | **parameters** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu reinicio o DOSBox aplicando os parâmetros fornecidos. Isso é importante para garantir que as configurações corretas sejam usadas durante a reinicialização. Ao fazer isso, eu removo parâmetros indesejados e formo a linha de comando adequada para o sistema operacional.

---

## 🛠 Função: `remove_waitpid`

> **Resumo:** Remove parâmetros --waitpid da lista.

### 💻 Assinatura

```cpp
void remove_waitpid(std::vector<std::string>& parameters)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `std::vector<std::string>&` | **parameters** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste caso, eu removo qualquer parâmetro --waitpid existente da lista de parâmetros. Isso é necessário para evitar conflitos em reinicializações múltiplas. Ao fazer isso, eu asseguro que a linha de comando esteja limpa e pronta para novos parâmetros, melhorando a estabilidade do sistema.

---

## 🛠 Função: `GFX_RequestExit`

> **Resumo:** Solicita a saída do sistema gráfico.

### 💻 Assinatura

```cpp
void GFX_RequestExit(bool immediate)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `bool` | **immediate** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu solicito a saída do sistema gráfico, podendo ser imediata ou não. Isso é crucial para garantir que o DOSBox feche corretamente, liberando recursos e evitando possíveis vazamentos de memória. Essa ação finaliza a execução de forma controlada, mantendo a integridade do sistema.

---

## 🛠 Função: `CreateProcess`

> **Resumo:** Cria um novo processo no Windows.

### 💻 Assinatura

```cpp
BOOL CreateProcess(LPCSTR lpApplicationName, LPSTR lpCommandLine, LPSECURITY_ATTRIBUTES lpProcessAttributes, LPSECURITY_ATTRIBUTES lpThreadAttributes, BOOL bInheritHandles, DWORD dwCreationFlags, LPVOID lpEnvironment, LPCSTR lpCurrentDirectory, LPSTARTUPINFO lpStartupInfo, LPPROCESS_INFORMATION lpProcessInformation)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `LPCSTR` | **lpApplicationName** |
| `LPSTR` | **lpCommandLine** |
| `LPSECURITY_ATTRIBUTES` | **lpProcessAttributes** |
| `LPSECURITY_ATTRIBUTES` | **lpThreadAttributes** |
| `BOOL` | **bInheritHandles** |
| `DWORD` | **dwCreationFlags** |
| `LPVOID` | **lpEnvironment** |
| `LPCSTR` | **lpCurrentDirectory** |
| `LPSTARTUPINFO` | **lpStartupInfo** |
| `LPPROCESS_INFORMATION` | **lpProcessInformation** |

### 📤 Retorno

- **Tipo:** `BOOL`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, utilizo a função CreateProcess para iniciar um novo processo no Windows. Ao fornecer os parâmetros corretos, consigo controlar a criação do processo e suas características, impactando diretamente na execução do meu aplicativo.

---

## 🛠 Função: `LOG_ERR`

> **Resumo:** Registra uma mensagem de erro.

### 💻 Assinatura

```cpp
void LOG_ERR(const char* message)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const char*` | **message** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! A função LOG_ERR é utilizada para registrar mensagens de erro quando a criação do processo falha. Isso me ajuda a identificar problemas durante a execução do aplicativo, facilitando a depuração e a manutenção do código.

---

## 🛠 Função: `dosbox_realinit`

> **Resumo:** Inicializa os internos do DOSBox.

### 💻 Assinatura

```cpp
static void dosbox_realinit(SectionProp& section)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `SectionProp&` | **section** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, estou inicializando os internos do DOSBox. A ação envolve configurar variáveis, definir o tipo de máquina e ajustar a estratégia de falha do MCB. O impacto é que isso garante que o DOSBox funcione corretamente com as configurações do usuário.

---

## 🛠 Função: `DOSBOX_Init`

> **Resumo:** Inicializa o módulo DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu inicializo o módulo DOSBox, garantindo que todas as configurações e mensagens necessárias sejam carregadas. Isso é importante para preparar o ambiente de emulação, permitindo que o DOSBox funcione corretamente e ofereça uma experiência de usuário fluida.

---

## 🛠 Função: `DOSBOX_Destroy`

> **Resumo:** Destrói os módulos do DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_Destroy()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu implemento a função DOSBOX_Destroy. Ela é responsável por liberar todos os recursos alocados pelos módulos do DOSBox. Ao chamar essa função, garantimos que a memória e outros recursos sejam corretamente liberados, evitando vazamentos e garantindo um encerramento limpo do emulador.

---

## 🛠 Função: `notify_dosbox_setting_updated`

> **Resumo:** Notifica sobre atualizações de configurações do DOSBox.

### 💻 Assinatura

```cpp
static void notify_dosbox_setting_updated(const SectionProp& section, const std::string prop_name)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const SectionProp&` | **section** |
| `const std::string` | **prop_name** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu criei a função notify_dosbox_setting_updated. Ela é chamada quando uma configuração do DOSBox é atualizada. Dependendo da propriedade alterada, a função executa ações específicas, como carregar mensagens ou ajustar a taxa de atualização, garantindo que as mudanças sejam refletidas imediatamente.

---

## 🛠 Função: `add_dosbox_config_section`

> **Resumo:** Adiciona uma seção de configuração ao DOSBox.

### 💻 Assinatura

```cpp
static void add_dosbox_config_section(const ConfigPtr& conf)
```

### 📥 Parâmetros

| Tipo | Nome |
| :--- | :--- |
| `const ConfigPtr&` | **conf** |

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, add_dosbox_config_section, eu adiciono uma nova seção de configuração ao DOSBox. Através dela, é possível definir propriedades como a linguagem e registrar manipuladores de atualização, permitindo que o emulador responda a mudanças nas configurações de forma dinâmica e eficiente.

---

## 🛠 Função: `DOSBOX_InitModuleConfigsAndMessages`

> **Resumo:** Inicializa as configurações e mensagens do módulo DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_InitModuleConfigsAndMessages()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu inicializo várias seções de configuração do DOSBox. Ao chamar esta função, garanto que todos os módulos necessários sejam configurados corretamente, evitando inicializações duplicadas e assegurando que o sistema funcione de maneira eficiente. Isso é crucial para a operação correta do emulador.

---

## 🛠 Função: `DOSBOX_InitModules`

> **Resumo:** Inicializa todos os módulos do DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_InitModules()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu cuido da inicialização de todos os módulos do DOSBox. Essa função é chamada para garantir que cada parte do sistema esteja pronta para uso, o que é fundamental para a experiência do usuário. Sem essa inicialização, o emulador pode não funcionar corretamente.

---

## 🛠 Função: `DOSBOX_InitModules`

> **Resumo:** Inicializa todos os módulos do DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_InitModules()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu inicializo todos os módulos necessários para o funcionamento do DOSBox. Ao chamar esta função, garanto que cada componente, como CPU e áudio, esteja pronto para uso, impactando diretamente a performance e a estabilidade do emulador.

---

## 🛠 Função: `DOSBOX_Init`

> **Resumo:** Inicializa o DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu realizo a inicialização do DOSBox. Essa função é crucial, pois estabelece o ambiente necessário antes de qualquer operação, garantindo que todos os sistemas estejam prontos para serem utilizados, o que é fundamental para a experiência do usuário.

---

## 🛠 Função: `PROGRAMS_AddMessages`

> **Resumo:** Adiciona mensagens de configuração ao programa.

### 💻 Assinatura

```cpp
void PROGRAMS_AddMessages()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu adiciono mensagens que ajudam na configuração do programa. Isso é importante para que os usuários entendam como usar o DOSBox corretamente, melhorando a usabilidade e a experiência geral do usuário.

---

## 🛠 Função: `LOG_StartUp`

> **Resumo:** Inicia o log do sistema.

### 💻 Assinatura

```cpp
void LOG_StartUp()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu começo o registro de logs do sistema. Essa função é essencial para monitorar o comportamento do DOSBox durante a execução, permitindo que desenvolvedores e usuários identifiquem problemas e melhorem a performance do emulador.

---

## 🛠 Função: `LOG_Init`

> **Resumo:** Inicializa o sistema de log.

### 💻 Assinatura

```cpp
void LOG_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu configuro o sistema de log do DOSBox. Isso é fundamental para garantir que todas as informações relevantes sejam registradas corretamente, ajudando na depuração e na análise de desempenho do emulador.

---

## 🛠 Função: `COMPOSITE_Init`

> **Resumo:** Inicializa o sistema composto.

### 💻 Assinatura

```cpp
void COMPOSITE_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu inicializo o sistema composto do DOSBox. Essa função é importante para garantir que todos os componentes gráficos e de entrada funcionem em conjunto, proporcionando uma experiência de emulação mais fluida e integrada.

---

## 🛠 Função: `CPU_Init`

> **Resumo:** Inicializa a emulação da CPU.

### 💻 Assinatura

```cpp
void CPU_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu inicializo a emulação da CPU do DOSBox. Isso é crucial, pois garante que a emulação do processador funcione corretamente, impactando diretamente a performance dos jogos e aplicativos executados no emulador.

---

## 🛠 Função: `FPU_Init`

> **Resumo:** Inicializa a emulação da FPU.

### 💻 Assinatura

```cpp
void FPU_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu inicializo a emulação da Unidade de Ponto Flutuante (FPU) do DOSBox. Essa função é importante para garantir cálculos precisos em aplicações que dependem de operações matemáticas complexas, melhorando a compatibilidade e a performance.

---

## 🛠 Função: `DMA_Init`

> **Resumo:** Inicializa o sistema DMA.

### 💻 Assinatura

```cpp
void DMA_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu inicializo o sistema de Acesso Direto à Memória (DMA) do DOSBox. Isso é essencial para garantir que a transferência de dados entre dispositivos e a memória funcione de forma eficiente, impactando a performance geral do emulador.

---

## 🛠 Função: `VGA_Init`

> **Resumo:** Inicializa a emulação da VGA.

### 💻 Assinatura

```cpp
void VGA_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu inicializo a emulação da placa gráfica VGA do DOSBox. Essa função é fundamental para garantir que os gráficos sejam renderizados corretamente, proporcionando uma experiência visual adequada para os usuários.

---

## 🛠 Função: `KEYBOARD_Init`

> **Resumo:** Inicializa a emulação do teclado.

### 💻 Assinatura

```cpp
void KEYBOARD_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu inicializo a emulação do teclado do DOSBox. Isso é importante para garantir que as entradas do usuário sejam capturadas corretamente, permitindo uma interação fluida com os jogos e aplicativos.

---

## 🛠 Função: `PCI_Init`

> **Resumo:** Inicializa a emulação do PCI.

### 💻 Assinatura

```cpp
void PCI_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu inicializo a emulação do barramento PCI do DOSBox. Essa função é essencial para garantir que dispositivos conectados funcionem corretamente, melhorando a compatibilidade e a performance do emulador.

---

## 🛠 Função: `VOODOO_Init`

> **Resumo:** Inicializa a emulação da placa Voodoo.

### 💻 Assinatura

```cpp
void VOODOO_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu inicializo a emulação da placa gráfica Voodoo do DOSBox. Isso é crucial para garantir que jogos que utilizam essa tecnologia gráfica funcionem corretamente, proporcionando uma experiência visual melhorada.

---

## 🛠 Função: `CAPTURE_Init`

> **Resumo:** Inicializa o sistema de captura de vídeo.

### 💻 Assinatura

```cpp
void CAPTURE_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu inicializo o sistema de captura de vídeo do DOSBox. Essa função é importante para permitir que os usuários gravem suas sessões de jogo, melhorando a experiência e possibilitando o compartilhamento de gameplay.

---

## 🛠 Função: `MIXER_Init`

> **Resumo:** Inicializa o mixer de áudio.

### 💻 Assinatura

```cpp
void MIXER_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu inicializo o mixer de áudio do DOSBox. Isso é essencial para garantir que todos os sons e músicas sejam reproduzidos corretamente, proporcionando uma experiência auditiva imersiva para os usuários.

---

## 🛠 Função: `MIDI_Init`

> **Resumo:** Inicializa a emulação MIDI.

### 💻 Assinatura

```cpp
void MIDI_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu inicializo a emulação MIDI do DOSBox. Essa função é importante para garantir que dispositivos MIDI funcionem corretamente, permitindo que os usuários desfrutem de uma experiência musical rica e diversificada.

---

## 🛠 Função: `DEBUG_Init`

> **Resumo:** Inicializa o sistema de depuração.

### 💻 Assinatura

```cpp
void DEBUG_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu inicializo o sistema de depuração do DOSBox. Isso é crucial para desenvolvedores que precisam monitorar e corrigir problemas, melhorando a qualidade e a estabilidade do emulador.

---

## 🛠 Função: `SBLASTER_Init`

> **Resumo:** Inicializa a emulação da Sound Blaster.

### 💻 Assinatura

```cpp
void SBLASTER_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu inicializo a emulação da placa de som Sound Blaster do DOSBox. Essa função é essencial para garantir que os sons sejam reproduzidos corretamente, proporcionando uma experiência auditiva autêntica para os usuários.

---

## 🛠 Função: `GUS_Init`

> **Resumo:** Inicializa a emulação da Gravis Ultrasound.

### 💻 Assinatura

```cpp
void GUS_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu inicializo a emulação da placa de som Gravis Ultrasound do DOSBox. Isso é importante para garantir que jogos que utilizam essa tecnologia de som funcionem corretamente, melhorando a experiência auditiva.

---

## 🛠 Função: `IMFC_Init`

> **Resumo:** Inicializa a emulação do IMFC.

### 💻 Assinatura

```cpp
void IMFC_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu inicializo a emulação do IMFC no DOSBox. Essa função é crucial para garantir que dispositivos conectados funcionem corretamente, melhorando a compatibilidade e a performance do emulador.

---

## 🛠 Função: `INNOVATION_Init`

> **Resumo:** Inicializa a emulação de inovação.

### 💻 Assinatura

```cpp
void INNOVATION_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu inicializo a emulação de inovação do DOSBox. Isso é importante para garantir que novas tecnologias e dispositivos sejam suportados, melhorando a experiência do usuário.

---

## 🛠 Função: `SPEAKER_Init`

> **Resumo:** Inicializa a emulação do alto-falante.

### 💻 Assinatura

```cpp
void SPEAKER_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Aqui, eu inicializo a emulação do alto-falante do DOSBox. Essa função é essencial para garantir que os sons sejam reproduzidos corretamente, proporcionando uma experiência auditiva completa para os usuários.

---

## 🛠 Função: `REELMAGIC_Init`

> **Resumo:** Inicializa a emulação do Reel Magic.

### 💻 Assinatura

```cpp
void REELMAGIC_Init()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Nesta função, eu inicializo a emulação do Reel Magic no DOSBox. Isso é importante para garantir que jogos que utilizam essa tecnologia funcionem corretamente, melhorando a experiência do usuário.

---

## 🛠 Função: `DOSBOX_DestroyModules`

> **Resumo:** Destrói os módulos do DOSBox.

### 💻 Assinatura

```cpp
void DOSBOX_DestroyModules()
```

### 📤 Retorno

- **Tipo:** `void`

### 📖 Descrição Detalhada

Olá, Time LEGACY DOC! Neste contexto, eu estou destruindo todos os módulos do DOSBox. A ação garante que todos os recursos alocados sejam liberados corretamente, evitando vazamentos de memória. Isso é crucial para manter a estabilidade e a eficiência do emulador ao encerrar suas operações.

---

