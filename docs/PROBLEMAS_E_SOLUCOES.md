# Registro de Problemas e Soluções — Go2 Voice Control

Histórico de bugs enfrentados durante o desenvolvimento, causa raiz e solução aplicada. Serve como referência para depuração futura — sintomas parecidos provavelmente têm a mesma causa.

Este arquivo é a **fonte da verdade**. A [wiki do repositório](https://github.com/carlosvts/unitreego2/wiki) é gerada automaticamente a partir dele (não editar a wiki diretamente).

**Como adicionar uma entrada nova:** acrescente no final do arquivo, no formato abaixo (veja detalhes de cada campo no [README](../README.md#como-reportar-um-bug)):

```
### [BUG-0XX] <título curto do problema>
**Componente:** <client-tvbox | server-docker-network | dependencias-python | performance-gpu | go2>
**Tags:** <3-5 palavras-chave em minúsculo, separadas por vírgula>

**Sintoma:** ...
**Causa raiz:** ...
**Solução:** ...
```

ID sequencial, nunca renumeado. Depois do merge, rode `/sync-wiki` para regenerar a wiki.

---

### [BUG-001] `openwakeword.utils.download_models()` — `AttributeError`
**Componente:** dependencias-python
**Tags:** openwakeword, tflite-runtime, python-version, pip, docker-build

**Sintoma:**
```
AttributeError: module 'openwakeword.utils' has no attribute 'download_models'
```
Ocorria no build da imagem Docker, na etapa `RUN python3 -c "import openwakeword; openwakeword.utils.download_models()"`.

**Causa raiz:** `openwakeword >= 0.5` depende obrigatoriamente de `tflite-runtime`, que não é mais mantido e só tem wheels pré-compiladas até Python 3.11. Como o Dockerfile usava `python:3.12-slim`, o `pip` não conseguia resolver a versão pinada e caía silenciosamente para `openwakeword==0.4.0` — versão antiga sem `download_models`. Não havia erro visível no `pip install`, só quebrava no passo seguinte.

**Solução:**
- Trocar a imagem base para `python:3.11-slim`.
- Fixar `openwakeword==0.6.0` no `requirements.txt` (nunca usar `>=`, para não cair em fallback silencioso de versão).

---

### [BUG-002] Container não aceita conexão da TV box mesmo com bind em `0.0.0.0`
**Componente:** server-docker-network
**Tags:** firewalld, nftables, porta-9876, zona-public

**Sintoma:** `nc -zv <ip_do_pc> 9876` retornava `No route to host` a partir da TV box, mesmo o log do container mostrando `TCP: 0.0.0.0:9876`.

**Causa raiz:** `firewalld` ativo no PC (independente do `ufw`, que estava inativo), com a interface Wi-Fi na zona `public`. A zona `public` só libera SSH (porta 22) e mDNS por padrão — qualquer outra porta recebe `reject with icmpx admin-prohibited`, que aparece pro cliente como "No route to host" (diferente de "connection refused", que indicaria porta fechada mas host acessível).

**Diagnóstico:** `sudo nft list ruleset` mostrou a regra de reject na chain `filter_INPUT`, e a chain `filter_IN_public_allow` só tinha `tcp dport 22` e `udp dport 5353`.

**Solução:**
```bash
sudo firewall-cmd --zone=public --add-port=9876/tcp --permanent
sudo firewall-cmd --reload
```
**Nota:** o `firewalld` é independente do que o Docker configura. Qualquer porta nova exposta no projeto precisa ser liberada manualmente da mesma forma.

---

### [BUG-003] `MIC_DEVICE_INDEX`/`ANKER_CARD_INDEX` mudando a cada boot
**Componente:** client-tvbox
**Tags:** pyaudio, alsa, anker, generate_env.sh

**Sintoma:** índices ALSA/PyAudio do microfone Anker mudavam entre reconexões/boots, exigindo ajuste manual no `.env` toda vez.

**Solução:** script (`scripts/generate_env.sh` no repo da TV box) que detecta o dispositivo pelo **nome** ("anker") em vez de índice fixo, e regrava o `.env` a cada execução via `run.sh`.

---

### [BUG-004] `find_mic_index.py` não encontra o Anker logo após reboot
**Componente:** client-tvbox
**Tags:** pyaudio, alsa, usb, boot, retry

**Sintoma:** `arecord -l` mostrava o Anker normalmente, mas o script Python retornava "nenhum dispositivo encontrado".

**Causa raiz:** o filtro original exigia `maxInputChannels > 0` no PyAudio. Logo após o boot, o PortAudio/ALSA pode reportar `0` canais de entrada de forma espúria para dispositivos USB (timing de enumeração), mesmo o dispositivo funcionando normalmente para captura real — o `arecord -l` usa um caminho diferente (fala direto com o kernel ALSA) e por isso não sofre do mesmo problema.

**Solução:** o script passou a testar abrindo um stream real (1 e depois 2 canais) em vez de confiar só no metadado `maxInputChannels`. Também foi adicionado retry com espera (5 tentativas, 3s de intervalo) para cobrir o tempo de estabilização do USB logo após o boot.

**Erro relacionado, mesma causa:** `OSError: [Errno -9998] Invalid number of channels` ao tentar abrir o stream — indicava que o PortAudio realmente não tinha negociado canais com o dispositivo ainda naquele momento (não só um bug de metadado), reforçando a necessidade do retry.

---

### [BUG-005] Script de detecção de IP do PC não encontrava o servidor
**Componente:** client-tvbox
**Tags:** generate_env.sh, nmap, ip-detection, wifi, firewalld

**Sintoma:** `generate_env.sh` escaneava a rede com `nmap`/fallback bash e não encontrava a porta `9876` aberta, mesmo com o IP fixo (`192.168.0.111`) funcionando perfeitamente quando usado manualmente.

**Causa raiz combinada:**
- Inicialmente, `nmap` não estava instalado na TV box, caindo no fallback bash (`/dev/tcp`), mais lento e frágil.
- Depois de instalar o `nmap`, o problema real era o item #2 acima (firewalld bloqueando a porta) — o scan estava correto, só não havia porta aberta para encontrar.
- Após reboot, timing de associação Wi-Fi da TV box também podia atrasar a detecção.

**Solução:** detecção de IP em camadas, da mais rápida pra mais lenta:
1. Override manual via variável de ambiente (`PC_SERVER_IP=x ./run.sh`)
2. Cache do último IP que funcionou (`config/.last_known_pc_ip`), testado antes de qualquer scan
3. IP default conhecido, testado antes do scan completo
4. Scan completo da sub-rede (`nmap`, com fallback bash puro se ausente) — só como último recurso

Com retry (5 tentativas, 3s de intervalo) em torno de toda a detecção, para cobrir instabilidade de rede logo após boot.

---

### [BUG-006] Instalação do `nmap` falhando via `apt`
**Componente:** client-tvbox
**Tags:** apt, nmap, bullseye-backports, debian

**Sintoma:**
```
E: The repository 'http://deb.debian.org/debian bullseye-backports Release' no longer has a Release file.
```

**Causa raiz:** repositório `bullseye-backports` foi arquivado pelo Debian (bullseye está próximo do fim do suporte). O `apt update` não falhava por completo, só pulava esse repositório — o `nmap` vem do repositório principal, não do backports.

**Solução:** o erro era apenas um aviso; `sudo apt install -y nmap` funcionou normalmente sem alteração nenhuma. Opcionalmente, comentar a linha do backports no `sources.list` para eliminar o aviso:
```bash
sudo sed -i '/bullseye-backports/s/^/#/' /etc/apt/sources.list
```

---

### [BUG-007] Path do `.env` incorreto em `client_armbian.py`
**Componente:** client-tvbox
**Tags:** dotenv, path, client_armbian.py, config

**Sintoma:** `.env` não era carregado; variáveis vinham vazias mesmo com o arquivo existindo em `config/.env`.

**Causa raiz:** o código usava
```python
os.path.join(os.path.dirname(__file__), "config", ".env")
```
o que monta o path como `src/config/.env` — sem subir um nível como o comentário do próprio código dizia (`../config/.env`). O fallback (`src/.env`) também não existia, então o carregamento falhava silenciosamente (comportamento padrão do `load_dotenv` quando o arquivo não existe).

**Solução:**
```python
_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.normpath(os.path.join(_script_dir, "..", "config", ".env"))
if not os.path.exists(_env_path):
    _env_path = os.path.join(_script_dir, ".env")
load_dotenv(dotenv_path=_env_path)
```

---

### [BUG-008] Latência alta na transcrição (Whisper medium ~5.3-5.4s por comando)
**Componente:** performance-gpu
**Tags:** whisper, faster-whisper, ctranslate2, cpu, latencia

**Sintoma:** latência total wake word → comando de ~8-10s, considerada inaceitável para controle em tempo real do robô.

**Diagnóstico:** quebrando por estágio (captura, transcrição, classificação), o tempo de transcrição do Whisper era praticamente **constante** (~5.3s) independente da duração do áudio (1.6s a 2.6s) — indicando que o gargalo é o custo fixo de rodar o modelo `medium` em CPU, não o tamanho do áudio.

**Causa raiz:** `faster-whisper` usa CTranslate2, que só acelera via CPU ou CUDA (NVIDIA) — GPU integrada Intel não é suportada por nenhum caminho do CTranslate2. O servidor atual (Dell Inspiron 14, i7 mobile, GPU integrada) roda 100% em CPU.

**Mitigação (enquanto sem GPU dedicada):**
- Trocar `WHISPER_MODEL` de `medium` para `small` (redução significativa de parâmetros/custo).
- `compute_type="int8"` no `WhisperModel`.
- `BEAM_SIZE=1` (greedy decoding) em vez de beam search maior.
- Ajustar `CPU_THREADS` para o número real de núcleos físicos do processador.

**Solução definitiva (planejada):** migrar o servidor para hardware com GPU NVIDIA e usar `device="cuda"` no `WhisperModel` — redução esperada de ~5.3s para a casa de 200-500ms por transcrição.

---

### [BUG-009] `network_mode: host` não funciona no Docker Desktop Windows/WSL2
**Componente:** server-docker-network
**Tags:** docker-compose, wsl2, network_mode, bridge, redis

**Sintoma:** servidor mostrava bind em `0.0.0.0:9876` no log do container, mas `netstat -ano | findstr 9876` no Windows não retornava nada, e a TV box recebia timeout (`Operation now in progress`) ao tentar conectar.

**Causa raiz:** com `network_mode: host`, containers no Docker Desktop para Windows ficam na rede interna da VM WSL2, não na interface física do Windows — diferente do Linux nativo, onde host = a máquina real.

**Solução:**
- Trocar `network_mode: host` por rede bridge padrão (removendo a linha de todos os serviços).
- Adicionar `ports: - "${TCP_PORT}:${TCP_PORT}"` explícito só no serviço `inference` (único que recebe conexão externa).
- Trocar todas as referências internas de `REDIS_HOST=127.0.0.1` para `REDIS_HOST=redis` (nome do serviço, resolvido via DNS interno do Compose).

**Trade-offs:** toda porta nova precisa ser declarada manualmente em `ports:`; `127.0.0.1` entre containers passa a significar o próprio container, não mais compartilhado; leve overhead de NAT (desprezível no volume de tráfego do projeto). Ganho: isolamento de rede (Redis não fica mais exposto na rede local).

**Por que é a solução mais portável:** funciona idêntico em Linux nativo, Docker Desktop Windows/WSL2 e Docker Engine dentro de WSL2 puro — diferente de `network_mode: host`, que só é ótimo em Linux nativo.

---

### [BUG-010] Windows Firewall bloqueando porta do servidor
**Componente:** server-docker-network
**Tags:** windows-firewall, powershell, porta-9876

**Sintoma:** mesmo após corrigir o bind/bridge (item #9), a TV box não conseguia conectar na porta do servidor rodando em Windows.

**Causa raiz:** Windows Defender Firewall bloqueia conexões de entrada não solicitadas por padrão, especialmente quando o perfil de rede da interface está como "Public" (`Get-NetConnectionProfile` mostrando `NetworkCategory: Public`).

**Solução:**
```powershell
New-NetFirewallRule -DisplayName "Go2 Inference TCP 9876" -Direction Inbound -LocalPort 9876 -Protocol TCP -Action Allow
```
(PowerShell como administrador.)

**Nota:** bug diferente do item #2 (firewalld no Linux) — mesmo sintoma de porta inacessível, causa raiz e ferramenta de correção completamente distintas por ser outro SO.

---

### [BUG-011] Limite de memória do WSL2 travando download de modelos durante o build
**Componente:** server-docker-network
**Tags:** wsl2, wslconfig, memoria, docker-build

**Sintoma:** build do container `inference` travava por 20+ minutos no passo de download do Whisper medium (`WhisperModel('medium')`), sem erro, aparentemente parado.

**Causa raiz:** WSL2 por padrão aloca um limite conservador de RAM (bem menor que o total da máquina), insuficiente para builds pesados com múltiplos modelos sendo baixados/carregados.

**Solução:** criar/editar `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
memory=8GB
```
(ajustar ao total real de RAM da máquina — testado com 16GB total), depois `wsl --shutdown` e reabrir o Docker Desktop.

---

### [BUG-012] Bug de escopo de variável no `generate_env.sh` (TV box) — override de `PC_SERVER_IP` ignorado
**Componente:** client-tvbox
**Tags:** bash, escopo-de-variavel, generate_env.sh, pc_server_ip

**Sintoma:** rodar `PC_SERVER_IP=<ip> ./run.sh` na TV box não usava o IP fornecido, caía sempre no scan de rede completo mesmo com o override explícito.

**Causa raiz:** o script fazia `PC_SERVER_IP=""` dentro do loop de retry ANTES de chamar a função `find_pc_ip()`. Como funções em Bash compartilham escopo de variáveis por padrão (sem `local`), isso apagava o valor do override antes da função conseguir checá-lo.

**Solução:** capturar o valor do override numa variável separada (`PC_SERVER_IP_OVERRIDE="${PC_SERVER_IP:-}"`) logo no topo do script, antes de qualquer lógica de retry/reset, e usar essa cópia dentro de `find_pc_ip()`.

---

### [BUG-013] Detecção de IP do servidor sem hardcode — removido default fixo
**Componente:** client-tvbox
**Tags:** generate_env.sh, ip-detection, cache, hardcode

**Sintoma/contexto:** versão inicial do `generate_env.sh` usava um `KNOWN_DEFAULT_IP` fixo no código como fast path. Isso quebra toda vez que o servidor muda de máquina/rede (aconteceu na migração do Dell para o PC com GPU).

**Solução:** nova função `last_known_ip()` que busca o último IP conhecido de duas fontes, sem hardcode:
- o arquivo de cache (`config/.last_known_pc_ip`), ou
- na ausência dele, o `PC_SERVER_IP` já gravado no `config/.env` de uma execução anterior.

Ordem de prioridade final: override manual → cache testado (confirma que a porta responde) → scan de rede → cache sem confirmar como último recurso (com aviso).

---

### [BUG-014] Índice PyAudio do microfone Anker inconsistente entre boots (índice 6 vs 14)
**Componente:** client-tvbox
**Tags:** pyaudio, alsa, anker, hw-vs-alias

**Sintoma:** `find_mic_index.py` às vezes retornava o índice 6 (dispositivo de hardware real, `hw:1,0`) e às vezes o 14 (alias genérico "anker" do ALSA), dependendo do boot.

**Observação:** essa hipótese foi levantada mas **não confirmada** como causa raiz de um problema real de wake word não disparando — o problema real nesse caso específico era de conexão de rede (itens #9-#10). Fica registrado mesmo assim como possível fonte de instabilidade futura.

**Mitigação aplicada:** `find_mic_index.py` agora separa candidatos em `hw_candidates` (nomes contendo "hw:") e `alias_candidates`, testando primeiro os de hardware antes de cair nos aliases genéricos.

---

### [BUG-015] Incompatibilidade torch/transformers (`finegrained_fp8`/`deepgemm`) ao adicionar suporte a GPU
**Componente:** dependencias-python
**Tags:** torch, transformers, sentence-transformers, cuda, pip

**Sintoma:**
```
AttributeError: module 'sys' has no attribute 'get_int_max_str_digits'
```
Ocorria no build, no passo do `SentenceTransformer`, dentro de `transformers/integrations/deepgemm.py`.

**Causa raiz:** `requirements.txt` não fixava versões de `torch`/`transformers`. Sem pin, o `pip` resolveu a versão mais recente do `transformers`, que carrega código experimental de suporte a FP8/MoE (irrelevante para o projeto) e que tem bug de compatibilidade com certas versões do `torch`.

**Solução:** fixar versões estáveis e testadas:
- `torch==2.4.1` (instalado via `--index-url https://download.pytorch.org/whl/cu124` para garantir build com suporte CUDA)
- `transformers==4.44.2`
- upgrade de `sentence-transformers` de `2.2.0` para `3.0.1` (aproveitando o momento para reduzir dívida técnica de uma versão já antiga)

---

### [BUG-016] `ModuleNotFoundError: async_timeout` ao importar `redis`
**Componente:** dependencias-python
**Tags:** redis, async-timeout, pip, requirements

**Sintoma:** container `inference` entrava em crash loop com
```
ModuleNotFoundError: No module named 'async_timeout'
```
dentro de `redis/asyncio/connection.py`.

**Causa raiz:** `requirements.txt` tinha `redis>=5.0.0` sem teto. Ao recalcular toda a árvore de dependências (após adicionar os pins de torch/transformers do item #15), o `pip` resolveu uma versão do `redis` que importa `async_timeout` incondicionalmente no código, mas não o declara como dependência obrigatória de instalação.

**Solução:** fixar `redis==5.0.8` e adicionar `async-timeout>=4.0.3` como dependência explícita no `requirements.txt`, independente do que o `redis` declarar internamente.

---

### [BUG-017] Falha transitória de rede durante build (download do OpenWakeWord via GitHub Releases)
**Componente:** server-docker-network
**Tags:** docker-build, rede, github, openwakeword, transitorio

**Sintoma:** build falhava no passo `openwakeword.utils.download_models()` com `ConnectionRefusedError` ao baixar `silero_vad.onnx` de `github.com/dscripka/openWakeWord/releases`, enquanto outros downloads (Hugging Face) no mesmo build funcionavam normalmente.

**Causa raiz:** instabilidade pontual de rede/DNS específica da conexão com GitHub naquele momento do build — não relacionado a firewall (outros domínios funcionaram) nem a nada de configuração do projeto.

**Solução:** re-executar o build resolveu (`docker compose build inference`, aproveitando cache das camadas já bem-sucedidas).

**Mitigação opcional (não aplicada):** adicionar retry de até 3 tentativas nessa camada específica do Dockerfile, para não depender de intervenção manual em falhas transitórias futuras.

---

### [BUG-018] Suporte a GPU (CUDA) para o Whisper — implementação e resultado
**Componente:** performance-gpu
**Tags:** cuda, whisper, docker-compose, nvidia, gpu

**Contexto:** servidor migrou de CPU-only (Dell Inspiron 14, i7) para máquina com GPU NVIDIA (RTX 3050 Ti Laptop, 4GB VRAM). Resolve o item #8 (latência alta em CPU) — ver item #8 para o diagnóstico original.

**Implementação:**
- Dockerfile do `inference` trocou a base de `python:3.11-slim` para `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`.
- `docker-compose.yml`: serviço `inference` ganhou `deploy.resources.reservations.devices` com `driver: nvidia`, `capabilities: [gpu]`.
- `server.py`: nova função `_detect_best_device_and_compute_type()` que consulta `ctranslate2.get_cuda_device_count()` e escolhe `device="cuda"` + `compute_type="float16"` se disponível, com fallback automático (via try/except no carregamento real do `WhisperModel`) para `device="cpu"` + `compute_type="int8"` caso a GPU falhe ao carregar (VRAM insuficiente, driver incompatível, etc). Nunca lança exceção não tratada — sempre entrega um modelo funcional.
- `run.ps1`/`run.sh` ganharam checagem automática de GPU (`Check-Gpu`/`check_gpu`, e comando dedicado `gpu-check`) que roda `docker run --gpus all nvidia/cuda:... nvidia-smi` antes de subir os profiles `voz`/`inference-debug` — informativo, não bloqueia o `up` se não houver GPU.

**Resultado medido:**
- Latência média do Whisper: ~5.6s (CPU) → ~0.43s (GPU) — queda de ~92%.
- Latência total do pipeline (wake word → comando): ~8.56s → ~3.06s — queda de ~64%.
- Novo gargalo identificado: etapa de captura/escuta (VAD aguardando silêncio + tempo real de fala do usuário) — considerado aceitável, não otimizado further por risco de cortar palavras faladas mais devagar.