#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  server.py — Container INFERENCE                                            ║
║                                                                              ║
║  Pipeline de IA completo (tudo em memória, zero serialização entre etapas): ║
║    TCP áudio → OpenWakeWord → Whisper → SentenceTransformer → Redis         ║
║                                                                              ║
║  Publica o comando final no canal Redis 'go2:commands'. O container         ║
║  robot-control consome e executa no robô.                                    ║
║                                                                              ║
║  Correções estruturais (zero hardcode):                                      ║
║    • Descarte pós-wake (elimina eco da wake word no comando)                 ║
║    • Detecção de repetição por razão de unicidade                           ║
║    • initial_prompt=None + vad_filter (anti-alucinação)                      ║
║    • Rejeição por duração e nº de palavras (regras físicas)                  ║
║    • Detecção automática de GPU (CUDA), com fallback robusto para CPU        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import collections
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from enum import Enum, auto
from typing import Deque

import numpy as np
import redis
import webrtcvad
import ctranslate2
from faster_whisper import WhisperModel

from intent_classifier import IntentClassifier, normalize

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [INFERENCE] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ─── Configuração (tudo via ambiente, injetado pelo docker-compose) ──────────
TCP_HOST            = os.getenv("PC_SERVER_IP", "0.0.0.0")
TCP_PORT            = int(os.getenv("TCP_PORT", "9876"))
SAMPLE_RATE         = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
CHUNK_MS            = int(os.getenv("AUDIO_CHUNK_MS", "30"))

# Wake word
OWW_MODEL           = os.getenv("OWW_MODEL", "hey_jarvis")
OWW_THRESHOLD       = float(os.getenv("OWW_THRESHOLD", "0.85"))
WAKE_COOLDOWN_S     = float(os.getenv("WAKE_COOLDOWN_S", "1.5"))

# Sincronização de áudio (física do sinal)
POST_WAKE_DISCARD_MS = int(os.getenv("POST_WAKE_DISCARD_MS", "400"))
MIN_CMD_DURATION_S   = float(os.getenv("MIN_CMD_DURATION_S", "0.4"))
SILENCE_TIMEOUT_MS   = int(os.getenv("SILENCE_TIMEOUT_MS", "600"))
CMD_MAX_SECONDS      = float(os.getenv("CMD_MAX_SECONDS", "6.0"))

# Whisper (medium — servidor potente)
WHISPER_MODEL       = os.getenv("WHISPER_MODEL", "medium")
CPU_THREADS         = int(os.getenv("CPU_THREADS", str(os.cpu_count() or 4)))
BEAM_SIZE           = int(os.getenv("BEAM_SIZE", "5"))
NO_SPEECH_THRESHOLD = float(os.getenv("NO_SPEECH_THRESHOLD", "0.6"))

# Filtros anti-alucinação (estruturais)
MAX_CMD_WORDS       = int(os.getenv("MAX_CMD_WORDS", "12"))
REPETITION_THRESHOLD = float(os.getenv("REPETITION_THRESHOLD", "0.5"))

# Redis
REDIS_HOST          = os.getenv("REDIS_HOST", "redis")
REDIS_PORT          = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CHANNEL       = os.getenv("REDIS_CHANNEL", "go2:commands")

# Derivados
CHUNK_SAMPLES       = SAMPLE_RATE * CHUNK_MS // 1000
CHUNK_BYTES         = CHUNK_SAMPLES * 2
PRE_BUFFER_FRAMES   = int(1500 / CHUNK_MS)
PAUSE_FRAMES        = int(SILENCE_TIMEOUT_MS / CHUNK_MS)

CMD_BEEP = b"\x01"

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="inference")

# Canal reverso para o beep
_client_writer: asyncio.StreamWriter | None = None
_client_writer_lock = asyncio.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
#  Detecção de GPU (CUDA) com fallback robusto para CPU
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_best_device_and_compute_type():
    """
    Detecta o melhor device/compute_type disponível para o CTranslate2
    (motor por trás do faster-whisper). Tenta CUDA primeiro; se não
    disponível ou falhar por qualquer motivo, cai para CPU com int8.
    Nunca lança exceção — sempre retorna algo utilizável.
    """
    try:
        cuda_device_count = ctranslate2.get_cuda_device_count()
    except Exception as e:
        log.warning("Não foi possível consultar dispositivos CUDA: %s", e)
        cuda_device_count = 0

    if cuda_device_count > 0:
        log.info("✓ CUDA detectado (%d dispositivo(s)). Tentando usar GPU.", cuda_device_count)
        return "cuda", "float16"

    log.info("CUDA não disponível — usando CPU (int8).")
    return "cpu", "int8"


def load_whisper_model(model_name: str, cpu_threads: int) -> WhisperModel:
    """
    Carrega o WhisperModel no melhor device disponível. Se CUDA for
    detectado mas o carregamento falhar na prática (VRAM insuficiente,
    cuDNN ausente, driver incompatível), faz fallback automático para CPU
    em vez de derrubar o servidor.
    """
    device, compute_type = _detect_best_device_and_compute_type()

    try:
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads if device == "cpu" else 0,
            num_workers=1,
        )
        log.info("✓ Whisper carregado: device=%s, compute_type=%s", device, compute_type)
        return model
    except Exception as e:
        if device == "cuda":
            log.warning("Falha ao carregar Whisper em CUDA (%s). Tentando fallback para CPU...", e)
            model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=cpu_threads,
                num_workers=1,
            )
            log.info("✓ Whisper carregado em CPU (fallback pós-falha de GPU).")
            return model
        raise


# ═══════════════════════════════════════════════════════════════════════════════
#  Modelos
# ═══════════════════════════════════════════════════════════════════════════════

log.info("Carregando Whisper (%s, threads=%d se CPU)...", WHISPER_MODEL, CPU_THREADS)
_whisper = load_whisper_model(WHISPER_MODEL, CPU_THREADS)
log.info("✓ Whisper pronto: %s (beam=%d)", WHISPER_MODEL, BEAM_SIZE)

_classifier = IntentClassifier()

_redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  OpenWakeWord (compatível 0.4.0 e 0.6.0)
# ═══════════════════════════════════════════════════════════════════════════════

class WakeWordEngine:
    def __init__(self, model_name: str, threshold: float) -> None:
        from openwakeword.model import Model as OWWModel
        self._threshold = threshold
        self._name = model_name
        try:
            self._model = OWWModel(wakeword_models=[model_name], inference_framework="onnx")
        except TypeError:
            log.warning("openwakeword antigo — carregando built-in e filtrando '%s'.", model_name)
            self._model = OWWModel()
            if model_name not in self._model.models:
                raise ValueError(f"Modelo '{model_name}' indisponível: {list(self._model.models)}")
        log.info("✓ OpenWakeWord: %s (threshold=%.2f)", model_name, threshold)

    def process_frame(self, frame: bytes) -> tuple[bool, float]:
        audio = np.frombuffer(frame, dtype=np.int16)
        scores = self._model.predict(audio)
        score = float(scores.get(self._name, 0.0))
        return score >= self._threshold, score

    def reset(self) -> None:
        try:
            self._model.reset()
        except AttributeError:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#  VAD
# ═══════════════════════════════════════════════════════════════════════════════

class VADCollector:
    def __init__(self, aggressiveness: int = 3) -> None:
        self._vad = webrtcvad.Vad(aggressiveness)
        self._pre: Deque[bytes] = collections.deque(maxlen=PRE_BUFFER_FRAMES)
        self._speech: list[bytes] = []
        self._sil = 0
        self._speaking = False

    def process(self, frame: bytes) -> bytes | None:
        is_speech = self._vad.is_speech(frame, SAMPLE_RATE)
        if not self._speaking:
            self._pre.append(frame)
            if is_speech:
                self._speaking = True
                self._sil = 0
                self._speech = list(self._pre)
        else:
            self._speech.append(frame)
            if is_speech:
                self._sil = 0
            else:
                self._sil += 1
                if self._sil >= PAUSE_FRAMES:
                    audio = b"".join(self._speech)
                    self._speaking = False
                    self._speech = []
                    self._sil = 0
                    self._pre.clear()
                    return audio
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  AudioBuffer
# ═══════════════════════════════════════════════════════════════════════════════

class AudioBuffer:
    def __init__(self) -> None:
        self._q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2000)

    async def put(self, frame: bytes) -> None:
        if self._q.full():
            try:
                self._q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self._q.put(frame)

    async def get(self) -> bytes:
        return await self._q.get()

    def drain(self) -> None:
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except asyncio.QueueEmpty:
                break


# ═══════════════════════════════════════════════════════════════════════════════
#  Utilitários anti-alucinação (estruturais, não hardcode)
# ═══════════════════════════════════════════════════════════════════════════════

def _has_pathological_repetition(texto: str, threshold: float = REPETITION_THRESHOLD) -> bool:
    """Detecta loop de repetição por razão únicas/totais. Genérico."""
    palavras = texto.lower().split()
    if len(palavras) < 6:
        return False
    return (len(set(palavras)) / len(palavras)) < threshold


# ═══════════════════════════════════════════════════════════════════════════════
#  Transcrição
# ═══════════════════════════════════════════════════════════════════════════════

def _transcribe(audio_bytes: bytes) -> str:
    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segs, _ = _whisper.transcribe(
        audio,
        language="pt",
        initial_prompt=None,          # anti-alucinação + escalável
        beam_size=BEAM_SIZE,
        best_of=BEAM_SIZE,
        temperature=0.0,
        condition_on_previous_text=False,
        vad_filter=True,
        no_speech_threshold=NO_SPEECH_THRESHOLD,
    )
    return " ".join(s.text.strip() for s in segs).strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  Beep (canal reverso TCP)
# ═══════════════════════════════════════════════════════════════════════════════

async def send_beep() -> None:
    global _client_writer
    async with _client_writer_lock:
        if _client_writer is None or _client_writer.is_closing():
            return
        try:
            _client_writer.write(CMD_BEEP)
            await _client_writer.drain()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#  Publicar comando no Redis
# ═══════════════════════════════════════════════════════════════════════════════

def publish_command(intent: str, score: float) -> None:
    payload = json.dumps({"intent": intent, "score": round(score, 3), "ts": time.time()})
    _redis.publish(REDIS_CHANNEL, payload)
    log.info("📤 Publicado no Redis: %s (score=%.2f)", intent, score)


# ═══════════════════════════════════════════════════════════════════════════════
#  Máquina de estados
# ═══════════════════════════════════════════════════════════════════════════════

class Estado(Enum):
    PASSIVO = auto()
    OUVINDO_COMANDO = auto()


async def state_machine(audio_buf: AudioBuffer, loop) -> None:
    wake = WakeWordEngine(OWW_MODEL, OWW_THRESHOLD)
    estado = Estado.PASSIVO
    last_return = 0.0

    log.info("🎯 ESTADO 1: PASSIVO — diga a wake word para ativar.")

    while True:
        if estado == Estado.PASSIVO:
            frame = await audio_buf.get()

            # Cooldown: consome (descarta) frames após voltar do ESTADO 2
            if time.perf_counter() - last_return < WAKE_COOLDOWN_S:
                continue

            found, score = wake.process_frame(frame)
            if not found:
                continue

            log.info("🔔 WAKE WORD DETECTADA (score=%.2f)", score)
            t0 = time.perf_counter()
            asyncio.create_task(send_beep())
            estado = Estado.OUVINDO_COMANDO

        elif estado == Estado.OUVINDO_COMANDO:
            log.info("👂 Ouvindo comando...")

            # 1) Limpa buffer + reseta OWW
            audio_buf.drain()
            wake.reset()

            # 2) Descarta eco da wake word (sincronização de sinal)
            n_discard = int(POST_WAKE_DISCARD_MS / CHUNK_MS)
            for _ in range(n_discard):
                await audio_buf.get()

            # 3) Captura por VAD
            vad = VADCollector(aggressiveness=3)
            max_frames = int(CMD_MAX_SECONDS * 1000 / CHUNK_MS)
            audio_cmd = None
            for _ in range(max_frames):
                frame = await audio_buf.get()
                result = vad.process(frame)
                if result is not None:
                    audio_cmd = result
                    break

            if not audio_cmd:
                log.warning("⚠️  Nenhum comando capturado.")
                last_return = time.perf_counter()
                estado = Estado.PASSIVO
                continue

            # 4) Rejeita áudio curto demais (regra física)
            if len(audio_cmd) < int(SAMPLE_RATE * 2 * MIN_CMD_DURATION_S):
                log.warning("🗑️  Áudio curto demais — descartando.")
                last_return = time.perf_counter()
                estado = Estado.PASSIVO
                continue

            # 5) Transcreve
            texto = await loop.run_in_executor(_executor, _transcribe, audio_cmd)

            # 6) Filtros anti-alucinação estruturais
            if not texto:
                log.warning("⚠️  Transcrição vazia.")
                last_return = time.perf_counter()
                estado = Estado.PASSIVO
                continue
            if len(texto.split()) > MAX_CMD_WORDS:
                log.warning("🗑️  Texto longo demais (%d palavras) — alucinação.", len(texto.split()))
                last_return = time.perf_counter()
                estado = Estado.PASSIVO
                continue
            if _has_pathological_repetition(texto):
                log.warning("🗑️  Repetição patológica — alucinação.")
                last_return = time.perf_counter()
                estado = Estado.PASSIVO
                continue

            log.info("🗣️  Transcrito: \"%s\"", texto)

            # 7) Classifica e publica
            intent, score = _classifier.classify(texto)
            if intent:
                log.info("✅ Comando: %s (%.2f) | latência: %.2fs",
                         intent, score, time.perf_counter() - t0)
                publish_command(intent, score)
            else:
                log.warning("❓ Não reconhecido (score=%.2f)", score)

            last_return = time.perf_counter()
            estado = Estado.PASSIVO


# ═══════════════════════════════════════════════════════════════════════════════
#  TCP receiver
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_client(reader, writer, audio_buf: AudioBuffer) -> None:
    global _client_writer
    addr = writer.get_extra_info("peername")
    log.info("📡 TV Box conectada: %s", addr)
    async with _client_writer_lock:
        _client_writer = writer
    frames = 0
    try:
        while True:
            frame = await reader.readexactly(CHUNK_BYTES)
            await audio_buf.put(frame)
            frames += 1
    except asyncio.IncompleteReadError:
        log.warning("📴 TV Box desconectou (%d frames).", frames)
    finally:
        async with _client_writer_lock:
            if _client_writer is writer:
                _client_writer = None
        writer.close()


async def main() -> None:
    log.info("=" * 60)
    log.info("  INFERENCE — Go2 Voice Pipeline")
    log.info("  TCP: %s:%d | Whisper: %s | Redis: %s:%d",
             TCP_HOST, TCP_PORT, WHISPER_MODEL, REDIS_HOST, REDIS_PORT)
    log.info("=" * 60)

    loop = asyncio.get_running_loop()
    audio_buf = AudioBuffer()
    asyncio.create_task(state_machine(audio_buf, loop))

    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, audio_buf),
        host=TCP_HOST, port=TCP_PORT, limit=2 ** 16,
    )
    log.info("✓ Servidor TCP ativo. Aguardando TV Box...")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Encerrado.")
    finally:
        _executor.shutdown(wait=False)