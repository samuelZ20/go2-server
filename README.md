# Go2 Voice Control

Controle por voz do robô Unitree Go2: wake word → transcrição → classificação de intenção → comando ao robô.

Este repositório contém o **servidor** (pipeline de IA + controle do robô). O código que roda na TV box (captura de áudio) fica em um repositório separado: [go2-tvbox](https://github.com/carlosvts/go2-tvbox).

## Arquitetura

```
[TV Box] ──TCP audio──▶ [inference] ──HTTP (não integrado ainda)──▶ [go2-api] ──WebRTC──▶ [Go2]
```

- **TV Box** (repo separado): captura áudio do microfone Anker e envia via TCP.
- **inference**: OpenWakeWord (wake word) → faster-whisper (transcrição) → SentenceTransformer (classificação de intenção).
- **go2-api** (repo separado): dono único da conexão WebRTC com o Go2; recebe o comando via HTTP e o executa no robô.

O controle do robô (WebRTC, comandos de movimento) não faz parte deste repositório — vive inteiramente no `go2-api`. O envio do intent classificado pelo `inference` para o `go2-api` via HTTP ainda não está implementado (ver `TODO` em `publish_command()` em `inference/src/server.py`).

Diagramas detalhados em [`organograms/`](./organograms):
- [Fluxo de dados completo](./organograms/fluxo_de_dados.md)
- [Serviços do docker-compose](./organograms/docker_compose_profiles.md)
- [Estados internos do inference](./organograms/inference_estados.md)

Histórico de bugs encontrados e soluções: [`docs/PROBLEMAS_E_SOLUCOES.md`](./docs/PROBLEMAS_E_SOLUCOES.md) (também navegável na [wiki](https://github.com/carlosvts/unitreego2/wiki)).

## Como reportar um bug

Encontrou um bug enfrentado durante o desenvolvimento? Registre em [`docs/PROBLEMAS_E_SOLUCOES.md`](./docs/PROBLEMAS_E_SOLUCOES.md) — esse arquivo é a fonte da verdade; a [wiki](https://github.com/carlosvts/unitreego2/wiki) é gerada automaticamente a partir dele e não deve ser editada diretamente.

Adicione uma nova entrada no final do arquivo seguindo este formato:

```
### [BUG-0XX] <título curto do problema>
**Componente:** <client-tvbox | server-docker-network | dependencias-python | performance-gpu | go2>
**Tags:** <3-5 palavras-chave em minúsculo, separadas por vírgula>

**Sintoma:** ...
**Causa raiz:** ...
**Solução:** ...
```

- **ID**: sequencial, sempre o próximo número livre (nunca renumeie ou reaproveite o ID de um item removido).
- **Componentes**:
  - `client-tvbox`: PyAudio, ALSA, microfone Anker, `generate_env.sh`, detecção de IP do lado da TV box, path do `.env` no `client_armbian.py` (repo separado [go2-tvbox](https://github.com/carlosvts/go2-tvbox))
  - `server-docker-network`: firewalld, Windows Firewall, `network_mode`, WSL2, docker-compose
  - `dependencias-python`: pip, torch, transformers, openwakeword, conflitos de versão
  - `performance-gpu`: latência do Whisper, CUDA, CPU vs GPU
  - `go2`: controle do robô via WebRTC, comandos de movimento, conexão/autenticação com o Go2 — vive no repositório separado `go2-api`, não neste repo
  - Se o bug tocar mais de uma área, use a categoria onde a causa raiz mora e adicione a outra como tag secundária.
- Depois do PR mergeado, rode `/sync-wiki` (comando do Claude Code, em [`.claude/commands/sync-wiki.md`](./.claude/commands/sync-wiki.md)) para regenerar a wiki.

## Estrutura do projeto

```
.
├── docker-compose.yml
├── inference/          # Dockerfile + código do pipeline de IA
├── organograms/        # Diagramas Mermaid da arquitetura
├── .env                # Configuração do servidor (não versionado)
└── docs/
    └── PROBLEMAS_E_SOLUCOES.md
```

> O controle do robô (WebRTC) vive no repositório separado `go2-api`, não aqui.

## Configuração (`.env`)

Crie um `.env` na raiz com as seguintes variáveis:

| Variável | Descrição |
|---|---|
| `PC_SERVER_IP` | IP do servidor na rede local |
| `TCP_PORT` | Porta TCP para receber áudio da TV box (padrão: `9876`) |
| `AUDIO_SAMPLE_RATE`, `AUDIO_CHANNELS`, `AUDIO_CHUNK_MS` | Formato de áudio — deve ser idêntico ao configurado na TV box |
| `OWW_MODEL`, `OWW_THRESHOLD` | Modelo e limiar de confiança do OpenWakeWord |
| `WAKE_COOLDOWN_S` | Tempo de espera após um comando antes de aceitar nova wake word |
| `POST_WAKE_DISCARD_MS` | Áudio descartado logo após detectar a wake word (evita capturar o fim da própria wake word) |
| `MIN_CMD_DURATION_S`, `SILENCE_TIMEOUT_MS`, `CMD_MAX_SECONDS` | Controle de captura do comando de voz |
| `WHISPER_MODEL`, `CPU_THREADS`, `BEAM_SIZE`, `NO_SPEECH_THRESHOLD` | Configuração do faster-whisper |
| `MAX_CMD_WORDS`, `REPETITION_THRESHOLD`, `INTENT_THRESHOLD` | Configuração do classificador de intenção |

## Como rodar

### Linux / macOS

O jeito recomendado é usar o `./run.sh` (DX helper com todos os comandos do projeto):

```bash
./run.sh                    # mostra o menu de ajuda com todos os comandos
./run.sh build              # build de todas as imagens
./run.sh up                 # sobe a inferência (wake word / Whisper / classificador)
./run.sh logs inference     # logs de um serviço específico
./run.sh down               # parar tudo
./run.sh gpu-check          # checa se há GPU NVIDIA disponível pro Docker
```

### Windows

Use o `.\run.ps1` (PowerShell), equivalente ao `run.sh` com os mesmos comandos:

```powershell
.\run.ps1                    # mostra o menu de ajuda com todos os comandos
.\run.ps1 build               # build de todas as imagens
.\run.ps1 up                  # sobe a inferência (wake word / Whisper / classificador)
.\run.ps1 logs inference      # logs de um serviço específico
.\run.ps1 down                # parar tudo
.\run.ps1 gpu-check           # checa se há GPU NVIDIA disponível pro Docker
```

> [!WARNING]
> **WSL2 / Docker Desktop precisa de memória suficiente alocada.** Por padrão, o WSL2 limita a RAM disponível para os containers a uma fração conservadora da máquina — insuficiente para builds pesados do `inference` (download/carregamento de múltiplos modelos: Whisper, OpenWakeWord, SentenceTransformer). Isso trava o build por 20+ minutos sem erro aparente.
>
> **Configure pelo menos 8GB** de memória para o WSL2 (Docker Desktop) ou para a distro WSL nativa antes de rodar `build` ou `voz`. Crie/edite `%USERPROFILE%\.wslconfig`:
> ```ini
> [wsl2]
> memory=8GB
> ```
> Ajuste para mais se a máquina tiver RAM sobrando. Depois de salvar, rode `wsl --shutdown` e reabra o Docker Desktop para aplicar. Detalhes em [`docs/PROBLEMAS_E_SOLUCOES.md`](./docs/PROBLEMAS_E_SOLUCOES.md) (item #11).

<details>
<summary>Comandos <code>docker compose</code> equivalentes (sem o run.sh)</summary>

```bash
docker compose build
docker compose up
docker compose logs -f inference
docker compose down
```

</details>

## Requisitos de hardware

- Suporte a GPU NVIDIA via CUDA, com detecção automática e fallback para CPU quando a GPU não está disponível (ou falha ao carregar). O Dockerfile do `inference` usa base `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`, e o `docker-compose.yml` reserva a GPU para o serviço via `deploy.resources.reservations.devices`.
- Roda também sem GPU (CPU-only), com latência de transcrição maior — ver [`docs/PROBLEMAS_E_SOLUCOES.md`](./docs/PROBLEMAS_E_SOLUCOES.md) para detalhes de configuração e resultados medidos.

## TV Box (repositório separado)

Ver [go2-tvbox](https://github.com/carlosvts/go2-tvbox) para setup do lado da TV box (captura de áudio, detecção automática de mic/IP).

## Autores

- Samuel Frizzone Cardoso
- Carlos Vinícius Teixeira de Souza
- Hugo Prado Lima

## Licença

Este projeto está sob licença restritiva — veja [LICENSE.md](./LICENSE.md). Todos os direitos reservados; uso não autorizado.