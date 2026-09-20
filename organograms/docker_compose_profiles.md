# Serviços do docker-compose

Ver [fluxo_de_dados.md](./fluxo_de_dados.md) para o que o serviço faz.

```mermaid
flowchart TB
    subgraph compose["docker-compose.yml"]
        I1["inference"]
    end

    style compose fill:#e6f4ea
```

| Comando | Uso |
|---|---|
| `docker compose up` | Sobe a inferência (wake word/Whisper/classificador) |

O controle do robô (WebRTC) não faz mais parte deste repositório — é responsabilidade do `go2-api` (repo separado).
