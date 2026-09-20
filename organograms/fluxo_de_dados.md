# Fluxo de Dados — Go2 Voice Control

Visão macro do caminho de um comando de voz, do microfone até o robô.

Para o que acontece dentro da caixa "inference", ver [inference_estados.md](./inference_estados.md).

```mermaid
flowchart LR
    Mic["🎙️ Microfone Anker"] -->|áudio PCM| TVBox["TV Box\nclient_armbian.py"]
    TVBox -->|TCP :9876| Inference["Container: inference\n(OWW → Whisper → Classifier)"]
    Inference -.->|"HTTP (não integrado ainda)"| Go2Api["go2-api\n(repo separado)"]
    Go2Api -->|WebRTC| Go2["🐕 Unitree Go2"]

    style Inference fill:#e8f0fe
    style Go2Api fill:#fdecea
```

Este repositório cobre só até o `inference`. O envio do comando ao robô (via HTTP para o `go2-api`) ainda não está integrado — ver `TODO` em `publish_command()` no `inference/src/server.py`. O `go2-api` é dono único da conexão WebRTC com o Go2.