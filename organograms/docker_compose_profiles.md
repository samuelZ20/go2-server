# Profiles do docker-compose

Cada profile ativa um subconjunto de serviços, dependendo do que está sendo testado.

Ver [fluxo_de_dados.md](./fluxo_de_dados.md) para o que cada serviço faz.

```mermaid
flowchart TB
    subgraph voz["profile: voz (produção)"]
        direction LR
        R1["redis"] --- I1["inference"] --- RC1["robot-control"]
    end

    subgraph debug["profile: inference-debug"]
        direction LR
        R2["redis"] --- I2["inference"]
    end

    subgraph keyboard["profile: keyboard-control"]
        T1["teclado\n(docker compose run --rm)"]
    end

    style voz fill:#e6f4ea
    style debug fill:#fef7e0
    style keyboard fill:#e8eaed
```

| Profile | Comando | Uso |
|---|---|---|
| `voz` | `docker compose --profile voz up` | Pipeline completo, produção |
| `inference-debug` | `docker compose --profile inference-debug up` | Testar wake word/Whisper/classificador sem o robô |
| `keyboard-control` | `docker compose run --rm teclado` | Testar o robô manualmente, sem voz |