#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  control_keyboard.py — Controle do Unitree Go2 via teclado                  ║
║                                                                              ║
║  Uso:                                                                        ║
║    Docker:  docker compose run --rm teclado                                  ║
║    Direto:  ROBOT_IP=10.0.0.152 python3 scripts_teste/control_keyboard.py    ║
║                                                                              ║
║  O IP do robô vem da variável de ambiente ROBOT_IP:                          ║
║    • No Docker: injetada automaticamente pelo docker-compose (lê o .env)     ║
║    • Rodando direto: exporte ROBOT_IP ou use o python-dotenv                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os
import sys

# Fallback: se rodar FORA do Docker, tenta carregar o .env local.
# Dentro do Docker as variáveis já vêm injetadas, então isto é opcional.
try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=_env)
except ImportError:
    pass  # python-dotenv não instalado — usa variáveis de ambiente direto

from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD

# ─── IP do robô via ambiente (NUNCA hardcoded) ────────────────────────────────
ROBOT_IP: str = os.getenv("ROBOT_IP", "192.168.123.161")


async def main():
    print(f"🤖 Conectando ao Go2 em {ROBOT_IP}...")
    conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ROBOT_IP)

    try:
        await conn.connect()
        print("✅ Conectado ao Go2 com sucesso!")
        print()
        print("=" * 50)
        print("🎮 PAINEL DE CONTROLE GO2")
        print("=" * 50)
        print("1 - LEVANTAR (Stand Up)")
        print("2 - SENTAR (Sit / StandDown)")
        print("3 - ALONGAR (Stretch)")
        print("4 - GESTO COM A PATA (FingerHeart)")
        print("5 - DIZER OLÁ (Hello)")
        print("6 - ABANAR O RABO (WiggleHips)")
        print("0 - SAIR")
        print("=" * 50)

        # Mapeamento escalável — adicionar comando = 1 linha
        COMMANDS = {
            "1": ("Levantando...",     SPORT_CMD["StandUp"]),
            "2": ("Sentando...",       SPORT_CMD["StandDown"]),
            "3": ("Alongando...",      SPORT_CMD["Stretch"]),
            "4": ("Gesto da pata...",  SPORT_CMD["FingerHeart"]),
            "5": ("Dizendo olá...",    SPORT_CMD["Hello"]),
            "6": ("Abanando rabo...",  SPORT_CMD["WiggleHips"]),
        }

        while True:
            comando = await asyncio.to_thread(input, "\nDigite o comando: ")

            if comando == "0":
                print("👋 Encerrando...")
                break

            if comando in COMMANDS:
                descricao, sport_cmd = COMMANDS[comando]
                print(f"🤖 {descricao}")
                await conn.datachannel.pub_sub.publish_request_new(
                    RTC_TOPIC["SPORT_MOD"],
                    sport_cmd,
                )
            else:
                print("⚠️  Comando inválido. Use 1-6 ou 0 para sair.")

    except ConnectionRefusedError:
        print(f"❌ Não foi possível conectar ao Go2 em {ROBOT_IP}")
        print("   Verifique se o robô está ligado e na mesma rede.")
    except KeyboardInterrupt:
        print("\n👋 Encerrado pelo usuário.")
    finally:
        print("🔌 Desconectando...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass