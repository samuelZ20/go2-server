# Dockerfile — ROBOT-CONTROL + TECLADO (ambos precisam do SDK do Go2)
# Build context = RAIZ do projeto (para acessar unitree_webrtc_connect/).

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libgl1 \
    libglib2.0-0 \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libsndfile1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─── SDK do Go2 ───────────────────────────────────────────────────────────────
COPY unitree_webrtc_connect/ /app/unitree_webrtc_connect/
RUN pip install --no-cache-dir -e /app/unitree_webrtc_connect/

# ─── Dependências: redis async + python-dotenv (fallback do teclado) ─────────
RUN pip install --no-cache-dir "redis>=5.0.0" "python-dotenv>=1.0.0"

# ─── Código: controlador (produção) + teclado (teste manual) ─────────────────
COPY robot_control/src/ /app/src/
COPY scripts_teste/ /app/scripts_teste/

# Comando padrão: controlador. O serviço 'teclado' sobrescreve via 'command'.
CMD ["python3", "src/controller.py"]