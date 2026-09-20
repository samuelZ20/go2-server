# Dockerfile — Container INFERENCE (OWW → Whisper medium → Classifier)
# Modelos baixados NO BUILD → imagem sobe 100% offline (exceto uso de GPU).
#
# Base com CUDA 12 + cuDNN já inclusos (necessário para faster-whisper/
# CTranslate2 usar GPU). Ainda funciona sem GPU — o código detecta e cai
# para CPU automaticamente se CUDA não estiver disponível.

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip python3.11-venv build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

WORKDIR /app

# ─── Dependências Python ──────────────────────────────────────────────────────
COPY requirements.txt /app/
# Torch com suporte CUDA explícito (evita ambiguidade de qual variante o pip resolveria)
# Timeout e retries para evitar problemas de rede ruim
RUN pip install --no-cache-dir --timeout=1000 --retries=5 torch==2.4.1 --index-url https://download.pytorch.org/whl/cu124
RUN pip install --no-cache-dir -r requirements.txt

# ─── Baixar modelos NO BUILD (offline) ────────────────────────────────────────
# Whisper medium (~1.5GB)
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('medium')"

# OpenWakeWord (modelos built-in: hey_jarvis, alexa, etc)
RUN python3 -c "import openwakeword; openwakeword.utils.download_models()"

# SentenceTransformer multilingual (~120MB)
RUN python3 -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# ─── Código ───────────────────────────────────────────────────────────────────
COPY src/ /app/src/

EXPOSE 9876

CMD ["python3", "src/server.py"]