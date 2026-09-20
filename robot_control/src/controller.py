#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  controller.py — Container ROBOT-CONTROL                                    ║
║                                                                              ║
║  Consome comandos do Redis (canal 'go2:commands') e executa no Unitree Go2  ║
║  via WebRTC. Isolado do pipeline de IA: se o robô cair, a inferência        ║
║  continua viva e vice-versa.                                                 ║
║                                                                              ║
║  Fluxo:                                                                       ║
║    Redis subscribe → {"intent": "SIT"} → SPORT_CMD → Go2                    ║
║                                                                              ║
║  Baseado em unitree_webrtc_connect >= 2.1.0 (legion1581).                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import os
import sys

import redis.asyncio as aioredis

from unitree_webrtc_connect import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
    RTC_TOPIC,
    SPORT_CMD,
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ROBOT] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# As exceções tipadas abaixo só existem em versões mais novas da lib
# (a partir do suporte a firmware Go2 >= 1.1.15 / chave AES-128 por
# dispositivo). Se a imagem tiver uma versão antiga instalada (ex: clone
# git desatualizado), caímos em classes-dummy que nunca serão de fato
# levantadas pela lib — o código continua funcionando, só perde o
# tratamento fino desses casos específicos até a lib ser atualizada.
try:
    from unitree_webrtc_connect import (
        AesKeyRequiredError,
        AesKeyRejectedError,
        LocalSignalingPortError,
        RobotBusyError,
        NoSdpAnswerError,
        DataChannelTimeoutError,
    )
except ImportError:
    log.warning(
        "⚠️ Versão instalada de unitree_webrtc_connect não tem as exceções "
        "tipadas (AesKeyRequiredError etc.) — provavelmente uma versão antiga. "
        "Considere atualizar a lib na imagem (ver Dockerfile)."
    )

    class AesKeyRequiredError(Exception):
        pass

    class AesKeyRejectedError(Exception):
        pass

    class LocalSignalingPortError(Exception):
        pass

    class RobotBusyError(Exception):
        pass

    class NoSdpAnswerError(Exception):
        pass

    class DataChannelTimeoutError(Exception):
        pass

# ─── Configuração (via ambiente) ──────────────────────────────────────────────
ROBOT_IP      = os.getenv("ROBOT_IP", "192.168.123.161")
# Necessário apenas em firmware Go2 >= 1.1.15 (handshake data2=3).
# Obtenha com: unitree-fetch-aes-key --email ... --password ... --device-type Go2
ROBOT_AES_KEY = os.getenv("ROBOT_AES_128_KEY") or None
REDIS_HOST    = os.getenv("REDIS_HOST", "redis")
REDIS_PORT    = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CHANNEL = os.getenv("REDIS_CHANNEL", "go2:commands")

# ─── Mapeamento intent → comando do SDK (escalável: adicionar = 1 linha) ─────
# Nota: "SIT" está mapeado para StandDown (deitar). Se você quiser o comando
# "Sit" de verdade (senta com as patas dianteiras erguidas), troque para
# SPORT_CMD["Sit"].
INTENT_TO_SPORT = {
    "STAND":        SPORT_CMD["StandUp"],
    "SIT":          SPORT_CMD["StandDown"],
    "STRETCH":      SPORT_CMD["Stretch"],
    "FINGER_HEART": SPORT_CMD["FingerHeart"],
    "HELLO":        SPORT_CMD["Hello"],
    "WAG_TAIL":     SPORT_CMD["WiggleHips"],
}


async def connect_robot() -> UnitreeWebRTCConnection:
    """Conecta ao Go2 com retry infinito (o robô pode ligar depois)."""
    while True:
        try:
            log.info("🤖 Conectando ao Go2 em %s...", ROBOT_IP)
            # Só passa aes_128_key se estiver definido: versões antigas da lib
            # (sem suporte a firmware >= 1.1.15) nem aceitam esse parâmetro no
            # construtor, e passar None incondicionalmente quebra nelas.
            conn_kwargs = {"ip": ROBOT_IP}
            if ROBOT_AES_KEY:
                conn_kwargs["aes_128_key"] = ROBOT_AES_KEY
            conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, **conn_kwargs)
            await conn.connect()
            log.info("✅ Conectado ao Go2!")
            return conn

        except AesKeyRequiredError:
            log.error(
                "🔑 Este robô exige a chave AES-128 por dispositivo "
                "(firmware Go2 >= 1.1.15). Rode: "
                "unitree-fetch-aes-key --email SEU_EMAIL --password SUA_SENHA "
                "--device-type Go2  e defina ROBOT_AES_128_KEY no ambiente."
            )
            await asyncio.sleep(10)
        except AesKeyRejectedError:
            log.error("🔑 Chave AES-128 incorreta para este robô. Verifique ROBOT_AES_128_KEY.")
            await asyncio.sleep(10)
        except LocalSignalingPortError:
            log.warning(
                "🔌 Não consegui alcançar as portas 9991/8081 em %s. "
                "Verifique se o IP está certo e se o robô está na mesma rede. "
                "Tentando em 5s...", ROBOT_IP,
            )
            await asyncio.sleep(5)
        except RobotBusyError:
            log.warning(
                "📱 O robô recusou a conexão — provavelmente o app Unitree Go "
                "ou outro cliente WebRTC já está conectado. Feche-o e tente novamente."
            )
            await asyncio.sleep(5)
        except NoSdpAnswerError:
            log.warning("📡 Sem resposta SDP do robô. Tentando em 5s...")
            await asyncio.sleep(5)
        except DataChannelTimeoutError:
            log.warning("⏱️ Data channel não validou a tempo. Tentando em 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            log.warning("Falha ao conectar (%s). Tentando em 5s...", e)
            await asyncio.sleep(5)


async def execute_command(conn: UnitreeWebRTCConnection, intent: str) -> None:
    """Traduz o intent e envia ao robô."""
    sport_cmd = INTENT_TO_SPORT.get(intent)
    if sport_cmd is None:
        log.warning("Intent '%s' sem mapeamento — ignorando.", intent)
        return
    log.info("🤖 Executando: %s", intent)
    try:
        await conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"],
            {"api_id": sport_cmd},
        )
        log.info("✓ %s executado.", intent)
    except Exception as e:
        log.error("Erro ao executar %s: %s", intent, e)


async def main() -> None:
    log.info("=" * 60)
    log.info("  ROBOT-CONTROL — Go2")
    log.info("  Robô: %s | Redis: %s:%d canal '%s'",
             ROBOT_IP, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL)
    log.info("=" * 60)

    # Conecta ao robô
    conn = await connect_robot()

    # Conecta ao Redis e assina o canal
    r = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)
    log.info("👂 Assinando canal Redis '%s'...", REDIS_CHANNEL)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            intent = data.get("intent")
            score = data.get("score", 0.0)
            log.info("📥 Recebido: %s (score=%.2f)", intent, score)

            # Reconecta automaticamente se a conexão WebRTC caiu.
            if not conn.isConnected:
                log.warning("Conexão com o Go2 caiu — reconectando...")
                conn = await connect_robot()

            await execute_command(conn, intent)
        except json.JSONDecodeError:
            log.warning("Mensagem inválida no Redis: %s", message["data"])
        except Exception as e:
            log.error("Erro ao processar comando: %s", e)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Encerrado.")