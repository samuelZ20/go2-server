# Estados internos do `inference`

Máquina de estados executada dentro do container `inference` para cada sessão de comando.

Ver [fluxo_de_dados.md](./fluxo_de_dados.md) para onde essa caixa se encaixa no pipeline geral.

```mermaid
stateDiagram-v2
    [*] --> PASSIVO

    PASSIVO --> WakeDetectada: OpenWakeWord\nscore > OWW_THRESHOLD

    WakeDetectada --> Ouvindo: descarta POST_WAKE_DISCARD_MS

    Ouvindo --> Transcrevendo: silêncio (SILENCE_TIMEOUT_MS)\nou CMD_MAX_SECONDS atingido

    Transcrevendo --> Classificando: Whisper retorna texto

    Classificando --> Publicado: score > INTENT_THRESHOLD
    Classificando --> PASSIVO: score baixo\n(não reconhecido)

    Publicado --> PASSIVO: cooldown (WAKE_COOLDOWN_S)
```