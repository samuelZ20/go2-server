# Fluxo de Dados — Go2 Voice Control

Visão macro do caminho de um comando de voz, do microfone até o robô.

Para o que acontece dentro da caixa "inference", ver [inference_estados.md](./inference_estados.md).

```mermaid
flowchart LR
    Mic["🎙️ Microfone Anker"] -->|áudio PCM| TVBox["TV Box\nclient_armbian.py"]
    TVBox -->|TCP :9876| Inference["Container: inference\n(OWW → Whisper → Classifier)"]
    Inference -->|publish comando| Redis[("Redis\npub/sub")]
    Redis -->|subscribe| RobotControl["Container: robot-control"]
    RobotControl -->|WebRTC| Go2["🐕 Unitree Go2"]

    style Inference fill:#e8f0fe
    style Redis fill:#fdecea
```